"""
==============================================================
WebSocket 长连接处理模块
负责：
1. 实时音频流接收与ASR转写
2. 流式文本推送（分句、边生成边推送）
3. 音频数据推送
4. 情绪标签推送
5. 实时打断机制

使用 flask-sock 原生同步 API（非 asyncio 包装），
确保与 Flask 开发服务器兼容。
==============================================================
"""

import os
import sys
import json
import re
import subprocess
import threading
import time
import base64
import tempfile
import uuid
from typing import Optional

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import request
from flask_sock import Sock

from config import SENTENCE_SPLIT_PATTERN, UPLOAD_FOLDER
from models import db, ChatLog, DigitalHuman, User
from services.llm_service import get_llm_service
from services.agent_service import run_agent_stream
from services import memory_service
from services.tts_service import get_tts_service
from services.asr_service import get_asr_service
from services.emotion_service import get_emotion_service
from services.livetalking_service import get_livetalking_service

# ======================== WebSocket消息类型定义 ========================
# 客户端 -> 服务器
MSG_TYPE_TEXT = "text"          # 用户发送文本
MSG_TYPE_AUDIO = "audio"        # 用户发送音频数据
MSG_TYPE_IMAGE = "image"        # 用户发送图片
MSG_TYPE_VIDEO = "video"        # 用户发送视频（video_url + 可选 text）
MSG_TYPE_INTERRUPT = "interrupt"  # 用户打断
MSG_TYPE_HEARTBEAT = "heartbeat"  # 心跳

# 服务器 -> 客户端
MSG_TYPE_USER_TEXT = "user_text"        # 用户语音识别结果文本（前端应展示为用户消息）
MSG_TYPE_TEXT_START = "text_start"      # AI开始生成文本
MSG_TYPE_TEXT_CHUNK = "text_chunk"      # AI文本片段
MSG_TYPE_TEXT_END = "text_end"          # AI文本结束
MSG_TYPE_AUDIO_START = "audio_start"    # AI音频开始
MSG_TYPE_AUDIO_CHUNK = "audio_chunk"    # AI音频数据
MSG_TYPE_AUDIO_END = "audio_end"        # AI音频结束
MSG_TYPE_EMOTION = "emotion"            # 情绪标签推送
MSG_TYPE_STATUS = "status"              # 状态消息
MSG_TYPE_ERROR = "error"                # 错误消息
MSG_TYPE_DONE = "done"                  # 整个对话完成
MSG_TYPE_ROUTE = "route"                # 路线导航信息


# 全局待处理映射：{lt_sessionid: [{"flag": interrupt_flag, "ws": ws, "answer": full_answer}, ...]}
# 用于在 lt_synced 模式下等待 LiveTalking 说完再发 done
# 用 sessionid 为 key 避免多连接间的竞态
_pending_lt_waits = {}  # {sessionid: [dict, ...]}
_pending_lt_lock = threading.Lock()


def _convert_audio_to_pcm(audio_data: bytes) -> Optional[bytes]:
    """
    将前端录制的音频转为 16kHz/16bit/mono PCM

    策略：
    1. 将原始音频写入临时文件（保留原始格式）
    2. 用 ffmpeg 转为 PCM
    3. 若 ffmpeg 失败或不可用，直接用临时文件 + Whisper 原生解码

    返回 PCM 字节，或 None 表示需要走文件降级路径。
    """
    tmp_path = None
    try:
        # 写入临时文件（用 .webm 后缀，ffmpeg auto-detect 实际格式）
        fd, tmp_path = tempfile.mkstemp(suffix=".audio.webm")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(audio_data)

        # 用 ffmpeg 转码（不再强制 -f webm，由 ffmpeg 自动探测容器格式）
        proc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", tmp_path,                     # 自动探测输入格式
                "-ar", "16000",                      # 16kHz 采样率
                "-ac", "1",                          # 单声道
                "-sample_fmt", "s16",                # 16-bit signed
                "-f", "s16le",                       # 输出原始 PCM
                "-acodec", "pcm_s16le",
                "-af", "highpass=f=80,lowpass=f=7500",  # 带通滤波保留人声
                "pipe:1"
            ],
            capture_output=True,
            timeout=15
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
        else:
            print(f"[Audio] ffmpeg 转换失败（将走文件降级）：{proc.stderr.decode('utf-8', errors='ignore')[:200]}")
            # 返回空字节 + tmp_path，调用方可做文件降级
            return None
    except FileNotFoundError:
        print("[Audio] ffmpeg 未安装（将走文件降级）")
        return None
    except subprocess.TimeoutExpired:
        print("[Audio] ffmpeg 转换超时（将走文件降级）")
        return None
    except Exception as e:
        print(f"[Audio] 音频转换异常（将走文件降级）：{e}")
        return None
    finally:
        # 不在此处删除 tmp_path，调用方可能需要它做降级
        pass


