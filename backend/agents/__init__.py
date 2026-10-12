"""
==============================================================
多 Agent 包（严格两级 Orchestrator-Workers）
==============================================================
对外统一入口 run_agent_stream —— 与旧单 Agent 签名完全一致，chat_ws 调用零改动。

结构：
    base.py        通用 ReAct 循环 + 子 Agent 基类 + 回退
    rag_agent.py   检索专员（search_knowledge）
    trip_agent.py  行程专员（get_route_recommendation + get_spot_info）
    registry.py    子 Agent 注册 + 子 Agent 工具 schema + 执行器
    orchestrator.py 总调度（只挂子 Agent 工具，严格两级）
==============================================================
"""

from agents.orchestrator import run_orchestrator_stream, ORCHESTRATOR_PROMPT

# 向后兼容：与旧 services.agent_service.run_agent_stream 同名同签名
run_agent_stream = run_orchestrator_stream

__all__ = ["run_agent_stream", "ORCHESTRATOR_PROMPT"]