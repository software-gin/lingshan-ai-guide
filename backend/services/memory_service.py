"""
==============================================================
memoryAgent —— 用户记忆管理服务
==============================================================
三类记忆：
1. 短期记忆（会话内）：按 session_id 从 ChatLog 加载最近多轮对话，
   注入上下文实现多轮连贯对话（窗口默认 10-20 轮，见 MEMORY_SHORT_TERM_TURNS）。
2. 长期摘要记忆：会话结束后，LLM 将历史对话压缩成关键信息摘要，
   向量化存入独立 Chroma 集合 + SQLite（UserMemory 表）持久化；
   下次对话按语义相关性召回，实现跨会话记忆。
3. 用户画像/偏好记忆：从对话中抽取用户偏好、习惯、常用需求
   （如"带小孩出游""对佛教文化感兴趣"），对话时注入实现个性化服务。

合规设计（用户可控）：
- 仅存业务相关信息（偏好/习惯），不存身份证、支付等敏感数据
- 提供查看与一键清除接口（见 user_routes /api/user/memory）
- 向量化为增量更新：仅对新压缩的记忆做 embed，不全量重算
==============================================================
"""

import os
import sys
import json
import time
import uuid
import threading
import math
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb

from config import CHROMA_PERSIST_DIR, MEMORY_SHORT_TERM_TURNS, MEMORY_RECALL_TOP_K
from models import db, ChatLog, UserMemory

MEMORY_COLLECTION_NAME = "lingshan_user_memory"

# 长期记忆压缩的系统提示词
SUMMARY_SYSTEM_PROMPT = (
    "你是用户记忆压缩器。将一段景区AI导游与游客的对话历史压缩为简洁的关键信息摘要，"
    "只保留：游客关心的景点/主题、出行人物构成（如亲子/老人/团队）、"
    "表达的偏好与需求（如想看表演/想走轻松路线/预算有限）。"
    "用第三人称陈述句输出，不超过150字，不要任何解释或格式符号。"
)

PROFILE_SYSTEM_PROMPT = (
    "你是用户画像抽取器。从游客与景区AI导游的对话中抽取用户的偏好、习惯、常用需求。\n"
    "只抽取对话中明确体现的信息，每条一句话，最多5条，用换行分隔，不要编号和解释。\n"
    "示例格式：\n带孩子出游，偏好互动性强的景点\n对佛教历史文化感兴趣\n"
    "如果对话中没有可抽取的偏好信息，只输出：无"
)

# 敏感信息黑名单：命中则不入库（合规边界）
SENSITIVE_KEYWORDS = ["身份证", "护照", "银行卡", "支付密码", "手机号", "家庭住址", "信用卡"]

# 记忆衰减半衰期（天）：超过此时间的记忆权重降为原来的 1/e ≈ 37%
MEMORY_DECAY_HALF_LIFE_DAYS = 30.0


