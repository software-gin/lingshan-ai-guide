"""
==============================================================
行程专员（Trip Agent）
==============================================================
职责：路线推荐与景点基础信息。挂载领域工具子集 ——
    get_route_recommendation（按偏好筛选路线）
    get_spot_info          （景点/设施基础信息，DB 优先 + 向量兜底）
产出：一段清晰的行程/景点信息（供 Orchestrator 组织最终回答）。
==============================================================
"""

from typing import List, Dict, Any

from config import SUBAGENT_MAX_ROUNDS
from services.tool_registry import get_openai_tools
from agents.base import BaseAgent

TRIP_AGENT_PROMPT = """你是「灵山胜境行程/景点专员」。你的任务是围绕用户的路线或景点需求，调用工具获取信息并整理成一段清晰的结论。

## 工作方式：
1. 路线推荐 / 行程规划类：调用 get_route_recommendation，可带偏好（如亲子、文化、自然、祈福、轻松）。
2. 查询具体景点/设施基础信息（门票、开放时间、位置、看点）：调用 get_spot_info。
3. 需要时可在一轮内同时调用多个工具。
4. 汇总工具返回的信息，输出一段完整、有条理的行程或景点说明。

## 硬性要求：
- 只输出工具返回的真实信息，严禁编造具体价格、时间、场次；工具结果中没有的数据要如实说明并建议咨询景区官方。
- 不要输出 JSON、代码块或任何结构化格式，用纯自然语言。
- 你的输出会被主调度（Orchestrator）用于组织最终回答，请确保信息完整、可读。"""


def build_trip_agent() -> BaseAgent:
    tools: List[Dict[str, Any]] = get_openai_tools(
        names=["get_route_recommendation", "get_spot_info"]
    )
    return BaseAgent(
        name="trip",
        system_prompt=TRIP_AGENT_PROMPT,
        tools=tools,
        max_rounds=SUBAGENT_MAX_ROUNDS,
        label="行程专员",
    )