def _transcribe_audio(audio_bytes: bytes, asr_service) -> str:
    """
    完整的音频转文字流程

    1. 尝试 ffmpeg 转为 PCM → Whisper 识别
    2. ffmpeg 不可用时，直接写临时文件 → Whisper 原生解码
    """
    pcm = _convert_audio_to_pcm(audio_bytes)
    if pcm:
        # ffmpeg 转码成功，用 PCM 数据识别
        return asr_service.transcribe(pcm)

    # ffmpeg 降级：将原始音频写入临时文件，让 Whisper 直接读文件
    # Whisper/faster-whisper 原生支持 webm/ogg/mp3 等格式
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".webm")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(audio_bytes)

        result = asr_service.transcribe_file(tmp_path)
        return result
    except Exception as e:
        print(f"[Audio] 文件降级识别失败：{e}")
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

def _send(ws, message: dict):
    """发送JSON消息到客户端（同步）"""
    try:
        ws.send(json.dumps(message, ensure_ascii=False))
    except Exception as e:
        print(f"[WebSocket] 发送消息失败：{e}")


def _cleanup_lt_wait(sid_key: str, wait_entry: dict):
    """从全局等待列表中移除指定条目"""
    with _pending_lt_lock:
        lst = _pending_lt_waits.get(sid_key, [])
        if wait_entry in lst:
            lst.remove(wait_entry)
            if not lst:
                _pending_lt_waits.pop(sid_key, None)


def clean_llm_text(text: str) -> str:
    """
    清理 LLM 输出中的 Markdown 符号和无关字符，
    保留纯净的中文自然语言文本，确保语音合成连贯自然。
    """
    if not text:
        return ""
    # 移除 Markdown 加粗/斜体标记（连续星号）
    text = re.sub(r'\*+', '', text)
    # 移除 Markdown 标题标记
    text = re.sub(r'#+\s*', '', text)
    # 移除 Markdown 列表标记（行首的 - * + 后跟空格）
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
    # 移除 Markdown 代码块标记
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # 移除 Markdown 链接，仅保留链接文字
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # 移除下划线标记
    text = re.sub(r'_+', '', text)
    # 移除波浪线标记
    text = re.sub(r'~+', '', text)
    # 移除多余空格
    text = re.sub(r'\s+', ' ', text)
    # 合并重复标点
    text = re.sub(r'[，,]+', '，', text)
    text = re.sub(r'[。.]+', '。', text)
    text = re.sub(r'[！!]+', '！', text)
    text = re.sub(r'[？?]+', '？', text)
    # 移除首尾空白
    text = text.strip()
    return text


def _receive(ws) -> Optional[dict]:
    """接收客户端JSON消息（同步）"""
    try:
        data = ws.receive()
        if data is None:
            return None
        if isinstance(data, str):
            return json.loads(data)
        return data
    except Exception:
        return None


