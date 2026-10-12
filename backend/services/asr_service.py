"""
==============================================================
语音识别服务模块 (ASR)
基于 faster-whisper 本地离线运行，纯CPU执行
==============================================================
"""

import os
import sys
import re
import tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, ASR_INITIAL_PROMPT


# ======================== 景区专有名词纠错映射 ========================
# Whisper 对中文专有名词识别容易出错，这里做后处理纠正
# 格式："可能识别错" → "正确的词"
_CORRECTION_MAP = {
    # 景点名称纠错
    "灵山圣经": "灵山胜境",
    "灵山盛景": "灵山胜境",
    "灵山圣境": "灵山胜境",
    "灵山神经": "灵山胜境",
    "梵宫": "梵宫",
    "房公": "梵宫",
    "饭工": "梵宫",
    "九龙关羽": "九龙灌浴",
    "九龙关玉": "九龙灌浴",
    "九龙冠玉": "九龙灌浴",
    "九年关羽": "九龙灌浴",
    "黏花湾": "拈花湾",
    "年花湾": "拈花湾",
    "莲花湾": "拈花湾",
    "五年谈成": "五印坛城",
    "五星坛城": "五印坛城",
    "五银潭城": "五印坛城",
    "降幅阐释": "祥符禅寺",
    "享福阐释": "祥符禅寺",
    "响福禅寺": "祥符禅寺",
    "灵山金社": "灵山精舍",
    "佛山谈": "佛足坛",
    "佛珠坛": "佛足坛",
    "阿玉王住": "阿育王柱",
    "阿玉王柱": "阿育王柱",
    "天下第一张": "天下第一掌",
    "摆子戏弥勒": "百子戏弥勒",
    "白纸戏弥勒": "百子戏弥勒",
    "百子喜弥勒": "百子戏弥勒",
    "普提大道": "菩提大道",
    "不踢大道": "菩提大道",
    "香水河": "香水海",
    "放圣池": "放生池",
    "灵山塔": "灵山塔",
    "曼菲龙塔": "曼飞龙塔",
    "大雄宝殿": "大雄宝殿",
    "大熊宝殿": "大雄宝殿",
    # 常见景观词
    "大佛": "大佛",
    "喷泉": "喷泉",
    "雕塑": "雕塑",
    "钟楼": "钟楼",
    "鼓楼": "鼓楼",
    "广场": "广场",
    "停车场": "停车场",
    "停车厂": "停车场",
    # 服务相关
    "门票": "门票",
    "门票价格": "门票价格",
    "开放时间": "开放时间",
    "怎么走": "怎么走",
    "怎么去": "怎么去",
    "游览路线": "游览路线",
    "推荐路线": "推荐路线",
    "素斋": "素斋",
    "素食": "素食",
    "讲解": "讲解",
    "导游": "导游",
    "观光车": "观光车",
    "电瓶车": "电瓶车",
}


def _post_correct(text: str) -> str:
    """
    对 Whisper 识别结果做后处理纠错。
    1. 精确匹配常见错词并替换
    2. 去除不必要的标点（Whisper 有时会在短句中加句号）
    3. 合并多余空格
    """
    if not text:
        return text

    result = text

    # 精确替换已知的同音错字（按长度降序排列，优先匹配长词）
    sorted_keys = sorted(_CORRECTION_MAP.keys(), key=len, reverse=True)
    for wrong in sorted_keys:
        if wrong in result:
            correct = _CORRECTION_MAP[wrong]
            result = result.replace(wrong, correct)

    # 去除多余空格
    result = re.sub(r'\s+', '', result)

    # 清理无意义的尾部标点
    result = result.rstrip('，。！？,!?')

    if result != text:
        print(f"[ASR] 后处理纠错：{text} → {result}")

    return result


