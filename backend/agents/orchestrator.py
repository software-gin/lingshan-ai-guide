"""
==============================================================
Orchestrator Agent（严格两级调度）
==============================================================
总调度职责（ReAct，只挂子 Agent 工具）：
- 判断能否直接回答（寒暄/常识/闲聊）→ 直接流式回答，不派发
- 景区知识性问题 → 派发 consult_retrieval_specialist（检索专员）
- 路线/行程/景点信息 → 派发 consult_trip_specialist（行程专员）
- 汇总各专员返回的结论，组织成最终的导游式回答

严格两级：Orchestrator 不直接调用任何领域工具（search_knowledge /
get_route_recommendation / get_spot_info），全部通过子 Agent 完成。
==============================================================
"""

from typing import Generator, List, Dict, Any, Callable, Optional

from config import AGENT_MAX_ROUNDS, ROUTER_PRECHECK
from services.llm_service import get_llm_service
from agents.base import react_loop, fallback_stream
from agents.registry import get_orchestrator_tools, execute_subagent


ORCHESTRATOR_PROMPT = """你是灵山胜境景区AI导游的总调度（Orchestrator）。你的职责是理解游客的问题、按需派发任务给专员、并组织出最终的导游式回答。

## 决策规则（先判断类别，再决定是否派发）：
1. 寒暄、问候、常识性闲聊、与景区无关的通用对话 → 直接回答，不派发给任何专员。
2. 景区知识性问题（门票价格、交通、开放时间、景点讲解、历史文化、常见问题）→ 派发给知识检索专员 consult_retrieval_specialist。
3. 路线推荐、行程规划、具体景点/设施基础信息（票价/位置/看点）→ 派发给行程专员 consult_trip_specialist。
4. 复杂问题可一次派发多个专员（并列调用），拿到专员结论后再综合整理。

## 组织回答的要求：
- 基于专员返回的结论回答，不要编造事实；专员结论中没有的具体数据（价格、时间、场次等）严禁编造，应如实告知并建议咨询景区官方。
- 回答热情、生动、有感染力、简短，适合导游讲解风格；用纯自然语言，不要输出 JSON、代码块或任何结构化格式。
- 只回答与灵山胜境景区、拈花湾禅意小镇相关的内容，无关问题友好引导。
- 用户问路线时，直接结合专员返回给出具体方向和步行指引。{personality_section}"""


def run_orchestrator_stream(question: str,
                            personality_section: str = "",
                            history_messages: Optional[List[Dict[str, str]]] = None,
                            memory_context: str = "",
                            on_status: Optional[Callable[[str], None]] = None,
                            trace: Optional[Any] = None) -> Generator[str, None, None]:
    """
    Orchestrator 主循环（流式产出最终回答文本）。
    对外签名与旧 run_agent_stream 完全一致，chat_ws 调用零改动。
    trace 由 chat_ws 透传，使 Orchestrator 及其派发的子 Agent 工具 span 挂在同一 trace 下。
    """
    llm = get_llm_service()

    if not llm.is_configured():
        yield from fallback_stream(question, personality_section, history_messages)
        return

    system_prompt = ORCHESTRATOR_PROMPT.replace("{personality_section}", personality_section or "")

    # 长期记忆（用户画像/历史摘要）注入系统提示，实现个性化服务
    if memory_context and memory_context.strip():
        system_prompt += (
            f"\n\n## 关于这位游客的已知记忆（自然地加以运用，不要刻意复述）：\n{memory_context.strip()}\n"
        )

    # 轻量预判（可配开关）：寒暄/闲聊等无需派发的问题直接流式回答
    if ROUTER_PRECHECK:
        try:
            from services.router_service import get_router
            decision = get_router().route(question)
            if not decision.get("need_retrieval", True):
                print(f"[Orchestrator] 预判无需派发，直接回答：{question[:50]}")
                yield from llm.chat_stream([
                    {"role": "system", "content": system_prompt},
                    *(history_messages or []),
                    {"role": "user", "content": question},
                ])
                return
        except Exception as e:
            print(f"[Orchestrator] 预判路由异常，进入完整调度：{e}")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *(history_messages or []),
        {"role": "user", "content": question},
    ]
    tools = get_orchestrator_tools()

    # 闭包：把 trace 注入子 Agent 执行器，使子 Agent 内部工具 span 贯通
    def _executor(name, arguments):
        return execute_subagent(name, arguments, trace=trace)

    try:
        yield from react_loop(
            messages, tools, max(1, AGENT_MAX_ROUNDS),
            executor=_executor, label="Orchestrator", on_status=on_status,
            context=trace,  # Orchestrator 的工具（子 Agent）调用挂到 trace
        )
    except Exception as e:
        print(f"[Orchestrator] 调度循环异常，回退传统RAG链路：{e}")
        yield from fallback_stream(question, personality_section, history_messages)