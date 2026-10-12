"""
==============================================================
Agent 注册表（registry）
==============================================================
管理专职 Agent 的注册，并把子 Agent 暴露为 Orchestrator 的工具（Agent-as-Tool）。

严格两级：
    Orchestrator 只挂子 Agent 工具（consult_retrieval_specialist / consult_trip_specialist），
    领域工具（search_knowledge / get_route_recommendation / get_spot_info）只存在于各子 Agent 内部。
==============================================================
"""

from typing import Dict, List, Any

from agents.base import BaseAgent


# 子 Agent 单例（惰性构建，避免首次 import 就初始化 LLM 依赖）
_AGENTS: Dict[str, BaseAgent] = {}

# 子 Agent 工具名（暴露给 Orchestrator）→ 注册 key
_AGENT_TOOL_KEY = {
    "consult_retrieval_specialist": "rag",
    "consult_trip_specialist": "trip",
}


def _ensure_agents() -> None:
    if _AGENTS:
        return
    from agents.rag_agent import build_rag_agent
    from agents.trip_agent import build_trip_agent
    _AGENTS["rag"] = build_rag_agent()
    _AGENTS["trip"] = build_trip_agent()


def execute_subagent(name: str, arguments: Dict[str, Any], trace=None) -> str:
    """
    Orchestrator 的工具执行器：派发任务给子 Agent，返回其观察结果（文本）。

    子 Agent 不得反向调用 Orchestrator（注册表只提供单向依赖），
    且子 Agent 异常只会以文本形式回传给 Orchestrator 自行处理。
    trace 由 Orchestrator 透传，使子 Agent 内部工具 span 挂在同一 trace 下。
    """
    _ensure_agents()
    key = _AGENT_TOOL_KEY.get(name, name)
    agent = _AGENTS.get(key)
    if not agent:
        return f"错误：未知专员 {name}"

    # 统一从多个可能的入参键中提取任务描述
    task = str(
        arguments.get("query")
        or arguments.get("request")
        or arguments.get("question")
        or ""
    ).strip()
    if not task:
        return f"[{agent.label}] 任务为空，无法执行。"

    return agent.run(task, trace=trace)


def get_orchestrator_tools() -> List[Dict[str, Any]]:
    """
    供 Orchestrator 使用的工具定义（即子 Agent 工具）。
    严格两级：这里不包含任何领域工具，只有两个子 Agent 入口。
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "consult_retrieval_specialist",
                "description": (
                    "派发任务给知识检索专员。适用于景区知识性问题：门票价格、交通、开放时间、"
                    "景点讲解、历史文化、常见问题（FAQ）等。返回检索专员整理好的知识结论。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "需要检索的问题或查询内容",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "consult_trip_specialist",
                "description": (
                    "派发任务给行程/景点专员。适用于：游览路线推荐、行程规划（怎么走/怎么玩/半天一天怎么安排）、"
                    "具体景点/设施的基础信息查询（门票价格、开放时间、位置、看点）。返回整理好的行程或景点信息。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "路线推荐或景点查询需求",
                        },
                    },
                    "required": ["request"],
                },
            },
        },
    ]