class ASRService:
    """
    语音识别服务
    将音频文件/音频数据转换为文字
    基于 faster-whisper，纯CPU本地运行
    """

    def __init__(self):
        self.model = None
        self.model_loaded = False
        print(f"[ASR] 初始化ASR服务，模型大小：{WHISPER_MODEL_SIZE}，设备：{WHISPER_DEVICE}")

    def _load_model(self):
        """延迟加载Whisper模型"""
        if self.model_loaded:
            return

        try:
            from faster_whisper import WhisperModel

            # 使用配置的 HF_TOKEN，避免 huggingface_hub 的未认证下载警告
            from config import HF_TOKEN
            os.environ.setdefault("HF_TOKEN", HF_TOKEN)
            os.environ.setdefault("HF_HUB_DISABLE_SYMPY_DOWNLOAD_WARNINGS", "1")

            # 使用int8量化，减少CPU负载
            self.model = WhisperModel(
                model_size_or_path=WHISPER_MODEL_SIZE,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
            )
            self.model_loaded = True
            print(f"[ASR] Whisper模型加载完成（{WHISPER_MODEL_SIZE}）")
        except ImportError:
            print("[ASR] 警告：faster-whisper未安装，使用模拟模式")
            self.model_loaded = True
        except Exception as e:
            print(f"[ASR] 警告：模型加载失败：{e}，使用模拟模式")
            self.model_loaded = True

    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        将音频数据转换为文字

        参数：
            audio_data: PCM音频二进制数据（16kHz, 16bit, mono）
            sample_rate: 采样率

        返回：
            识别出的文本
        """
        self._load_model()

        if self.model is None:
            return "用户语音输入内容"

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                self._write_wav(tmp_path, audio_data, sample_rate)

            # 执行语音识别（优化参数）
            segments, info = self.model.transcribe(
                tmp_path,
                beam_size=8,                          # 增大搜索宽度，提高准确率
                language="zh",
                initial_prompt=ASR_INITIAL_PROMPT,    # 引导模型识别专有名词
                temperature=0.0,                       # 确定性输出，避免随机偏差
                best_of=5,                             # 多候选取最优
                patience=1.0,                          # beam search 耐心值
                vad_filter=True,                       # 启用VAD过滤静音
                vad_parameters=dict(
                    min_silence_duration_ms=400,       # 稍短的静音边界，避免切碎
                    threshold=0.4,                     # VAD 灵敏度
                ),
                condition_on_previous_text=False,      # 避免幻觉关联上一句
                compression_ratio_threshold=2.4,       # 压缩比阈值，过滤解码失败
                log_prob_threshold=-1.0,               # 对数概率阈值
                no_speech_threshold=0.6,               # 无语音检测阈值
                word_timestamps=False,                 # 不需要时间戳，加速
            )

            # 收集识别结果
            text_parts = []
            for segment in segments:
                if segment.text and segment.text.strip():
                    text_parts.append(segment.text.strip())

            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            result = "".join(text_parts)
            # 后处理纠错
            result = _post_correct(result)
            print(f"[ASR] 识别结果：{result}")
            return result

        except Exception as e:
            print(f"[ASR] 语音识别失败：{e}")
            return ""

    def _write_wav(self, file_path: str, audio_data: bytes, sample_rate: int):
        """将PCM数据写入WAV文件"""
        import struct
        import wave

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)  # 单声道
            wf.setsampwidth(2)  # 16bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)

    def transcribe_file(self, file_path: str) -> str:
        """
        直接转录音频文件

        参数：
            file_path: 音频文件路径

        返回：
            识别出的文本
        """
        self._load_model()

        if self.model is None:
            return "用户语音输入内容"

        try:
            segments, info = self.model.transcribe(
                file_path,
                beam_size=8,
                language="zh",
                initial_prompt=ASR_INITIAL_PROMPT,
                temperature=0.0,
                best_of=5,
                patience=1.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400, threshold=0.4),
                condition_on_previous_text=False,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                word_timestamps=False,
            )

            text_parts = []
            for segment in segments:
                if segment.text and segment.text.strip():
                    text_parts.append(segment.text.strip())

            result = "".join(text_parts)
            result = _post_correct(result)
            return result

        except Exception as e:
            print(f"[ASR] 文件转录失败：{e}")
            return ""


# ======================== VAD静音检测 ========================
class VADDetector:
    """
    简单的VAD（语音活动检测器）
    基于能量阈值检测静音
    """

    def __init__(self, silence_threshold: float = 0.01, silence_duration: float = 3.0, sample_rate: int = 16000):
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.sample_rate = sample_rate
        self.silence_frames = int(sample_rate * silence_duration / 2)  # 每帧约30ms
        self.frame_size = int(sample_rate * 0.03)  # 30ms一帧

    def has_voice_activity(self, audio_chunk: bytes) -> bool:
        """
        检测音频块中是否包含语音活动

        参数：
            audio_chunk: PCM音频数据

        返回：
            True=检测到语音，False=静音
        """
        if len(audio_chunk) < 2:
            return False

        # 将bytes转换为int16数组
        import struct
        samples = struct.unpack(f"<{len(audio_chunk) // 2}h", audio_chunk[:len(audio_chunk) - len(audio_chunk) % 2])

        if not samples:
            return False

        # 计算RMS能量
        rms = np.sqrt(np.mean(np.array(samples, dtype=np.float32) ** 2))
        return rms > self.silence_threshold * 32768


# ======================== 全局单例 ========================
_asr_service = None


def get_asr_service() -> ASRService:
    """获取ASR服务单例"""
    global _asr_service
    if _asr_service is None:
        _asr_service = ASRService()
    return _asr_service
