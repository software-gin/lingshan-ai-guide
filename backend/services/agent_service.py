"""
==============================================================
Agent 调度层 —— 兼容转发层
==============================================================
多 Agent 架构（严格两级 Orchestrator-Workers）迁移后，本模块保留旧的导入路径，
对外接口 run_agent_stream 现由 agents 包实现（apps.orchestrator），仅做向后兼容转发，
chat_ws 等既有调用方无需改动。

结构（实现详见 agents/ 包）：
    base.py        通用 ReAct 循环 + 子 Agent 基类 + 回退
    rag_agent.py   检索专员（search_knowledge）
    trip_agent.py  行程专员（get_route_recommendation + get_spot_info）
    registry.py    子 Agent 注册 + 子 Agent 工具
    orchestrator.py 总调度（只挂子 Agent 工具，严格两级）
==============================================================
"""

from agents import run_agent_stream
from agents.orchestrator import ORCHESTRATOR_PROMPT

# 兼容旧评测脚本引用（值指向新架构的调度提示词）
AGENT_SYSTEM_PROMPT = ORCHESTRATOR_PROMPT

__all__ = ["run_agent_stream", "AGENT_SYSTEM_PROMPT"]