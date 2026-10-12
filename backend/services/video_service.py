"""
==============================================================
多模态理解服务（视频 / 图片）
==============================================================
视频采用降级方案（成本低、落地快）：
    关键帧抽提(ffmpeg) → 单帧图像理解(视觉LLM，多帧一次请求)
    → 音轨转写(ffmpeg 抽音频 + Whisper ASR)
    → LLM 融合归一化（生成标准查询，交给 Agent 检索与回答）

图片与视频同构：
    视觉理解提取要素 → LLM 融合归一化 → 交给 Agent（图片不再绕过检索）

处理流程：
    用户上传视频/图片 → POST /api/user/upload-video|upload-image 存储并返回 URL
    → WS 发送 {type:"video"|"image", ...}
    → analyze_video() / analyze_images() 产出要素与归一化查询
    → 归一化文本交给 ReAct Agent 生成回答
==============================================================
"""

import os
import re
import sys
import uuid
import shutil
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import UPLOAD_FOLDER, VIDEO_MAX_KEYFRAMES

# 视觉理解提示词：让模型从关键帧中提取场景与要素
FRAME_SYSTEM_PROMPT = (
    "你是视频内容理解助手。以下是一段视频中按时间顺序抽取的关键帧。\n"
    "请综合所有帧输出：\n"
    "1. 场景描述：画面中出现了什么（地点/建筑/景物/人物活动/文字信息）\n"
    "2. 关键要素：可识别的具体实体（如景点名、建筑名、设施、表演），逐个列出\n"
    "3. 时序变化：帧与帧之间场景的变化过程\n"
    "用简洁的中文陈述，不要逐帧罗列。"
)

# 视觉理解提示词（图片）：提取场景与要素
IMAGE_SYSTEM_PROMPT = (
    "你是图片内容理解助手。请分析图片并输出：\n"
    "1. 场景描述：画面中出现了什么（地点/建筑/景物/人物活动/文字信息）\n"
    "2. 关键要素：可识别的具体实体（如景点名、建筑名、设施、表演），逐个列出\n"
    "用简洁的中文陈述。"
)

# 融合归一化提示词：合并视觉+音频+用户问题，产出标准查询（{media_type} 动态替换为 视频/图片）
FUSION_SYSTEM_PROMPT = (
    "你是景区AI导游的多模态查询归一化器。用户上传了一段{media_type}并提问。\n"
    "给你三部分信息：用户问题、画面理解、音轨文字。\n"
    "请输出一段融合后的中文标准查询（120字以内），包含：\n"
    "1. 用户的核心问题或意图\n"
    "2. 画面中识别到的关键实体（景点名/建筑名/设施名）\n"
    "3. 音轨中提到的关键信息\n"
    "输出纯文本，不要任何格式符号和解释。"
)


_FFMPEG_PATH = None


def get_ffmpeg() -> Optional[str]:
    """
    解析 ffmpeg 可执行文件路径：
    1. 系统 PATH 中的 ffmpeg（服务器完整安装）
    2. imageio-ffmpeg 自带的二进制（pip 依赖兜底，Windows/常见平台可用）
    都不可用时返回 None。
    """
    global _FFMPEG_PATH
    if _FFMPEG_PATH:
        return _FFMPEG_PATH
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_PATH = found
        return found
    try:
        import imageio_ffmpeg
        _FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"[Video] 使用 imageio-ffmpeg 内置二进制：{_FFMPEG_PATH}")
        return _FFMPEG_PATH
    except Exception:
        return None


def _run_cmd(args: List[str], timeout: int = 120) -> Optional[bytes]:
    """执行命令行工具，成功返回 stdout，失败返回 None"""
    try:
        proc = subprocess.run(args, capture_output=True, timeout=timeout)
        if proc.returncode == 0:
            return proc.stdout
        err = proc.stderr.decode("utf-8", errors="ignore")[:200]
        print(f"[Video] 命令失败（{' '.join(args[:3])}...）：{err}")
        return None
    except FileNotFoundError:
        print(f"[Video] 未找到可执行文件：{args[0]}（请确认 ffmpeg 已安装）")
        return None
    except subprocess.TimeoutExpired:
        print(f"[Video] 命令超时：{' '.join(args[:3])}...")
        return None


