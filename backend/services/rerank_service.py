"""
==============================================================
RAG 精排服务（bge-reranker cross-encoder，可降级）
==============================================================
粗排（语义 + BM25 + RRF）取 top RERANK_TOP_K 候选后，
由 cross-encoder 对 (query, document) 对打分，按精排分数重排并截取最终 top_k。

降级策略（任何一步失败都不影响粗排链路）：
  - RERANK_ENABLED=false            → 跳过精排
  - FlagEmbedding 未安装 / 模型加载失败 → 跳过精排
  - 精排调用异常                     → 跳过精排，返回原顺序
==============================================================
"""

import os
import threading
from typing import List, Dict, Any, Optional

from config import RERANK_ENABLED, RERANK_MODEL

_lock = threading.Lock()
_reranker = None  # 懒加载单例
_load_failed = False  # 加载失败后标记，避免重复尝试拖慢链路


def _get_reranker():
    """懒加载精排模型（失败即降级）。复用 sentence-transformers 的 CrossEncoder，零新增依赖。"""
    global _reranker, _load_failed
    if not RERANK_ENABLED or _load_failed:
        return None
    with _lock:
        if _reranker is None and not _load_failed:
            try:
                from sentence_transformers import CrossEncoder
                os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
                _reranker = CrossEncoder(RERANK_MODEL)
                print(f"[Rerank] 精排模型已加载：{RERANK_MODEL}")
            except Exception as e:
                _load_failed = True
                print(f"[Rerank] 精排模型加载失败（降级为不精排）：{e}")
    return _reranker


def rerank(query: str,
           candidates: List[Dict[str, Any]],
           top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    对候选列表精排重排。

    参数：
        query:      查询文本
        candidates: 粗排候选，每项含 text 字段
        top_k:      返回条数（None 表示全部）

    返回：
        精排后的候选列表（附加 rerank_score 字段）；任何失败均返回原列表原顺序。
    """
    if not candidates:
        return candidates
    model = _get_reranker()
    if model is None:
        return candidates[:top_k] if top_k else candidates

    try:
        pairs = [(query, str(c.get("text", ""))) for c in candidates]
        scores = model.predict(pairs)  # 返回 numpy 数组
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        candidates = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
    except Exception as e:
        print(f"[Rerank] 精排调用失败（返回粗排原序）：{e}")

    return candidates[:top_k] if top_k else candidates
