"""
==============================================================
知识图谱增强 RAG（GraphRAG）服务
==============================================================
两阶段：
1. 离线建图：用 LLM 从知识库内容抽取 (头实体, 关系, 尾实体) 三元组，
   持久化到 SQLite（KnowledgeTriple 表）。
2. 在线检索：查询时先做实体链接（词典最长匹配，无 LLM，零额外延迟），
   再沿图做邻域扩展（默认 1 跳），把向量检索命中的知识点用图谱关联起来，
   作为补充上下文返回。

设计考量：
- 建图耗时（每条知识一次 LLM 抽取），一律后台线程执行，不阻塞查询。
- 查询时只做词典匹配与邻域扩展，不额外调 LLM，保证检索延迟可控。
- 图谱为空或未建时，检索链路自动退化为纯向量混合检索（不影响可用性）。
==============================================================
"""

import os
import sys
import threading
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import GRAPH_ENHANCED_RAG, GRAPH_MAX_HOPS, GRAPH_TOP_K
from models import db, Knowledge, KnowledgeTriple

# 实体关系抽取系统提示词
EXTRACT_SYSTEM_PROMPT = (
    "你是景区知识图谱构建器。从给定的知识文本中抽取实体关系三元组 (头实体, 关系, 尾实体)。\n"
    "头实体/尾实体必须是具体实体：景点名（如 灵山大佛、梵宫、九龙灌浴、祥符禅寺、拈花湾）、"
    "设施、人物、地点、活动、服务、时间、价格等。\n"
    "关系要简洁，如：位于、属于、包含、门票、开放时间、始建于、相邻、推荐、提供、典故、又称 等。\n"
    "每条关系只表达一个明确事实；不确定或空泛的不要抽取。\n"
    "你只能调用 extract_entity_relations 函数，通过 triples 数组一次性返回所有三元组；"
    "如果文本中没有可抽取的实体关系，返回空数组 []。"
)

# 三元组抽取工具定义（一次返回多条三元组）
TRIPLE_TOOLS: List[Dict] = [{
    "type": "function",
    "function": {
        "name": "extract_entity_relations",
        "description": "从知识文本中抽取实体关系三元组列表",
        "parameters": {
            "type": "object",
            "properties": {
                "triples": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "head": {"type": "string", "description": "头实体（景点/设施/人物/地点等具体名称）"},
                            "relation": {"type": "string", "description": "关系，如 位于/属于/门票/包含/相邻/始建于"},
                            "tail": {"type": "string", "description": "尾实体"},
                        },
                        "required": ["head", "relation", "tail"],
                    },
                },
            },
            "required": ["triples"],
        },
    },
}]

# 单条知识最多保留的三元组数量（防止单条文本抽取爆炸；路线类含 7+ 途经景点，需留足余量）
MAX_TRIPLES_PER_ITEM = 15


