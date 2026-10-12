"""
==============================================================
多 Agent 基类与通用 ReAct 循环（严格两级架构）
==============================================================
统一抽象：
    react_loop    —— 通用 ReAct 生成器（子 Agent 与 Orchestrator 共用同一套协议）
    BaseAgent     —— 专职 Agent 基类（非流式执行，返回文本观察值，供 Orchestrator 作为工具调用）
    fallback_stream —— LLM 未配置 / 严重异常时的固定 RAG 回退（保证可用性）

协作协议：Agent-as-Tool
    Orchestrator 挂载"子 Agent 工具"，子 Agent 内部挂载"领域工具"；
    子 Agent 一律非流式执行、产出被截断后作为 Orchestrator 的 Observation。
==============================================================
"""

import json
from typing import Generator, List, Dict, Any, Callable, Optional

from services.llm_service import get_llm_service

# 子 Agent 观察值上限：防止观察文本撑爆 Orchestrator 上下文
SUBAGENT_OBSERVATION_MAX_CHARS = 1500


def react_loop(messages: List[Dict[str, Any]],
               tools: List[Dict[str, Any]],
               max_rounds: int,
               executor: Callable[[str, Dict[str, Any]], str],
               label: str = "Agent",
               on_status: Optional[Callable[[str], None]] = None,
               context: Optional[Any] = None) -> Generator[str, None, None]:
    """
    通用 ReAct 循环（流式产出文本增量）。

    参数：
        messages:   消息列表（已在头部包好 system + history + user）
        tools:      工具定义（OpenAI 格式，子 Agent 为领域工具子集，Orchestrator 为子 Agent 工具）
        max_rounds: 最大轮数；<=0 时不调用工具，仅做一次直接生成
        executor:   工具执行器，(name, arguments) -> 观察文本
        label:      日志与状态前缀
        on_status:  可选状态回调 fn(str)

    行为：
        每轮调一次 chat_with_tools_stream，yield 文本增量；聚合 tool_calls；
        无调用即返回（本轮流式输出即最终回答）；有调用则回填 assistant + tool 观察，进入下一轮；
        超过 max_rounds 仍未收敛时，追加强制收敛指令并一次性生成。
    """
    llm = get_llm_service()

    if max_rounds <= 0:
        yield from llm.chat_stream(messages)
        return

    for _round in range(max_rounds):
        calls: List[Dict[str, Any]] = []
        for event in llm.chat_with_tools_stream(messages, tools):
            if event["type"] == "content":
                yield event["text"]
            elif event["type"] == "tool_calls":
                calls = event["calls"]

        if not calls:
            # 未触发工具：本轮流式输出即为最终回答
            return

        # 回填 assistant 工具调用消息（协议要求 content 传空串）
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {
                        "name": c["name"],
                        "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                    },
                }
                for c in calls
            ],
        })

        # 执行工具并回填观察结果（Observation）
        for c in calls:
            if on_status:
                try:
                    on_status(f"正在执行：{c['name']}...")
                except Exception:
                    pass
            print(f"[{label}] 调用工具 {c['name']}，参数：{c['arguments']}")
            observation = executor(c["name"], c["arguments"])
            print(f"[{label}] 工具 {c['name']} 观察：{str(observation)[:120]}")
            # 可观测性：记录工具调用与观察摘要（trace 存在时）
            if context is not None:
                try:
                    context.span(
                        f"tool.{c['name']}",
                        as_type="tool",
                        input={"arguments": c["arguments"]},
                        output=str(observation)[:500],
                    )
                except Exception:
                    pass
            messages.append({
                "role": "tool",
                "tool_call_id": c["id"],
                "content": observation,
            })
        # 进入下一轮：模型基于观察结果继续思考或给出最终回答

    # 超出最大轮数：强制收敛，基于已获取的信息生成最终回答
    print(f"[{label}] 已达最大轮数 {max_rounds}，强制收敛")
    messages.append({
        "role": "system",
        "content": "已达工具调用轮数上限。请立即基于以上已获取的信息直接回答，不要再调用工具。",
    })
    yield from llm.chat_stream(messages)


class BaseAgent:
    """
    专职 Agent（子 Agent）基类：非流式执行 ReAct，返回最终文本。

    Orchestrator 通过 execute_subagent() 调用 run()，其返回值即该子 Agent 的观察结果。
    子 Agent 的工具由 tool_registry 提供（领域工具子集），通过 execute_tool 执行。
    """

    def __init__(self, name: str, system_prompt: str, tools: List[Dict[str, Any]],
                 max_rounds: int = 3, label: str = "专员"):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.max_rounds = max_rounds
        self.label = label

    def run(self, query: str, history: Optional[List[Dict[str, str]]] = None,
            trace: Optional[Any] = None) -> str:
        """非流式运行，返回最终文本（作为 Orchestrator 的观察值）。
        trace 由 Orchestrator 透传，使子 Agent 的工具调用 span 挂在同一 trace 下。"""
        from services.tool_registry import execute_tool

        llm = get_llm_service()
        if not llm.is_configured():
            return f"[{self.label}] 大模型未配置，无法执行。"

        query = (query or "").strip()
        if not query:
            return f"[{self.label}] 任务为空。"

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            *(history or []),
            {"role": "user", "content": query},
        ]

        try:
            text = "".join(react_loop(
                messages, self.tools, self.max_rounds,
                executor=execute_tool, label=self.label,
                context=trace,  # 透传 trace，子 Agent 内部工具调用也挂到同一链路
            ))
        except Exception as e:
            print(f"[{self.label}] 执行异常：{e}")
            return f"[{self.label}] 执行异常：{e}"

        text = text or f"[{self.label}] 未产出结果。"
        if len(text) > SUBAGENT_OBSERVATION_MAX_CHARS:
            text = text[:SUBAGENT_OBSERVATION_MAX_CHARS] + "…(已截断)"
        return text


def fallback_stream(question: str, personality_section: str = "",
                    history_messages: Optional[List[Dict[str, str]]] = None) -> Generator[str, None, None]:
    """
    回退链路：固定全量检索 + 直接生成（传统 RAG 行为）。
    在大模型未配置或 ReAct 循环严重异常时启用，保证服务可用。
    """
    llm = get_llm_service()
    context = ""
    try:
        from services.rag_service import get_knowledge_processor
        context = get_knowledge_processor().get_knowledge_context(question)
    except Exception as e:
        print(f"[Agent] 回退检索失败：{e}")

    system_prompt = (
        "你是一个专业的灵山胜境景区AI导游。基于知识库上下文回答用户问题，"
        "不要编造事实。回答热情、生动、简短，适合导游讲解风格，用纯自然语言。"
        + (personality_section or "")
    )
    user_content = f"知识库参考信息：\n{context}\n\n用户问题：{question}" if context else question
    yield from llm.chat_stream([
        {"role": "system", "content": system_prompt},
        *(history_messages or []),
        {"role": "user", "content": user_content},
    ])