def handle_chat(ws):
    """
    处理单次WebSocket连接的全双工通信（同步版本）
    由 flask-sock 的 @sock.route 直接调度
    """
    user_id = None
    digital_human_id = 1
    tts_voice = None
    tts_speed = 1.0
    tts_pitch = 1.0
    dh_personality = None  # 数字人性格描述（传递给大模型）
    is_interrupted = False
    current_question = ""
    current_image_urls = []      # 图片 URL 列表（新：使用服务器存储路径）
    current_image_path = None    # 兼容旧版
    current_image_data = None    # 兼容旧版
    lt_sessionid = ""  # LiveTalking WebRTC session id
    chat_session_id = str(uuid.uuid4())[:12]  # 本次 WebSocket 连接的一轮对话 ID
    welcome_played = False  # 欢迎动作只播一次

    # 获取服务实例
    llm = get_llm_service()
    tts = get_tts_service()
    asr = get_asr_service()
    emotion = get_emotion_service()
    lt = get_livetalking_service()  # LiveTalking 3D 数字人服务

    def parse_init_message(msg: dict):
        """解析客户端初始化消息（支持嵌套 data 字段）"""
        nonlocal user_id, digital_human_id, tts_voice, tts_speed, tts_pitch, dh_personality
        # 前端 websocket.js connect() 发送: { type:"text", data:'{"user_id":1,...}' }
        # user_id 嵌套在 data 字符串里，先尝试顶层再尝试 data 字段
        init_data = msg
        if isinstance(msg.get("data"), str):
            try:
                inner = json.loads(msg["data"])
                if isinstance(inner, dict):
                    init_data = inner
            except json.JSONDecodeError:
                pass
        user_id = init_data.get("user_id", 0)
        # 【安全】校验客户端上报的 user_id 是否真实存在，防止伪造身份越权
        try:
            if user_id and int(user_id) > 0:
                if not User.query.get(int(user_id)):
                    print(f"[WebSocket] 警告：客户端上报的 user_id={user_id} 不存在，降级为游客")
                    user_id = 0
        except (TypeError, ValueError):
            user_id = 0
        dh_id = init_data.get("digital_human_id", 1)
        digital_human_id = dh_id
        print(f"[WebSocket] 用户{user_id} 连接，数字人ID={dh_id}")
        try:
            dh = DigitalHuman.query.get(dh_id)
            if dh:
                tts_voice = dh.default_voice
                tts_speed = dh.default_speed
                tts_pitch = dh.default_pitch
                dh_personality = dh.personality
        except Exception:
            pass

    def split_sentences(text: str) -> list:
        """将长文本按句子分割"""
        parts = re.split(SENTENCE_SPLIT_PATTERN, text)
        sentences = [p.strip() for p in parts if p.strip()]
        if len(sentences) <= 1:
            return [text]
        merged = []
        for s in sentences:
            if len(s) < 5 and merged:
                merged[-1] += s
            else:
                merged.append(s)
        return merged if merged else [text]

    def process_question():
        """处理用户问题：RAG检索 -> 流式LLM生成 -> 实时分句推送 -> TTS合成 -> 情绪推送"""
        nonlocal is_interrupted, current_question, current_image_path, current_image_data, current_image_urls
        nonlocal tts_voice, tts_speed, tts_pitch, dh_personality

        if not current_question.strip():
            _send(ws, {"type": MSG_TYPE_ERROR, "data": "问题不能为空"})
            return

        if is_interrupted:
            return

        question = current_question

        # 每次提问前重新从数据库加载数字人配置（确保管理员修改后即时生效）
        try:
            dh = DigitalHuman.query.get(digital_human_id)
            if dh:
                tts_voice = dh.default_voice
                tts_speed = dh.default_speed
                tts_pitch = dh.default_pitch
                dh_personality = dh.personality
        except Exception:
            pass

        # 检测 LiveTalking 是否可用：可用则跳过本地 TTS，只用 WebRTC 音频（音画同步）
        lt_available = lt.is_available()

        # 检测 TTS 是否可用（当 LiveTalking 不可用时的降级语音）
        tts_available = tts.is_available() if not lt_available else False

        # 通知前端当前的音频模式
        if lt_available:
            print("[Audio] 使用 LiveTalking WebRTC 音频")
        elif tts_available:
            print("[Audio] 使用 Edge-TTS 本地音频")
        else:
            print("[Audio] 音频服务均不可用，使用纯文字模式")
            _send(ws, {"type": MSG_TYPE_STATUS, "data": "当前音频服务暂不可用，文字回复正常"})

        # ---- 步骤1：构建个性提示词 + 记忆注入（检索决策与知识库调用由 Agent/ReAct 内部自主完成） ----
        personality_section = ""
        if dh_personality and dh_personality.strip():
            personality_section = f"\n\n## 你的性格与说话风格（严格遵循）：\n{dh_personality.strip()}\n"

        # 可观测性：每轮提问一个 trace（未启用时为空操作）
        from services.observability_service import new_trace
        trace = new_trace(
            "chat.question",
            input={"question": question[:500]},
            metadata={"user_id": user_id, "session_id": chat_session_id},
        )

        # memoryAgent：短期记忆（本会话最近多轮）+ 长期记忆召回（用户画像/历史摘要）
        history_messages = []
        memory_context = ""
        try:
            memory = memory_service.get_memory_agent()
            history_messages = memory.get_short_term_messages(chat_session_id)
            memory_context = memory.recall_long_term(user_id or 0, question)
        except Exception as e:
            print(f"[WebSocket] 记忆加载失败（不影响主流程）：{e}")

        # ---- 步骤2：动作状态机 + Agent流式生成 ----
        nonlocal welcome_played
        if lt_available:
            if not welcome_played:
                welcome_played = True
                def _play_welcome():
                    time.sleep(0.5)
                    lt.set_audiotype(2, lt_sessionid or "")
                threading.Thread(target=_play_welcome, daemon=True).start()
            lt.set_audiotype(3, lt_sessionid)

        _send(ws, {"type": MSG_TYPE_STATUS, "data": "AI导游正在思考..."})
        _send(ws, {"type": MSG_TYPE_TEXT_START, "data": ""})

        full_answer = ""
        text_buffer = ""       # 累积流式文本
        sentence_buffer = ""   # 逐句缓存（用于TTS）
        chunk_index = 0
        full_audio = bytearray()
        emotion_label = "平静"
        route_info = None
        first_sentence_sent = False

        # 获取LLM流式生成器（Agent/ReAct 模式：图片/视频/语音/文字均已归一化为文本，统一走 Agent 检索链路）
        def _push_status(status_text):
            _send(ws, {"type": MSG_TYPE_STATUS, "data": status_text})

        stream_gen = run_agent_stream(
            question, personality_section,
            history_messages=history_messages,
            memory_context=memory_context,
            on_status=_push_status,
            trace=trace,  # 透传 trace，使 Orchestrator 与子 Agent 的工具 span 挂到同一链路
        )
        for chunk in stream_gen:
            if is_interrupted:
                break

            full_answer += chunk
            text_buffer += chunk
            sentence_buffer += chunk

            # 检查句子边界 → 分句推送文字（仅文字，语音等完整回答再一次性合成）
            boundary_chars = set("。！？.!?\n")
            if any(c in chunk for c in boundary_chars) and len(sentence_buffer) >= 5:
                sentences_in_buffer = re.split(SENTENCE_SPLIT_PATTERN, sentence_buffer)
                for s in sentences_in_buffer:
                    s = s.strip()
                    if s and len(s) >= 2:
                        # 清理 Markdown 符号后推送文字显示
                        clean_s = clean_llm_text(s)
                        _send(ws, {"type": MSG_TYPE_TEXT_CHUNK, "data": clean_s, "index": chunk_index})
                        chunk_index += 1
                sentence_buffer = ""

            # 实时分析情绪（每收到一段内容都更新）
            emotion_label = emotion.get_emotion_label(full_answer)
            _send(ws, {"type": MSG_TYPE_EMOTION, "data": emotion_label})

        # 推送剩余的句子缓存（无论是否被中断，都要刷出）
        if sentence_buffer.strip():
            remaining = sentence_buffer.strip()
            clean_remaining = clean_llm_text(remaining)
            _send(ws, {"type": MSG_TYPE_TEXT_CHUNK, "data": clean_remaining, "index": chunk_index})

        # 无论是否被中断，确保有兜底回答
        if not full_answer.strip():
            full_answer = "抱歉，我暂时无法回答这个问题。请咨询灵山胜境景区其他相关事宜。"

        # ---- 最终情绪推送 ----
        emotion_label = emotion.get_emotion_label(full_answer)
        _send(ws, {"type": MSG_TYPE_EMOTION, "data": emotion_label})

        # 清理 LLM 回答中可能残留的 JSON 语法字符和 Markdown 符号
        clean_answer = full_answer.strip()
        clean_answer = re.sub(r'^[{\[]\s*"answer"\s*:\s*"', '', clean_answer)
        clean_answer = re.sub(r'",?\s*"route_intent".*$', '', clean_answer)
        clean_answer = re.sub(r'"\s*}$', '', clean_answer)
        clean_answer = clean_answer.replace('\\n', '\n').strip()
        clean_answer = clean_llm_text(clean_answer)  # 清理 Markdown 符号，仅保留纯净中文文本

        # 文本生成已完成，先发 text_end（关闭前端"思考中"状态）
        _send(ws, {"type": MSG_TYPE_TEXT_END, "data": clean_answer})

        # 可观测性：结束 trace 并提交（WS 长连接需主动 flush）
        try:
            trace.end(output=clean_answer[:2000])
            trace.flush()
        except Exception:
            pass

        # ---- 语音合成：使用完整回答一次性合成，确保连贯 ----
        if not is_interrupted and clean_answer.strip():
            if lt_available:
                # LiveTalking 模式：设置说话动作，将完整文本一次性推送
                if not first_sentence_sent:
                    first_sentence_sent = True
                    lt.set_audiotype(0, lt_sessionid)
                # 发送完整文本作为单次音频块（lt_synced 标记让前端不播放本地音频）
                _send(ws, {"type": MSG_TYPE_AUDIO_CHUNK, "data": "", "index": 0, "text": clean_answer, "lt_synced": True})
                # 将完整文本一次性推送给 LiveTalking 口播
                lt.speak(clean_answer, lt_sessionid, voice=tts_voice)
            elif tts_available:
                # Edge-TTS 模式：一次性合成完整回答
                audio = tts.synthesize(clean_answer, voice=tts_voice, speed=tts_speed, pitch_value=tts_pitch)
                if audio:
                    full_audio = bytearray(audio)
                    audio_b64 = base64.b64encode(audio).decode("utf-8")
                    _send(ws, {"type": MSG_TYPE_AUDIO_CHUNK, "data": audio_b64, "index": 0, "text": clean_answer})

        try:
            route_info = llm.extract_route_info(question, full_answer)
            # 有路线意图时发送（含"识别为外地、无对应路线"的场景，前端据此展示提示而非固定灵山路线）
            if route_info.get("route_intent") and (route_info.get("route_data") or route_info.get("in_scope") is False):
                # 用干净的 answer 替换 route_info 中的 answer
                route_info["answer"] = clean_answer
                _send(ws, {"type": MSG_TYPE_ROUTE, "data": route_info})
        except Exception as e:
            print(f"[WebSocket] 路线信息发送失败：{e}")

        if lt_available:
            # LiveTalking 模式：数字人还在朗读，后台等待说完再发 done
            # 这样前端打断按钮会保持可见（isSpeaking=true）
            sid_key = lt_sessionid or "__default__"
            wait_entry = {
                "flag": {"interrupted": False},
                "ws": ws,
                "answer": clean_answer,
            }
            with _pending_lt_lock:
                if sid_key not in _pending_lt_waits:
                    _pending_lt_waits[sid_key] = []
                _pending_lt_waits[sid_key].append(wait_entry)

            def _wait_lt_finish():
                interrupt_flag = wait_entry["flag"]
                # 阶段1：等待 LiveTalking 开始说话（最多等 10 秒）
                waited = 0.0
                speaking_started = False
                while waited < 10.0:
                    if interrupt_flag["interrupted"]:
                        return
                    time.sleep(0.3)
                    waited += 0.3
                    try:
                        if lt.is_speaking(lt_sessionid):
                            speaking_started = True
                            print(f"[LiveTalking] 开始说话，等待了 {waited:.1f}s")
                            break
                    except Exception:
                        pass

                if not speaking_started:
                    print(f"[LiveTalking] 等待说话超时，直接发 done")
                    if not interrupt_flag["interrupted"]:
                        _send(ws, {"type": MSG_TYPE_DONE, "data": ""})
                    _cleanup_lt_wait(sid_key, wait_entry)
                    return

                # 阶段2：等待 LiveTalking 停止说话（最多等 60 秒）
                waited = 0.0
                while waited < 60.0:
                    if interrupt_flag["interrupted"]:
                        return
                    time.sleep(0.3)
                    waited += 0.3
                    try:
                        if not lt.is_speaking(lt_sessionid):
                            print(f"[LiveTalking] 说话结束，总等待 {waited:.1f}s")
                            break
                    except Exception:
                        pass
                if not interrupt_flag["interrupted"]:
                    try:
                        _send(ws, {"type": MSG_TYPE_AUDIO_END, "data": ""})
                        _send(ws, {"type": MSG_TYPE_DONE, "data": ""})
                    except Exception:
                        pass
                _cleanup_lt_wait(sid_key, wait_entry)

            t = threading.Thread(target=_wait_lt_finish, daemon=True)
            t.start()
        else:
            # 本地 TTS 模式：立即发送完成信号（原有行为）
            _send(ws, {"type": MSG_TYPE_AUDIO_END, "data": ""})
            _send(ws, {"type": MSG_TYPE_DONE, "data": ""})

        # ---- 步骤7：保存对话日志 ----
        try:
            voice_duration = len(full_audio) / 16000 if full_audio else 0
            log = ChatLog(
                session_id=chat_session_id or "",
                user_id=user_id or 0,
                question_text=question,
                answer_text=clean_answer,
                emotion_label=emotion_label,
                voice_duration=voice_duration,
                digital_human_id=digital_human_id,
                tts_voice=tts_voice or "zh-CN-XiaoxiaoNeural",
                image_urls=json.dumps(current_image_urls, ensure_ascii=False) if current_image_urls else None,
                route_data=json.dumps(route_info, ensure_ascii=False) if route_info else None,
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            print(f"[WebSocket] 保存对话日志失败：{e}")

    def _cleanup_previous_turn():
        """
        清理当前 WS 连接上前一轮的未完成消息状态。
        当用户发送新消息时调用，确保：
        1. 打断 LiveTalking 当前口播
        2. 清空 LiveTalking 句子队列
        3. 清理 _pending_lt_waits 中的等待条目（标记打断 + 发送 done）
        4. 标记 is_interrupted 阻止上一轮 process_question 的残余输出
        """
        nonlocal is_interrupted
        # 标记打断
        is_interrupted = True

        # 打断 LiveTalking 说话 + 清空队列
        lt.interrupt(lt_sessionid)

        # 清理当前 session 所有等待中的 LiveTalking 完成检查线程
        sid_key = lt_sessionid or "__default__"
        with _pending_lt_lock:
            entries = _pending_lt_waits.pop(sid_key, [])
        for entry in entries:
            entry["flag"]["interrupted"] = True
            try:
                _send(entry["ws"], {"type": MSG_TYPE_DONE, "data": ""})
            except Exception:
                pass

    # ==================== 主循环 ====================
    try:
        # 接收客户端初始化消息
        init_msg = _receive(ws)
        if init_msg:
            parse_init_message(init_msg)

        while True:
            message = _receive(ws)
            if message is None:
                break

            msg_type = message.get("type")

            # 更新 LiveTalking sessionid（每条消息都可能携带）
            sid = message.get("lt_sessionid", "")
            if sid:
                lt_sessionid = sid

            # 处理心跳
            if msg_type == MSG_TYPE_HEARTBEAT:
                _send(ws, {"type": MSG_TYPE_HEARTBEAT, "data": "pong"})
                continue

            # 处理打断信号
            if msg_type == MSG_TYPE_INTERRUPT:
                is_interrupted = True
                lt.interrupt(lt_sessionid)  # 同步打断 LiveTalking 3D 数字人
                # 清理当前 session 所有等待中的 LiveTalking 完成检查
                sid_key = lt_sessionid or "__default__"
                with _pending_lt_lock:
                    entries = _pending_lt_waits.pop(sid_key, [])
                for entry in entries:
                    entry["flag"]["interrupted"] = True
                    try:
                        _send(entry["ws"], {"type": MSG_TYPE_DONE, "data": ""})
                    except Exception:
                        pass
                _send(ws, {"type": MSG_TYPE_STATUS, "data": "已打断当前回复"})
                continue

            # 处理文本消息
            if msg_type == MSG_TYPE_TEXT:
                _cleanup_previous_turn()  # 清理上一轮未完成消息
                is_interrupted = False
                current_question = message.get("data", "")
                current_image_path = None
                current_image_data = None
                current_image_urls = []
                process_question()

            # 处理图片消息（多模态闭环：视觉提取要素 → 融合归一化 → 交给 Agent 检索回答）
            elif msg_type == MSG_TYPE_IMAGE:
                _cleanup_previous_turn()  # 清理上一轮未完成消息
                is_interrupted = False
                image_text = message.get("text", "") or ""

                # 收集图片URL：新格式 image_urls 列表；兼容旧格式单图 base64（落盘转URL）
                image_urls = message.get("image_urls", [])
                if not (image_urls and isinstance(image_urls, list)):
                    image_urls = []
                    image_b64 = message.get("data")
                    if image_b64:
                        try:
                            from services.video_service import save_image_bytes
                            url = save_image_bytes(base64.b64decode(image_b64))
                            if url:
                                image_urls = [url]
                        except Exception as e:
                            print(f"[WebSocket] 图片落盘失败：{e}")

                if not image_urls:
                    _send(ws, {"type": MSG_TYPE_ERROR, "data": "未收到图片，请重新上传"})
                else:
                    try:
                        _send(ws, {"type": MSG_TYPE_STATUS, "data": "正在理解图片内容..."})
                        from services.video_service import analyze_images
                        ir = analyze_images(image_urls, image_text)
                        if ir["normalized_query"]:
                            current_question = f"用户上传了图片并提出问题。{ir['normalized_query']}"
                            # 清空图片状态：归一化后走 Agent 检索链路（不再看图直答）
                            current_image_path = None
                            current_image_data = None
                            current_image_urls = []
                            _send(ws, {"type": MSG_TYPE_STATUS, "data": f"图片解析完成（{ir['image_count']}张）"})
                            process_question()
                        else:
                            _send(ws, {"type": MSG_TYPE_ERROR, "data": "图片内容解析失败，请换一张图片或使用文字提问"})
                    except Exception as e:
                        print(f"[WebSocket] 图片处理失败：{e}")
                        _send(ws, {"type": MSG_TYPE_ERROR, "data": f"图片处理失败：{str(e)}"})

            # 处理视频消息（多模态：关键帧+单帧理解+ASR+融合，归一化后走 Agent）
            elif msg_type == MSG_TYPE_VIDEO:
                _cleanup_previous_turn()  # 清理上一轮未完成消息
                is_interrupted = False
                video_url = message.get("video_url", "")
                video_text = message.get("text", "") or ""

                if not video_url:
                    _send(ws, {"type": MSG_TYPE_ERROR, "data": "未收到视频地址，请先通过 /api/user/upload-video 上传"})
                else:
                    try:
                        # 解析视频本地路径（/uploads/... → UPLOAD_FOLDER/...）
                        local_path = os.path.join(UPLOAD_FOLDER, video_url.lstrip("/").replace("uploads/", "", 1).replace("/", os.sep))
                        if not os.path.isfile(local_path):
                            _send(ws, {"type": MSG_TYPE_ERROR, "data": "视频文件不存在或已过期，请重新上传"})
                        else:
                            _send(ws, {"type": MSG_TYPE_STATUS, "data": "正在理解视频内容（抽帧/转写/融合）..."})
                            from services.video_service import analyze_video
                            vr = analyze_video(local_path, video_text, asr_service=asr)
                            if vr["normalized_query"]:
                                current_question = f"用户上传了一段视频并提出问题。{vr['normalized_query']}"
                                current_image_path = None
                                current_image_data = None
                                current_image_urls = []
                                _send(ws, {"type": MSG_TYPE_STATUS, "data": f"视频解析完成（{vr['frame_count']}帧）"})
                                process_question()
                            else:
                                _send(ws, {"type": MSG_TYPE_ERROR, "data": "视频内容解析失败，请换一段视频或使用文字提问"})
                    except Exception as e:
                        print(f"[WebSocket] 视频处理失败：{e}")
                        _send(ws, {"type": MSG_TYPE_ERROR, "data": f"视频处理失败：{str(e)}"})

            # 处理音频消息（语音通话/按住说话模式）
            elif msg_type == MSG_TYPE_AUDIO:
                _cleanup_previous_turn()  # 清理上一轮未完成消息
                is_interrupted = False
                audio_b64 = message.get("data", "")
                if audio_b64:
                    try:
                        _send(ws, {"type": MSG_TYPE_STATUS, "data": "正在识别语音..."})
                        audio_bytes = base64.b64decode(audio_b64)

                        # 完整音频转文字流程（ffmpeg转换 + Whisper识别 + 降级兜底）
                        current_question = _transcribe_audio(audio_bytes, asr)
                        current_image_path = None
                        current_image_data = None

                        if current_question and current_question.strip():
                            _send(ws, {"type": MSG_TYPE_USER_TEXT, "data": current_question})
                            process_question()
                        else:
                            _send(ws, {"type": MSG_TYPE_ERROR, "data": "语音识别失败，请使用文字输入"})
                    except Exception as e:
                        print(f"[WebSocket] 音频处理失败：{e}")
                        _send(ws, {"type": MSG_TYPE_ERROR, "data": f"音频处理失败：{str(e)}"})
                else:
                    _send(ws, {"type": MSG_TYPE_ERROR, "data": "未收到音频数据"})

    except Exception as e:
        print(f"[WebSocket] 连接处理异常：{e}")
        try:
            _send(ws, {"type": MSG_TYPE_ERROR, "data": f"服务器内部错误：{str(e)}"})
        except Exception:
            pass

    # ---- 连接结束（正常关闭或异常退出）：memoryAgent 后台压缩本会话长期记忆 ----
    try:
        from flask import current_app
        memory_service.compress_session_async(
            current_app._get_current_object(), user_id or 0, chat_session_id)
    except Exception as e:
        print(f"[WebSocket] 记忆压缩触发失败：{e}")


# ======================== WebSocket路由注册 ========================
def register_websocket(app, sock: Sock):
    """
    注册WebSocket路由

    参数：
        app: Flask应用
        sock: Sock实例
    """

    @sock.route("/ws/chat")
    def chat_ws(ws):
        """WebSocket聊天接口（同步版本）"""
        handle_chat(ws)