def get_video_duration(video_path: str) -> float:
    """
    获取视频时长（秒）。
    优先 ffprobe（精确）；不可用时解析 `ffmpeg -i` 输出的 Duration 行（通用兜底）。
    """
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        print("[Video] ffmpeg 不可用，无法解析视频")
        return 0.0

    # 1. ffprobe 优先
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        out = _run_cmd([
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ], timeout=30)
        if out:
            try:
                return float(out.decode("utf-8").strip())
            except (ValueError, UnicodeDecodeError):
                pass

    # 2. ffmpeg -i stderr 解析（无输出文件时 ffmpeg 仍打印媒体信息，返回码非零属正常）
    try:
        proc = subprocess.run([ffmpeg, "-i", video_path], capture_output=True, timeout=30)
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", stderr)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mi * 60 + s
    except Exception as e:
        print(f"[Video] ffmpeg 解析时长失败：{e}")
    return 0.0


def extract_keyframes(video_path: str, max_frames: int = None) -> List[str]:
    """
    从视频中均匀抽取关键帧。

    返回：
        帧图片的本地路径列表（按时间顺序）；失败返回空列表。
    帧存放在 uploads/frames/ 下（URL 形式 /uploads/frames/...，
    可直接被视觉模型以本地文件方式加载），分析完成后由调用方清理。
    """
    if max_frames is None:
        max_frames = VIDEO_MAX_KEYFRAMES

    if not os.path.isfile(video_path):
        print(f"[Video] 视频不存在：{video_path}")
        return []

    duration = get_video_duration(video_path)
    if duration <= 0:
        print("[Video] 获取视频时长失败")
        return []

    # 均匀取时间点（跳过首帧 0 点，取中段更稳定）
    if duration <= max_frames:
        timestamps = [duration * (i + 0.5) / max_frames for i in range(max_frames)]
    else:
        step = duration / (max_frames + 1)
        timestamps = [step * (i + 1) for i in range(max_frames)]

    now = datetime.now()
    frame_dir = os.path.join(UPLOAD_FOLDER, "frames", now.strftime("%Y%m%d"))
    os.makedirs(frame_dir, exist_ok=True)
    batch_id = uuid.uuid4().hex[:12]

    frame_paths = []
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        print("[Video] ffmpeg 不可用，无法抽帧")
        return []

    for i, ts in enumerate(timestamps):
        frame_path = os.path.join(frame_dir, f"{batch_id}_{i:02d}.jpg")
        out = _run_cmd([
            ffmpeg, "-y",
            "-ss", f"{ts:.2f}",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",  # JPEG 质量 2-5（1最高）
            frame_path,
        ], timeout=60)
        if os.path.isfile(frame_path):
            frame_paths.append(frame_path)

    print(f"[Video] 抽帧完成：{len(frame_paths)}/{len(timestamps)} 帧（时长 {duration:.1f}s）")
    return frame_paths


def frame_path_to_url(frame_path: str) -> str:
    """本地帧路径 → /uploads/... URL（复用视觉模型的本地文件加载逻辑）"""
    relative = os.path.relpath(frame_path, UPLOAD_FOLDER).replace(os.sep, "/")
    return f"/uploads/{relative}"


def extract_audio_text(video_path: str, asr_service=None) -> str:
    """抽取视频音轨为 mp3 并 ASR 转文字；无音轨或失败返回空串"""
    if asr_service is None:
        return ""
    mp3_path = None
    try:
        ffmpeg = get_ffmpeg()
        if not ffmpeg:
            print("[Video] ffmpeg 不可用，跳过音轨转写")
            return ""
        fd, mp3_path = _temp_file(".wav")
        out = _run_cmd([
            ffmpeg, "-y",
            "-i", video_path,
            "-vn",              # 去掉视频流
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            mp3_path,
        ], timeout=120)
        if (mp3_path and os.path.isfile(mp3_path)
                and os.path.getsize(mp3_path) >= 1024):
            return asr_service.transcribe_file(mp3_path) or ""
        print("[Video] 无有效音轨（或音频过短），跳过语音转写")
        return ""
    except Exception as e:
        print(f"[Video] 音轨转写失败：{e}")
        return ""
    finally:
        if mp3_path and os.path.exists(mp3_path):
            try:
                os.unlink(mp3_path)
            except Exception:
                pass


def _temp_file(suffix: str):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return fd, path


def _vision_describe(image_urls: List[str], system_prompt: str) -> str:
    """视觉 LLM 理解图片/关键帧（多图一次请求，流式聚合）—— 视频与图片共用"""
    from services.llm_service import get_llm_service
    llm = get_llm_service()
    if not llm.is_configured() or not image_urls:
        return ""

    prompt = f"{system_prompt}\n\n请描述这些图片的内容："
    chunks = []
    try:
        for chunk in llm.chat_with_images_stream(prompt, image_urls):
            chunks.append(chunk)
    except Exception as e:
        print(f"[Vision] 视觉理解失败：{e}")
        return ""
    return "".join(chunks).strip()


