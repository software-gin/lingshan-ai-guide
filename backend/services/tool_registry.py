"""
==============================================================
Agent 工具注册表（Tool Registry）
==============================================================
统一工具标准接口：名称、功能描述、入参 schema（OpenAI function calling 格式）、
执行器。Agent（ReAct）通过 get_openai_tools() 获取工具定义，
通过 execute_tool() 执行工具并获取观察结果（Observation）。

首批工具（第一阶段，按约定控制在 5 个以内）：
1. search_knowledge         知识库检索（支持按知识分类，Agentic RAG 核心）
2. get_route_recommendation 游览路线推荐
3. get_spot_info            景点/票务基础信息查询

扩展方式：调用 register_tool() 注册新工具即可被 Agent 自动发现与调用。
==============================================================
"""

import traceback
import threading
from typing import Callable, Dict, Any, List, Optional

# 与 rag_service 中 KnowledgeCategory.code 保持一致（额外支持 all）
KNOWLEDGE_CATEGORIES = ["faq", "scene_intro", "history", "basic_info", "route", "all"]

# 工具执行并发上限（与 LLM 并发一致，防止本地资源争抢，如精排模型、向量库）
_TOOL_SEMAPHORE = threading.Semaphore(4)
# 工具入参长度上限（防止模型注入超长参数拖垮执行器）
_MAX_ARG_LEN = 2000


class Tool:
    """标准工具定义"""

    def __init__(self, name: str, description: str, parameters: Dict[str, Any],
                 executor: Callable[[Dict[str, Any]], str]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.executor = executor

    def to_openai_schema(self) -> Dict[str, Any]:
        """转为 OpenAI function calling 工具定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ======================== 注册表 ========================
_TOOLS: Dict[str, Tool] = {}


def register_tool(name: str, description: str, parameters: Dict[str, Any],
                  executor: Callable[[Dict[str, Any]], str]) -> None:
    """注册工具（同名覆盖）"""
    _TOOLS[name] = Tool(name, description, parameters, executor)


def get_tool(name: str) -> Optional[Tool]:
    """按名称获取工具"""
    return _TOOLS.get(name)


def get_openai_tools(names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    获取工具的 OpenAI 格式定义（供模型选择调用）。
    names 为空时返回全部工具；否则仅返回指定名称的工具子集（多 Agent 中给子 Agent 用）。
    """
    if names is None:
        return [t.to_openai_schema() for t in _TOOLS.values()]
    return [_TOOLS[n].to_openai_schema() for n in names if n in _TOOLS]


def execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """
    执行工具并返回观察结果（字符串）。
    异常不外抛，返回错误信息供模型自省（ReAct 的 Observation）。
    加并发信号量，防止工具并发过高争抢本地资源（精排/向量库/图谱）。
    """
    tool = _TOOLS.get(name)
    if not tool:
        return f"错误：未知工具 {name}"
    args = arguments or {}
    # 参数长度白名单校验：任何字符串参数超过上限都截断（防御注入）
    for k, v in list(args.items()):
        if isinstance(v, str) and len(v) > _MAX_ARG_LEN:
            args[k] = v[:_MAX_ARG_LEN]
    acquired = _TOOL_SEMAPHORE.acquire(timeout=15)
    if not acquired:
        return f"工具 {name} 执行超时：并发等待资源超过 15s"
    try:
        return tool.executor(args)
    except Exception as e:
        print(f"[Tool] 工具 {name} 执行失败：{e}")
        traceback.print_exc()
        return f"工具执行失败：{e}"
    finally:
        _TOOL_SEMAPHORE.release()


# ======================== 具体工具实现 ========================

def _tool_search_knowledge(args: Dict[str, Any]) -> str:
    """知识库检索（语义+BM25 混合检索，支持按分类过滤）"""
    from services.rag_service import get_knowledge_processor

    query = str(args.get("query") or "").strip()
    if not query:
        return "错误：query 不能为空"

    categories = args.get("categories") or ["all"]
    if not isinstance(categories, list):
        categories = ["all"]
    valid = set(KNOWLEDGE_CATEGORIES)
    categories = [c for c in categories if c in valid] or ["all"]

    try:
        top_k = int(args.get("top_k") or 5)
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, 10))

    results = get_knowledge_processor().search_knowledge(query, top_k=top_k, categories=categories)
    if not results:
        return "知识库中未找到相关内容。可尝试更换关键词再次检索，或基于已有知识如实回答。"

    lines = []
    for i, r in enumerate(results):
        cat = (r.get("metadata") or {}).get("category", "unknown")
        lines.append(f"[{i + 1}]（分类:{cat}）{r['text']}")
    result = "\n\n".join(lines)

    # 知识图谱增强：按查询实体做邻域扩展，补充关联三元组（图谱未建时自动退化为纯检索）
    try:
        from services.graph_service import get_knowledge_graph
        graph_ctx = get_knowledge_graph().retrieve_context(query)
        if graph_ctx:
            result += "\n\n" + graph_ctx
    except Exception as e:
        print(f"[Tool] 图谱增强失败：{e}")

    return result


