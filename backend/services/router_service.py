"""
==============================================================
动态路由推理层（Router）
==============================================================
让大模型判断：
1. 是否需要检索知识库（寒暄/闲聊/明确无关时无需检索，直接回答）
2. 需要检索哪个知识分类（faq / scene_intro / history / basic_info / route / all）

这是"小型推理层"的第一步，后续 Agentic RAG（ReAct）会在此基础上复用
function calling 的调度逻辑。
==============================================================
"""

import json
from typing import List, Dict, Any

from services.llm_service import get_llm_service

# 与 rag_service 中 KnowledgeCategory.code 保持一致的知识分类
ALL_CATEGORIES = ["faq", "scene_intro", "history", "basic_info", "route"]

ROUTING_SYSTEM_PROMPT = (
    "你是「灵山胜境景区」AI 导游的检索路由决策器。\n"
    "根据用户问题，判断是否需要检索景区知识库，以及需要检索的知识分类。\n"
    "规则：\n"
    "1. 寒暄、问候、自我介绍、与景区完全无关的闲聊：need_retrieval=false。\n"
    "2. 涉及门票/交通/开放时间/价格/地址电话等：categories 包含 basic_info。\n"
    "3. 涉及景点讲解/建筑/佛像/景观介绍：categories 包含 scene_intro。\n"
    "4. 涉及历史背景/文化/佛教典故/传说故事：categories 包含 history。\n"
    "5. 涉及游览路线/怎么走/怎么玩/行程攻略：categories 包含 route。\n"
    "6. 一般疑问句（怎么/什么/能否/可以吗）：categories 包含 faq。\n"
    "7. 无法确定或问题跨多个分类时：categories 使用 [\"all\"]。\n"
    "你只能调用 route_to_knowledge_base 函数，不要输出其他内容。"
)

ROUTE_TOOLS: List[Dict[str, Any]] = [{
    "type": "function",
    "function": {
        "name": "route_to_knowledge_base",
        "description": "决定检索策略：是否需要检索知识库、检索哪个知识分类",
        "parameters": {
            "type": "object",
            "properties": {
                "need_retrieval": {
                    "type": "boolean",
                    "description": "是否需要检索知识库",
                },
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ALL_CATEGORIES + ["all"],
                    },
                    "description": "需要检索的知识分类列表；跨类或不确定时用 [\"all\"]",
                },
            },
            "required": ["need_retrieval", "categories"],
        },
    },
}]


class KnowledgeRouter:
    """检索路由：让大模型判断检索策略"""

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    def route(self, query: str) -> Dict[str, Any]:
        """
        对用户问题做检索路由决策。

        返回：
            {"need_retrieval": bool, "categories": List[str]}
        任何异常都回退为全量检索（保证不丢失能力）。
        """
        fallback = {"need_retrieval": True, "categories": ["all"]}

        llm = self._get_llm()
        if not llm.is_configured():
            print("[Router] 大模型未配置，回退全量检索")
            return fallback

        try:
            call = llm.chat_tool_call(
                [
                    {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                ROUTE_TOOLS,
            )
            if not call or call.get("name") != "route_to_knowledge_base":
                print("[Router] 未触发路由函数，回退全量检索")
                return fallback

            args = call.get("arguments") or {}
            need_retrieval = bool(args.get("need_retrieval", True))

            raw_cats = args.get("categories") or ["all"]
            if not isinstance(raw_cats, list):
                raw_cats = ["all"]
            valid = set(ALL_CATEGORIES + ["all"])
            categories = [c for c in raw_cats if c in valid]
            if not categories or "all" in categories:
                categories = ["all"]

            return {"need_retrieval": need_retrieval, "categories": categories}
        except Exception as e:
            print(f"[Router] 路由失败，回退全量检索：{e}")
            return fallback


# ======================== 全局单例 ========================
_router = None


def get_router() -> KnowledgeRouter:
    """获取路由单例"""
    global _router
    if _router is None:
        _router = KnowledgeRouter()
    return _router