def _describe_frames(frame_paths: List[str]) -> str:
    """视觉 LLM 理解视频关键帧"""
    return _vision_describe(
        [frame_path_to_url(p) for p in frame_paths], FRAME_SYSTEM_PROMPT)


def _fuse(video_desc: str, audio_text: str, question: str, media_type: str = "视频") -> str:
    """LLM 融合归一化：用户问题 + 画面理解 + 音轨文字 → 标准查询"""
    from services.llm_service import get_llm_service
    llm = get_llm_service()
    if not llm.is_configured():
        # 降级：直接拼接原始要素
        parts = [p for p in [question, video_desc, audio_text] if p.strip()]
        return " ".join(parts)[:300]

    user_content = (
        f"用户问题：{question or '（用户未输入文字，请根据画面内容推断意图，如识别景点并介绍）'}\n\n"
        f"画面理解：{video_desc or '（无）'}\n\n"
        f"音轨文字：{audio_text or '（无音轨或无语音内容）'}"
    )
    try:
        result = llm.chat([
            {"role": "system", "content": FUSION_SYSTEM_PROMPT.replace("{media_type}", media_type)},
            {"role": "user", "content": user_content},
        ])
        return (result or "").strip()
    except Exception as e:
        print(f"[Vision] 融合归一化失败：{e}")
        parts = [p for p in [question, video_desc, audio_text] if p.strip()]
        return " ".join(parts)[:300]


def analyze_video(video_path: str, question: str = "",
                  asr_service=None, cleanup_frames: bool = True) -> Dict[str, Any]:
    """
    视频理解主流程（降级方案）。

    参数：
        video_path: 视频本地路径
        question: 用户随视频附带的文字问题（可为空）
        asr_service: ASR 实例（音轨转写用）
        cleanup_frames: 是否在分析完成后清理抽帧临时文件

    返回：
        {"frame_count", "video_desc", "audio_text", "normalized_query"}
        normalized_query 即归一化后的标准查询，交给 Agent 处理。
    """
    result = {"frame_count": 0, "video_desc": "", "audio_text": "", "normalized_query": ""}
    frame_paths = extract_keyframes(video_path)
    result["frame_count"] = len(frame_paths)

    try:
        result["video_desc"] = _describe_frames(frame_paths)
        result["audio_text"] = extract_audio_text(video_path, asr_service)
        result["normalized_query"] = _fuse(
            result["video_desc"], result["audio_text"], question)
        print(f"[Video] 融合查询：{result['normalized_query'][:150]}")
    finally:
        if cleanup_frames and frame_paths:
            try:
                for p in frame_paths:  # 仅清理本批次抽帧文件
                    if os.path.exists(p):
                        os.unlink(p)
            except Exception as e:
                print(f"[Video] 帧清理失败（不影响主流程）：{e}")

    return result


# ======================== 图片理解（与视频共用视觉理解与融合归一化） ========================

def save_image_bytes(image_bytes: bytes, ext: str = "jpg") -> str:
    """
    图片字节落盘到 uploads/images/，返回 /uploads/... URL。
    用途：旧版 base64 图片消息统一转为 URL，供视觉模型本地加载与静态访问。
    """
    if not image_bytes:
        return ""
    now = datetime.now()
    sub_dir = os.path.join(UPLOAD_FOLDER, "images", now.strftime("%Y%m%d"))
    os.makedirs(sub_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    path = os.path.join(sub_dir, filename)
    with open(path, "wb") as f:
        f.write(image_bytes)
    relative = os.path.relpath(path, UPLOAD_FOLDER).replace(os.sep, "/")
    return f"/uploads/{relative}"


def analyze_images(image_urls: List[str], question: str = "") -> Dict[str, Any]:
    """
    图片理解主流程（与视频同构）：
        视觉理解提取要素 → LLM 融合归一化 → 标准查询交给 Agent。

    参数：
        image_urls: 图片 URL 列表（/uploads/... 或 http 链接）
        question: 用户随图片附带的文字问题（可为空）

    返回：
        {"image_count", "image_desc", "normalized_query"}
    """
    image_urls = [u for u in (image_urls or []) if u]
    desc = _vision_describe(image_urls, IMAGE_SYSTEM_PROMPT)
    normalized = _fuse(desc, "", question, media_type="图片")
    print(f"[Image] 图片理解完成：{len(image_urls)} 张，融合查询：{normalized[:150]}")
    return {
        "image_count": len(image_urls),
        "image_desc": desc,
        "normalized_query": normalized,
    }