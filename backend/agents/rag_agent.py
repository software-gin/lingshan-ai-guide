"""
==============================================================
检索专员（RAG Agent）
==============================================================
职责：景区知识检索。挂载领域工具子集 —— search_knowledge（支持分类过滤、多轮改写重试）。
产出：一段清晰的检索结论（供 Orchestrator 组织最终回答）。
==============================================================
"""

from typing import List, Dict, Any

from config import SUBAGENT_MAX_ROUNDS
from services.tool_registry import get_openai_tools
from agents.base import BaseAgent

RAG_AGENT_PROMPT = """你是「灵山胜境景区知识检索专员」。你的任务是围绕用户的问题检索知识库，并把检索到的知识整理成一段清晰、可据以回答的结论。

## 工作方式：
1. 先把任务改写为适合检索的关键词查询，调用 search_knowledge 检索。
2. 按问题类型选择知识分类（faq/scene_intro/history/basic_info/route），不确定时用 ["all"]。
3. 检索结果不理想时，更换关键词或分类再检索（可多轮）。
4. 汇总检索到的所有知识，输出一段完整、有条理的检索结论。

## 硬性要求：
- 只输出检索到的真实知识，严禁编造；知识库里没有的具体数据（价格、时间、场次等）必须如实说明"知识库未收录"。
- 不要输出 JSON、代码块或任何结构化格式，用纯自然语言。
- 你的输出会被主调度（Orchestrator）用于组织最终回答，请确保信息完整、可读。"""


def build_rag_agent() -> BaseAgent:
    tools: List[Dict[str, Any]] = get_openai_tools(names=["search_knowledge"])
    return BaseAgent(
        name="rag",
        system_prompt=RAG_AGENT_PROMPT,
        tools=tools,
        max_rounds=SUBAGENT_MAX_ROUNDS,
        label="检索专员",
    )