class KnowledgeGraph:
    """知识图谱：建图 + 实体链接 + 邻域扩展子图检索"""

    def __init__(self):
        self._lock = threading.Lock()
        self._entity_names: Optional[List[str]] = None

    # -------------------- 实体关系抽取（离线，LLM） --------------------

    def extract_triples(self, text: str) -> List[Dict[str, str]]:
        """调用 LLM 从单条知识文本抽取三元组，返回 [{head, relation, tail}]"""
        from services.llm_service import get_llm_service
        llm = get_llm_service()
        if not llm.is_configured() or not text:
            return []

        call = llm.chat_tool_call(
            [
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": f"知识文本：\n{text[:2000]}"},
            ],
            TRIPLE_TOOLS,
            # 注意：DashScope 兼容层不支持旧式字符串函数名强制，
            # 必须用 OpenAI 对象格式 {"type": "function", "function": {"name": ...}}
            tool_choice={"type": "function", "function": {"name": "extract_entity_relations"}},
        )
        if not call or call.get("name") != "extract_entity_relations":
            return []

        args = call.get("arguments") or {}
        raw = args.get("triples")
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return []

        triples: List[Dict[str, str]] = []
        if isinstance(raw, list):
            for item in raw[:MAX_TRIPLES_PER_ITEM]:
                if not isinstance(item, dict):
                    continue
                h, r, t = item.get("head"), item.get("relation"), item.get("tail")
                if h and r and t:
                    triples.append({
                        "head": str(h).strip()[:120],
                        "relation": str(r).strip()[:60],
                        "tail": str(t).strip()[:120],
                    })
        return triples

    # -------------------- 建图（离线，幂等） --------------------

    def build(self, limit: Optional[int] = None) -> int:
        """
        遍历知识库，为每条知识抽取三元组并持久化（幂等：先清旧三元组再写）。
        返回新写入三元组总数。
        """
        from services.llm_service import get_llm_service
        llm = get_llm_service()
        if not llm.is_configured():
            print("[Graph] 大模型未配置，跳过建图")
            return 0

        items = (Knowledge.query
                 .filter_by(is_active=True)
                 .order_by(Knowledge.id)
                 .all())
        if limit:
            items = items[:limit]

        total = 0
        for k in items:
            text = f"标题：{k.title}\n内容：{k.content}"
            try:
                triples = self.extract_triples(text)
            except Exception as e:
                print(f"[Graph] 抽取失败 knowledge#{k.id}：{e}")
                continue
            if not triples:
                continue

            try:
                # 幂等：清除该知识的旧三元组后重写
                KnowledgeTriple.query.filter_by(knowledge_id=k.id).delete()
                for tp in triples:
                    db.session.add(KnowledgeTriple(
                        knowledge_id=k.id,
                        head=tp["head"],
                        relation=tp["relation"],
                        tail=tp["tail"],
                    ))
                db.session.commit()
                total += len(triples)
                print(f"[Graph] knowledge#{k.id} 抽取 {len(triples)} 条三元组")
            except Exception as e:
                print(f"[Graph] 写入失败 knowledge#{k.id}：{e}")
                db.session.rollback()

        # 实体词典缓存失效，下次检索时重建
        with self._lock:
            self._entity_names = None
        print(f"[Graph] 建图完成，共 {total} 条三元组")
        return total

    # -------------------- 实体链接（词典最长匹配，无 LLM） --------------------

    def _load_entity_names(self) -> List[str]:
        """加载图谱中全部出现过的实体名（去重，按长度降序便于最长匹配）"""
        with self._lock:
            if self._entity_names is not None:
                return self._entity_names
            names = set()
            try:
                rows = KnowledgeTriple.query.filter_by(is_active=True).all()
                for r in rows:
                    if r.head:
                        names.add(r.head)
                    if r.tail:
                        names.add(r.tail)
            except Exception as e:
                print(f"[Graph] 实体词典加载失败：{e}")
            # 按长度降序：查询时优先命中更长、更具体的实体名
            self._entity_names = sorted(names, key=len, reverse=True)
            return self._entity_names

    def link_entities(self, query: str) -> List[str]:
        """从查询文本中匹配已知实体（最长匹配，去重）"""
        if not query:
            return []
        matched = [n for n in self._load_entity_names() if n in query]
        return matched[:8]

    # -------------------- 子图检索（在线，邻域扩展） --------------------

    def retrieve_context(self, query: str,
                         top_k: Optional[int] = None,
                         max_hops: Optional[int] = None) -> str:
        """
        实体链接 + 邻域扩展，返回关联三元组文本（补充向量检索结果）。
        图谱未启用或未建时返回空串。
        """
        if not GRAPH_ENHANCED_RAG:
            return ""
        top_k = top_k or GRAPH_TOP_K
        max_hops = max_hops if max_hops is not None else GRAPH_MAX_HOPS

        try:
            entities = self.link_entities(query)
            if not entities:
                return ""

            frontier = set(entities)
            expanded = set(entities)
            triples: List[KnowledgeTriple] = []
            seen = set()

            for _ in range(max(1, max_hops)):
                if not frontier:
                    break
                rows = (KnowledgeTriple.query
                        .filter(
                            KnowledgeTriple.is_active.is_(True),
                            db.or_(
                                KnowledgeTriple.head.in_(frontier),
                                KnowledgeTriple.tail.in_(frontier),
                            ),
                        )
                        .limit(200)
                        .all())
                new_frontier = set()
                for r in rows:
                    key = (r.head, r.relation, r.tail)
                    if key in seen:
                        continue
                    seen.add(key)
                    triples.append(r)
                    new_frontier.add(r.head)
                    new_frontier.add(r.tail)
                frontier = new_frontier - expanded
                expanded |= new_frontier

            if not triples:
                return ""

            triples = triples[:top_k]
            lines = [f"「{t.head}」—{t.relation}—「{t.tail}」" for t in triples]
            return "【知识图谱关联】\n" + "\n".join(lines)
        except Exception as e:
            print(f"[Graph] 子图检索失败：{e}")
            return ""


# ======================== 后台建图入口 ========================

def build_graph_async(app, limit: Optional[int] = None) -> int:
    """建图任务写入持久化队列（进程重启不丢、失败退避重试），由 job worker 后台执行。
    保留 app 形参以兼容既有调用方；返回任务 id。"""
    from services.job_service import enqueue
    return enqueue("graph_build", {"limit": limit})


def _handle_graph_build(payload: dict) -> dict:
    """job worker 回调：执行建图，返回结果摘要（已在 app 上下文中）"""
    count = get_knowledge_graph().build(limit=payload.get("limit"))
    return {"triples": count}


# ======================== 全局单例 ========================
_knowledge_graph = None


def get_knowledge_graph() -> KnowledgeGraph:
    """获取知识图谱单例"""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph


# 注册到持久化任务队列（worker 消费 graph_build 任务时回调）
from services.job_service import register_handler
register_handler("graph_build", _handle_graph_build)