def _char_jaccard(a: str, b: str) -> float:
    """字符级 Jaccard 相似度（用于快速粗筛）"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _same_topic(a: str, b: str) -> bool:
    """
    快速粗筛同主题（字符 Jaccard > 0.3）。
    精确冲突检测由 _embedding_similarity 完成（见 _is_conflicting）。
    """
    return _char_jaccard(a, b) > 0.3


def _cosine_sim(v1, v2) -> float:
    """余弦相似度"""
    import numpy as np
    a, b = np.array(v1), np.array(v2)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class MemoryAgent:
    """记忆管理 Agent：短期记忆加载 / 长期记忆压缩与召回 / 用户画像"""

    def __init__(self):
        self._client = None
        self._collection = None
        self._embedding = None
        self._lock = threading.Lock()

    # -------------------- 基础设施（懒加载） --------------------

    def _get_infra(self):
        """懒加载向量库基础设施（与知识库共用 Chroma client 与 embedding 模型）"""
        if self._collection is not None:
            return self._client, self._collection, self._embedding
        with self._lock:
            if self._collection is not None:
                return self._client, self._collection, self._embedding
            try:
                from services.rag_service import get_knowledge_processor
                vector_db = get_knowledge_processor().vector_db
                if vector_db.client is not None:
                    self._client = vector_db.client
                else:
                    self._client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
                self._embedding = vector_db.embedding
            except Exception as e:
                print(f"[Memory] 复用知识库基础设施失败，独立初始化：{e}")
                self._client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
                from services.rag_service import SemanticEmbedding
                self._embedding = SemanticEmbedding()

            try:
                self._collection = self._client.get_collection(MEMORY_COLLECTION_NAME)
            except Exception:
                self._collection = self._client.create_collection(
                    name=MEMORY_COLLECTION_NAME,
                    metadata={"description": "用户长期记忆（memoryAgent）"}
                )
                print(f"[Memory] 创建记忆向量集：{MEMORY_COLLECTION_NAME}")
        return self._client, self._collection, self._embedding

    def _embed(self, text: str):
        _, _, embedding = self._get_infra()
        return embedding.embed(text)

    def _is_safe(self, text: str) -> bool:
        """合规检查：不含敏感个人信息才允许入库"""
        return not any(kw in text for kw in SENSITIVE_KEYWORDS)

    def _find_conflicting_profiles(self, user_id: int, content: str,
                                    collection, threshold: float = 0.70):
        """
        基于 embedding 余弦相似度查找与 content 同主题的已有 profile（用于冲突覆盖）。
        返回需覆盖的 UserMemory 列表（相似度 > threshold）。
        """
        try:
            existing = (UserMemory.query
                        .filter_by(user_id=user_id or 0, memory_type="profile", is_active=True)
                        .all())
            if not existing:
                return []
            new_vec = self._embed(content)
            conflicts = []
            for old in existing:
                # 从 Chroma 取已有 profile 的 embedding
                try:
                    res = collection.get(ids=[old.vector_id], include=["embeddings"])
                    if res and res.get("embeddings") and res["embeddings"][0]:
                        old_vec = res["embeddings"][0]
                        sim = _cosine_sim(new_vec, old_vec)
                        if sim > threshold:
                            conflicts.append(old)
                except Exception:
                    # 取不到 embedding 时退化为字符粗筛
                    if _same_topic(old.content, content):
                        conflicts.append(old)
            return conflicts
        except Exception as e:
            print(f"[Memory] 冲突检测异常，降级为不合并：{e}")
            return []

    # -------------------- 1. 短期记忆（会话内多轮） --------------------

    def get_short_term_messages(self, session_id: str, max_turns: int = None) -> list:
        """
        加载指定会话的最近对话（时间正序），构建为多轮消息列表。

        返回：
            [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}, ...]
        """
        if not session_id:
            return []
        if max_turns is None:
            max_turns = MEMORY_SHORT_TERM_TURNS
        try:
            logs = (ChatLog.query
                    .filter_by(session_id=session_id)
                    .order_by(ChatLog.question_time.desc(), ChatLog.id.desc())
                    .limit(max_turns)
                    .all())
            logs.reverse()  # 时间正序
            messages = []
            for log in logs:
                if log.question_text:
                    messages.append({"role": "user", "content": log.question_text})
                if log.answer_text:
                    messages.append({"role": "assistant", "content": log.answer_text})
            return messages
        except Exception as e:
            print(f"[Memory] 加载短期记忆失败：{e}")
            return []

    # -------------------- 2. 长期记忆召回 --------------------

    def recall_long_term(self, user_id: int, query: str, top_k: int = None) -> str:
        """
        按语义相关性召回该用户的长期记忆（摘要+画像），拼接为上下文文本。
        增强：按 created_at 做指数时间衰减，越新的记忆权重越高；
        最终排序分数 = 语义相似度 * 时间衰减因子。
        """
        if top_k is None:
            top_k = MEMORY_RECALL_TOP_K
        try:
            _, collection, _ = self._get_infra()
            if collection.count() == 0:
                return ""
            query_vector = self._embed(query)
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k * 3, 15),  # 多取一些做衰减重排
                where={"user_id": {"$eq": int(user_id)}},
                include=["documents", "metadatas", "distances"],
            )
            if not results or not results.get("ids") or not results["ids"][0]:
                return ""

            now = time.time()
            half_life_sec = MEMORY_DECAY_HALF_LIFE_DAYS * 86400
            scored = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                mtype = meta.get("memory_type", "fact")
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                if distance > 1.2:  # 相关性阈值：太远的不注入，避免噪声
                    continue
                # 时间衰减：越新权重越高（半衰期 30 天）
                created_at = meta.get("created_at")
                if created_at:
                    age_sec = max(0, now - float(created_at))
                    decay = math.exp(-age_sec / half_life_sec)
                else:
                    decay = 1.0  # 老数据无时间戳，不衰减
                # 语义相似度 = 1 - distance（Chroma 距离越小越相关）
                similarity = max(0.0, 1.0 - distance)
                final_score = similarity * decay
                content = results["documents"][0][i]
                label = {"summary": "历史对话摘要", "profile": "用户偏好", "fact": "已知信息"}.get(mtype, "已知信息")
                scored.append((final_score, f"（{label}）{content}"))

            # 按最终分数降序，取 top_k
            scored.sort(key=lambda x: x[0], reverse=True)
            parts = [text for _, text in scored[:top_k]]
            return "\n".join(parts)
        except Exception as e:
            print(f"[Memory] 长期记忆召回失败：{e}")
            return ""

    # -------------------- 3. 会话结束压缩（memoryAgent 核心动作） --------------------

    def compress_session(self, user_id: int, session_id: str) -> bool:
        """
        会话结束后压缩记忆（建议在后台线程调用）：
        1. 加载本会话全部对话，轮数不足(2轮)则跳过
        2. 去重：该会话已生成过摘要则跳过
        3. LLM 压缩会话摘要（summary）+ 抽取用户偏好（profile）
        4. 合规过滤 → SQLite 持久化 → 向量化入库（增量）
        """
        try:
            logs = ChatLog.query.filter_by(session_id=session_id).all()
            if len(logs) < 2:
                return False

            # 去重：该会话已压缩过
            exists = UserMemory.query.filter_by(
                source_session_id=session_id, memory_type="summary").first()
            if exists:
                print(f"[Memory] 会话 {session_id} 已压缩过，跳过")
                return False

            # 拼接对话历史文本
            dialogue_lines = []
            for log in sorted(logs, key=lambda x: (x.question_time, x.id)):
                dialogue_lines.append(f"游客：{log.question_text}")
                dialogue_lines.append(f"导游：{log.answer_text}")
            dialogue_text = "\n".join(dialogue_lines)[:6000]  # 截断防超长

            from services.llm_service import get_llm_service
            llm = get_llm_service()
            if not llm.is_configured():
                print("[Memory] 大模型未配置，跳过记忆压缩")
                return False

            # 3.1 会话摘要
            summary = llm.chat([
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"对话历史：\n{dialogue_text}"},
            ])
            summary = (summary or "").strip()

            # 3.2 用户偏好抽取
            profile = llm.chat([
                {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
                {"role": "user", "content": f"对话历史：\n{dialogue_text}"},
            ])
            profile = (profile or "").strip()

            saved = []
            if summary and self._is_safe(summary):
                saved.append(("summary", summary))
            # profile 按行拆分为独立偏好，便于冲突合并与精确召回
            if profile and profile != "无" and self._is_safe(profile):
                for line in profile.split("\n"):
                    line = line.strip()
                    if line and self._is_safe(line):
                        saved.append(("profile", line))

            if not saved:
                print(f"[Memory] 会话 {session_id} 无有效记忆内容")
                return False

            # 3.3 SQLite 持久化 + 冲突合并（profile 同主题以新覆盖旧）
            _, collection, _ = self._get_infra()

            for mtype, content in saved:
                # profile 冲突合并：embedding 相似度 > 0.7 的旧记忆软删除 + 删除向量
                if mtype == "profile":
                    for old in self._find_conflicting_profiles(user_id, content, collection):
                        old.is_active = False
                        try:
                            collection.delete(ids=[old.vector_id])
                        except Exception:
                            pass
                        print(f"[Memory] 偏好冲突覆盖：旧='{old.content[:30]}' → 新='{content[:30]}'")

                mem = UserMemory(
                    user_id=user_id or 0,
                    memory_type=mtype,
                    content=content,
                    source_session_id=session_id or "",
                )
                db.session.add(mem)
                db.session.commit()
                # 3.4 增量向量化入库
                try:
                    vector = self._embed(content)
                    collection.add(
                        ids=[mem.vector_id],
                        embeddings=[vector],
                        documents=[content],
                        metadatas=[{
                            "user_id": mem.user_id,
                            "memory_type": mtype,
                            "source_session_id": session_id or "",
                            "created_at": mem.created_at.timestamp() if mem.created_at else time.time(),
                        }],
                    )
                except Exception as ve:
                    print(f"[Memory] 记忆向量化入库失败（不影响持久化）：{ve}")

            print(f"[Memory] 会话 {session_id} 压缩完成，新增 {len(saved)} 条记忆")
            return True
        except Exception as e:
            print(f"[Memory] 记忆压缩失败：{e}")
            db.session.rollback()
            return False

    # -------------------- 3.5 主动写入（Agent/用户显式记忆） --------------------

    def add_fact(self, user_id: int, content: str, memory_type: str = "fact",
                 source_session_id: str = "") -> bool:
        """
        主动写入一条记忆（无需等待会话结束压缩）。
        适用场景：
        - 用户显式说"记住我喜欢素食"
        - Agent 判断某信息值得持久化（如用户明确的偏好/需求）
        - fact 类型用于关键事实，profile 类型用于偏好（会触发冲突合并）
        """
        content = (content or "").strip()
        if not content or not self._is_safe(content):
            return False
        try:
            _, collection, _ = self._get_infra()
            # profile 类型用 embedding 相似度做冲突合并
            if memory_type == "profile":
                for old in self._find_conflicting_profiles(user_id, content, collection):
                    old.is_active = False
                    try:
                        collection.delete(ids=[old.vector_id])
                    except Exception:
                        pass

            mem = UserMemory(
                user_id=user_id or 0,
                memory_type=memory_type,
                content=content,
                source_session_id=source_session_id or "",
            )
            db.session.add(mem)
            db.session.commit()
            # 向量化入库
            try:
                vector = self._embed(content)
                collection.add(
                    ids=[mem.vector_id],
                    embeddings=[vector],
                    documents=[content],
                    metadatas=[{
                        "user_id": mem.user_id,
                        "memory_type": memory_type,
                        "source_session_id": source_session_id or "",
                        "created_at": mem.created_at.timestamp() if mem.created_at else time.time(),
                    }],
                )
            except Exception as ve:
                print(f"[Memory] 主动写入向量化失败（不影响持久化）：{ve}")
            print(f"[Memory] 主动写入 {memory_type}：{content[:50]}")
            return True
        except Exception as e:
            print(f"[Memory] 主动写入失败：{e}")
            db.session.rollback()
            return False

    # -------------------- 4. 用户可控（合规：查看/清除） --------------------

    def get_user_memories(self, user_id: int) -> list:
        """查看用户全部长期记忆"""
        try:
            mems = (UserMemory.query
                    .filter_by(user_id=user_id, is_active=True)
                    .order_by(UserMemory.created_at.desc())
                    .limit(100)
                    .all())
            return [m.to_dict() for m in mems]
        except Exception as e:
            print(f"[Memory] 查询用户记忆失败：{e}")
            return []

    def clear_user_memories(self, user_id: int) -> int:
        """一键清除用户全部长期记忆（软删除 SQLite + 物理删除向量），返回清除条数"""
        try:
            mems = UserMemory.query.filter_by(user_id=user_id, is_active=True).all()
            if not mems:
                return 0
            ids = [m.vector_id for m in mems]
            for m in mems:
                m.is_active = False
            db.session.commit()
            try:
                _, collection, _ = self._get_infra()
                collection.delete(ids=ids)
            except Exception as ve:
                print(f"[Memory] 向量删除失败（SQLite 已软删除）：{ve}")
            return len(mems)
        except Exception as e:
            print(f"[Memory] 清除用户记忆失败：{e}")
            db.session.rollback()
            return 0


# ======================== 后台压缩入口 ========================

def compress_session_async(app, user_id: int, session_id: str) -> Optional[int]:
    """记忆压缩任务写入持久化队列（进程重启不丢、失败退避重试），由 job worker 后台执行。
    保留 app 形参以兼容既有调用方；返回任务 id（无 session_id 时返回 None）。"""
    if not session_id:
        return None
    from services.job_service import enqueue
    return enqueue("memory_compress", {"user_id": user_id, "session_id": session_id})


def _handle_memory_compress(payload: dict) -> None:
    """job worker 回调：执行会话记忆压缩（已在 app 上下文中）"""
    get_memory_agent().compress_session(payload["user_id"], payload["session_id"])


# ======================== 全局单例 ========================
_memory_agent = None


def get_memory_agent() -> MemoryAgent:
    """获取 memoryAgent 单例"""
    global _memory_agent
    if _memory_agent is None:
        _memory_agent = MemoryAgent()
    return _memory_agent


# 注册到持久化任务队列（worker 消费 memory_compress 任务时回调）
from services.job_service import register_handler
register_handler("memory_compress", _handle_memory_compress)