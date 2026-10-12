"""
==============================================================
LiveTalking 3D 数字人服务封装
负责：
1. 将 AI 回答文本发送到 LiveTalking 进行 3D Avatar 口播
2. 支持打断当前播放
3. LiveTalking 不可用时自动降级

LiveTalking API（aiohttp 路由）：
- POST /human         驱动数字人说话
  Body: {"type": "echo", "text": "...", "sessionid": "..."}
- POST /interrupt_talk  打断当前说话
  Body: {"sessionid": "..."}

注意：LiveTalking 默认端口 8010
==============================================================
"""

import sys
import os
import time
import threading
import requests
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LIVETALKING_API_URL, LIVETALKING_ENABLED

# 可用性缓存刷新间隔（秒）
_AVAILABILITY_CACHE_TTL = 30


class LiveTalkingService:
    """LiveTalking 3D 数字人调度服务（句子队列版）"""

    def __init__(self):
        self.api_url = LIVETALKING_API_URL.rstrip("/")
        self.enabled = LIVETALKING_ENABLED
        self._session = None
        self._init_session()
        self._available = None
        self._available_time = 0  # 上次检查时间戳
        # 每个 sessionid 一个句子队列 + 打断标记，解决竞态与覆盖问题
        self._queues = {}          # {sessionid: deque of (text, voice)}
        self._queue_locks = {}     # {sessionid: threading.Lock}
        self._queue_interrupted = {}  # {sessionid: bool}
        print(f"[LiveTalking] 服务初始化，地址：{self.api_url}，启用：{self.enabled}")

    def _init_session(self):
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def _check_available(self) -> bool:
        if not self.enabled:
            return False
        now = time.time()
        # 缓存有效期内直接返回，超时后重新探测
        if self._available is not None and (now - self._available_time) < _AVAILABILITY_CACHE_TTL:
            return self._available
        try:
            resp = self._session.get(f"{self.api_url}/", timeout=3)
            self._available = resp.status_code < 500
        except Exception:
            self._available = False
            print(f"[LiveTalking] 服务不可达：{self.api_url}")
        self._available_time = now
        return self._available

    def is_available(self) -> bool:
        return self._check_available()

    # ========== 句子队列（解决覆盖问题） ==========

    def _ensure_queue(self, sessionid: str):
        """确保 sessionid 对应的队列存在"""
        sid = sessionid or "__default__"
        if sid not in self._queues:
            self._queues[sid] = deque()
            self._queue_locks[sid] = threading.Lock()
            self._queue_interrupted[sid] = False

    def speak(self, text: str, sessionid: str = "", voice: str = ""):
        """
        发送文本到 LiveTalking 进行 3D 口播（入队，不阻塞）

        参数：
            text: 朗读文本
            sessionid: WebRTC 会话 ID（从 /offer 协商获取）
            voice: 音色名称，如 "zh-CN-XiaoxiaoNeural"，传空则使用 LiveTalking 默认
        """
        if not text or not text.strip():
            return
        text = text.strip()
        sid = sessionid or "__default__"
        self._ensure_queue(sid)
        with self._queue_locks[sid]:
            self._queues[sid].append((text, voice))
            # 如果队列之前为空，启动消费者线程
            if len(self._queues[sid]) == 1:
                t = threading.Thread(target=self._process_queue, args=(sid,), daemon=True)
                t.start()

    def _process_queue(self, sid: str):
        """队列消费者：串行发送句子，等上一句说完再发下一句"""
        while True:
            with self._queue_locks[sid]:
                if self._queue_interrupted.get(sid, False) or not self._queues.get(sid):
                    # 被打断或队列空了，退出
                    return
                text, voice = self._queues[sid][0]  # peek，不弹出

            # 发送当前句子
            self._do_speak(text, sid, voice)

            # 等待 LiveTalking 说完当前句子（最多等 30 秒）
            waited = 0.0
            while waited < 30.0:
                with self._queue_locks[sid]:
                    if self._queue_interrupted.get(sid, False):
                        return
                time.sleep(0.3)
                waited += 0.3
                try:
                    if not self.is_speaking(sid if sid != "__default__" else ""):
                        break
                except Exception:
                    pass

            # 弹出已完成的句子
            with self._queue_locks[sid]:
                if self._queues.get(sid):
                    self._queues[sid].popleft()
                    if not self._queues[sid]:
                        # 队列空了，退出
                        return

    def _do_speak(self, text: str, sessionid: str, voice: str = ""):
        if not self._check_available():
            print(f"[LiveTalking] 不可用，降级跳过：{text[:30]}...")
            return
        try:
            url = f"{self.api_url}/human"
            payload = {"type": "echo", "text": text, "sessionid": sessionid if sessionid != "__default__" else ""}
            if voice:
                payload["tts"] = {"ref_file": voice}
            resp = self._session.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                print(f"[LiveTalking] 推送成功：{text[:30]}... voice={voice}")
            else:
                print(f"[LiveTalking] 推送失败 HTTP {resp.status_code}：{resp.text[:100]}")
        except requests.exceptions.Timeout:
            print(f"[LiveTalking] 请求超时")
        except requests.exceptions.ConnectionError:
            print(f"[LiveTalking] 连接失败，服务可能未启动")
            self._available = False
        except Exception as e:
            print(f"[LiveTalking] 发送异常：{e}")

    def interrupt(self, sessionid: str = ""):
        """打断 LiveTalking 当前说话 + 清空句子队列"""
        sid = sessionid or "__default__"
        self._ensure_queue(sid)
        # 标记打断 + 清空队列
        with self._queue_locks[sid]:
            self._queue_interrupted[sid] = True
            self._queues[sid].clear()
        if not self._check_available():
            # 重置打断标记（不清空的话下次还能用）
            with self._queue_locks[sid]:
                self._queue_interrupted[sid] = False
            return
        try:
            url = f"{self.api_url}/interrupt_talk"
            resp = self._session.post(url, json={"sessionid": sessionid or ""}, timeout=5)
            if resp.status_code == 200:
                print(f"[LiveTalking] 已打断（session={sessionid}）")
        except Exception as e:
            print(f"[LiveTalking] 打断失败：{e}")
        # 重置打断标记，允许后续 speak
        with self._queue_locks[sid]:
            self._queue_interrupted[sid] = False

    def set_audiotype(self, audiotype: int, sessionid: str = ""):
        """切换数字人动作状态
        audiotype: 0=正常说话 1=静音空闲 2+=自定义动作
        """
        if not self._check_available():
            return
        try:
            url = f"{self.api_url}/set_audiotype"
            resp = self._session.post(
                url,
                json={"audiotype": audiotype, "sessionid": sessionid or ""},
                timeout=5
            )
            if resp.status_code == 200:
                print(f"[LiveTalking] 切换动作 audiotype={audiotype}")
        except Exception as e:
            print(f"[LiveTalking] 切换动作失败：{e}")

    def is_speaking(self, sessionid: str = "") -> bool:
        """查询 LiveTalking 是否正在说话（API + 队列状态综合考虑）"""
        sid = sessionid or "__default__"
        # 如果还有排队中的句子，视为"正在说话"
        with self._queue_locks.get(sid, threading.Lock()):
            if self._queues.get(sid) and len(self._queues[sid]) > 0:
                return True
        if not self._check_available():
            return False
        try:
            url = f"{self.api_url}/is_speaking"
            resp = self._session.post(
                url,
                json={"sessionid": sessionid or ""},
                timeout=3
            )
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0:
                    return result.get("data", False)
        except Exception as e:
            print(f"[LiveTalking] 查询说话状态失败：{e}")
        return False


# ======================== 全局单例 ========================
_livetalking_service = None


def get_livetalking_service() -> LiveTalkingService:
    global _livetalking_service
    if _livetalking_service is None:
        _livetalking_service = LiveTalkingService()
    return _livetalking_service
