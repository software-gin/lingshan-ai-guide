"""
==============================================================
可观测性服务（Langfuse v4 封装，懒加载、缺省关闭、零侵入）
==============================================================
未配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 或 LANGFUSE_ENABLED=false 时：
所有埋点调用直接静默返回 None，业务链路不受任何影响。

Langfuse v4 API 变化：
  - 移除了 trace()/span()/generation() 顶层方法
  - 统一用 start_observation(name=, as_type=, input=) 创建 observation
  - 根 observation 自动创建 trace；子 observation 通过 root.start_observation() 挂载
  - as_type 可选: span / tool / agent / chain / retriever / generation 等

接入点（trace 命名约定）：
  chat.question     —— 每轮用户提问（chat_ws）
  tool.<name>       —— 工具执行（agents/base.py）
==============================================================
"""

import time
import threading
from contextlib import contextmanager
from typing import Optional, Any

from config import (
    LANGFUSE_ENABLED, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST,
)

_lock = threading.Lock()
_client = None  # 懒加载单例


def get_langfuse():
    """获取 Langfuse 客户端（未启用时返回 None）"""
    global _client
    if not LANGFUSE_ENABLED:
        return None
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return None
    with _lock:
        if _client is None:
            try:
                from langfuse import Langfuse
                _client = Langfuse(
                    public_key=LANGFUSE_PUBLIC_KEY,
                    secret_key=LANGFUSE_SECRET_KEY,
                    host=LANGFUSE_HOST,
                    timeout=30,  # OTel 导出超时（秒），cloud.langfuse.com 网络较慢需放宽
                )
                print(f"[Observability] Langfuse 已启用：{LANGFUSE_HOST}")
            except Exception as e:
                print(f"[Observability] Langfuse 初始化失败（降级为关闭）：{e}")
                _client = None
    return _client


class Trace:
    """
    轻量 trace 句柄：聚合一次用户提问下的所有 observation。
    根 observation 即 trace（v4 中 trace 由根 observation 隐式创建）。
    无客户端时为空操作对象。
    """

    def __init__(self, name: str, **kwargs):
        client = get_langfuse()
        self._t = None
        self._t0 = time.time()
        if client:
            try:
                # v4 start_observation 不接受 user_id/session_id 顶层参数，
                # 统一塞进 metadata 以便在 Langfuse 后台过滤查看。
                metadata = kwargs.get("metadata") or {}
                if kwargs.get("user_id"):
                    metadata["user_id"] = kwargs["user_id"]
                if kwargs.get("session_id"):
                    metadata["session_id"] = kwargs["session_id"]
                # v4：start_observation 创建根 observation，自动归属一个 trace
                self._t = client.start_observation(
                    name=name,
                    as_type="span",
                    input=kwargs.get("input"),
                    metadata=metadata or None,
                )
            except Exception as e:
                print(f"[Observability] 创建 trace 失败：{e}")
                self._t = None

    def span(self, name: str, as_type: str = "span", **kwargs) -> Optional[Any]:
        """
        在当前 trace 下创建子 observation。
        as_type: span / tool / agent / chain / retriever / generation ...
        支持 input / output / metadata 透传。
        注意：v4 OTel span 必须 end() 才会导出。若传入了 output（表示已完成），
              则自动 end() 并返回 None；否则返回 span 对象供调用方手动 end()。
        """
        if not self._t:
            return None
        try:
            sp = self._t.start_observation(
                name=name,
                as_type=as_type,
                input=kwargs.get("input"),
                output=kwargs.get("output"),
                metadata=kwargs.get("metadata"),
            )
            if kwargs.get("output") is not None:
                # output 已提供，说明该 span 代表的操作已完成，直接 end
                sp.end()
                return None
            return sp
        except Exception:
            return None

    def generation(self, name: str, **kwargs) -> Optional[Any]:
        """创建类型为 generation 的子 observation（LLM 调用）"""
        return self.span(name, as_type="generation", **kwargs)

    def end(self, output: Optional[str] = None, level: str = "DEFAULT", status_message: str = ""):
        """结束根 observation（即整个 trace）"""
        if not self._t:
            return
        try:
            elapsed = round((time.time() - self._t0) * 1000)
            self._t.update(
                output=(output or "")[:2000],
                metadata={"latency_ms": elapsed, "status_message": status_message},
                level=level,
            )
            self._t.end()
        except Exception:
            pass

    def flush(self):
        """显式提交（WS 长连接场景下需要主动 flush）"""
        client = get_langfuse()
        if client:
            try:
                client.flush()
            except Exception:
                pass


@contextmanager
def observe_span(trace: Optional[Trace], name: str, as_type: str = "span", **kwargs):
    """便捷上下文：with observe_span(trace, 'tool.xxx', as_type='tool') as s: ... """
    span = trace.span(name, as_type=as_type, **kwargs) if trace else None
    t0 = time.time()
    try:
        yield span
    finally:
        if span:
            try:
                span.end(metadata={"latency_ms": round((time.time() - t0) * 1000)})
            except Exception:
                pass


def new_trace(name: str, **kwargs) -> Trace:
    return Trace(name, **kwargs)