def _tool_get_route_recommendation(args: Dict[str, Any]) -> str:
    """游览路线推荐（可按偏好筛选）"""
    from services.route_service import get_all_routes, get_routes_by_style, get_routes_by_tags

    preference = str(args.get("preference") or "").strip()
    routes = []
    if preference:
        routes = get_routes_by_style(preference)
        if not routes:
            routes = get_routes_by_tags([preference])
    if not routes:
        routes = get_all_routes()

    if not routes:
        return "暂无可用路线数据。"

    lines = []
    for r in routes[:5]:
        spots = "→".join(s.get("name", "") for s in r.get("spots", []))
        lines.append(
            f"路线{r.get('id')}：《{r.get('title')}》 时长:{r.get('duration', '')} "
            f"风格:{r.get('style', '')} 标签:{','.join(r.get('tags', []))}\n"
            f"  途经：{spots}\n"
            f"  简介：{r.get('description', '')}"
        )
    return "\n\n".join(lines)


def _tool_get_spot_info(args: Dict[str, Any]) -> str:
    """景点/票务基础信息查询（结构化库优先，向量检索兜底）"""
    spot_name = str(args.get("spot_name") or "").strip()
    if not spot_name:
        return "错误：spot_name 不能为空"

    # 1. 优先查结构化知识库（数据库）
    rows = []
    try:
        from models import db, Knowledge
        like = f"%{spot_name}%"
        rows = (Knowledge.query
                .filter(db.or_(Knowledge.title.ilike(like),
                               Knowledge.keywords.ilike(like),
                               Knowledge.tags.ilike(like)))
                .filter(Knowledge.is_active.is_(True))
                .limit(5).all())
    except Exception as e:
        print(f"[Tool] get_spot_info 数据库查询失败，降级向量检索：{e}")

    if rows:
        return "\n\n".join(f"【{k.title}】{k.content}" for k in rows)

    # 2. 兜底：向量库检索
    from services.rag_service import get_knowledge_processor
    results = get_knowledge_processor().search_knowledge(
        spot_name, top_k=3, categories=["basic_info", "scene_intro"])
    if not results:
        return f"知识库中未找到与「{spot_name}」相关的信息。"
    return "\n\n".join(f"[{i + 1}] {r['text']}" for i, r in enumerate(results))


# ======================== 注册首批工具 ========================

def register_default_tools() -> None:
    """注册第一阶段工具集"""
    register_tool(
        name="search_knowledge",
        description=(
            "检索灵山胜境景区知识库（门票、交通、开放时间、景点讲解、历史文化、"
            "常见问题等）。回答景区事实性问题前应优先调用；检索结果不理想时可更换关键词重试。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索查询语句（改写为适合检索的关键词短语）"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": KNOWLEDGE_CATEGORIES},
                    "description": "限定检索的知识分类；跨类或不确定时用 [\"all\"]",
                },
                "top_k": {"type": "integer", "description": "返回片段数量，1-10，默认 5"},
            },
            "required": ["query"],
        },
        executor=_tool_search_knowledge,
    )

    register_tool(
        name="get_route_recommendation",
        description=(
            "获取灵山胜境游览路线推荐，可按游客偏好（如亲子、文化、自然、祈福等）筛选。"
            "路线类问题（怎么走、怎么玩、推荐路线、行程规划）应调用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "preference": {
                    "type": "string",
                    "description": "游客偏好描述，可选；如：亲子、文化、自然、祈福",
                },
            },
            "required": [],
        },
        executor=_tool_get_route_recommendation,
    )

    register_tool(
        name="get_spot_info",
        description="查询指定景点/设施的基础信息（门票价格、开放时间、位置、看点等）。",
        parameters={
            "type": "object",
            "properties": {
                "spot_name": {
                    "type": "string",
                    "description": "景点或设施名称，如：灵山大佛、梵宫、九龙灌浴",
                },
            },
            "required": ["spot_name"],
        },
        executor=_tool_get_spot_info,
    )


register_default_tools()