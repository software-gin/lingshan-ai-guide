"""
==============================================================
RAG知识库检索服务模块
功能：文档切片 -> 向量化 -> ChromaDB存储 -> 语义检索
==============================================================
"""

import os
import re
import hashlib
import threading
from typing import List, Dict, Any

# ===== 限制 PyTorch CPU 线程数，避免跟 TTS / LiveTalking 争抢 CPU =====
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# BM25 依赖
import jieba
from rank_bm25 import BM25Okapi

# 语义嵌入模型（text2vec-base-chinese）
from sentence_transformers import SentenceTransformer

# 导入配置
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import KOWLEDGE_DIR, CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME, CHROMA_TOP_K

# 知识分类关键词映射
CATEGORY_KEYWORDS = {
    "scene_intro": ["景点", "讲解", "介绍", "景观", "建筑", "佛像", "大佛", "梵宫", "坛城", "塔", "禅寺", "精舍", "广场", "喷泉", "雕塑"],
    "history": ["历史", "文化", "古代", "朝代", "佛教", "传统", "习俗", "典故", "由来", "传说", "故事", "起源"],
    "basic_info": ["门票", "交通", "停车", "开放时间", "价格", "门票价格", "游玩时间", "费用", "地址", "电话", "联系"],
    "route": ["路线", "行程", "攻略", "游览", "推荐路线", "游玩顺序", "最佳路线"],
    "faq": ["如何", "怎么", "什么", "吗", "?", "？", "请问", "能否", "可以"]
}

def _detect_category(text: str) -> str:
    """根据文本内容自动检测知识分类"""
    scores = {}
    for cat_code, keywords in CATEGORY_KEYWORDS.items():
        scores[cat_code] = sum(1 for kw in keywords if kw in text)
    
    detected = max(scores, key=scores.get)
    if scores[detected] == 0:
        return "basic_info"
    return detected


def _detect_file_category(filename: str) -> str:
    """根据文件名检测知识分类"""
    lower_name = filename.lower()
    
    if any(kw in lower_name for kw in ["景点", "景区", "讲解", "介绍", "景观"]):
        return "scene_intro"
    elif any(kw in lower_name for kw in ["历史", "文化", "由来", "传说"]):
        return "history"
    elif any(kw in lower_name for kw in ["路线", "行程", "攻略", "游览"]):
        return "route"
    elif any(kw in lower_name for kw in ["问答", "faq", "问题"]):
        return "faq"
    else:
        return "basic_info"


def _detect_category_from_text(text: str, filename_hint: str = "") -> str:
    """
    根据文本内容和文件名线索检测知识分类
    优先使用文本内容，文件名为辅助
    """
    # 1. 从文本内容检测（主要依据）
    text_scores = {}
    for cat_code, keywords in CATEGORY_KEYWORDS.items():
        text_scores[cat_code] = sum(1 for kw in keywords if kw in text)
    
    # 2. 从文件名获取辅助分类
    file_cat = _detect_file_category(filename_hint)
    file_boost = 1 if text_scores.get(file_cat, 0) > 0 else 0
    
    # 3. 合并得分：文本得分 + 文件分类增强（最多+1）
    final_scores = {}
    for cat_code, score in text_scores.items():
        final_scores[cat_code] = score
    if file_boost:
        final_scores[file_cat] = final_scores.get(file_cat, 0) + file_boost
    
    detected = max(final_scores, key=final_scores.get)
    if final_scores[detected] == 0:
        return file_cat if file_cat else "basic_info"
    return detected

def _extract_keywords(text: str, top_k: int = 8) -> List[str]:
    """从文本中提取关键词"""
    keywords = []
    for cat_code, kw_list in CATEGORY_KEYWORDS.items():
        for kw in kw_list:
            if kw in text and kw not in keywords:
                keywords.append(kw)
    return keywords[:top_k]

# ======================== 语义嵌入模型 ========================
class SemanticEmbedding:
    """
    语义级文本向量化方案
    使用 shibing624/text2vec-base-chinese 中文语义模型
    CPU 可运行，单线程推理，避免阻塞同进程其他任务
    """

    def __init__(self, model_name: str = "shibing624/text2vec-base-chinese"):
        self.model_name = model_name
        self.model = None
        self.dimension = 768
        self._lock = threading.Lock()  # 防止多线程并发编码
        self._embed_cache = {}          # 嵌入缓存：{text: vector}
        self._embed_cache_max = 200     # 最多缓存 200 条
        self._load_model()

    def _load_model(self):
        """加载模型（启动时加载，优先使用本地缓存）"""
        if self.model is not None:
            return
        # 优先使用本地缓存路径，避免网络问题
        from config import EMBEDDING_MODEL_PATH
        local_paths = [
            EMBEDDING_MODEL_PATH,
            self.model_name,  # fallback: 在线加载
        ]
        import torch
        torch.set_num_threads(1)
        for path in local_paths:
            try:
                print(f"[Embedding] 正在加载语义模型（路径：{path}）...")
                # 显式指定 device="cpu"，避免 meta tensor 拷贝错误
                self.model = SentenceTransformer(path, device="cpu", trust_remote_code=True)
                # sentence-transformers 3.x 中 get_embedding_dimension() 已废弃
                # 用 encode 测试字符串的方式获取实际维度
                test_vec = self.model.encode("test", normalize_embeddings=True)
                self.dimension = len(test_vec)
                print(f"[Embedding] 语义模型加载完成，维度：{self.dimension}，PyTorch线程数：{torch.get_num_threads()}")
                return
            except Exception as e:
                print(f"[Embedding] 路径 {path} 加载失败：{e}，尝试下一个...")
        print("[Embedding] 语义模型加载失败，将使用 SimpleEmbedding 降级方案")
        self.model = None

    def embed(self, text: str) -> List[float]:
        """
        将文本转换为语义向量
        使用 text2vec-base-chinese 模型编码
        线程安全：加了锁防止并发踩踏；带 LRU 缓存
        """
        if self.model is None:
            self._load_model()
        if self.model is None:
            fallback = SimpleEmbedding(dimension=self.dimension)
            return fallback.embed(text)

        if not text or not text.strip():
            return [0.0] * self.dimension

        # 缓存命中直接返回
        if text in self._embed_cache:
            return self._embed_cache[text]

        with self._lock:  # 串行化编码，避免多线程同时推理导致 CPU 过载
            try:
                vector = self.model.encode(text, normalize_embeddings=True)
                result = vector.tolist()
                # LRU 缓存淘汰
                if len(self._embed_cache) >= self._embed_cache_max:
                    self._embed_cache.pop(next(iter(self._embed_cache)))
                self._embed_cache[text] = result
                return result
            except Exception as e:
                print(f"[Embedding] 编码失败：{e}")
                fallback = SimpleEmbedding(dimension=self.dimension)
                return fallback.embed(text)


# ======================== 轻量级文本嵌入（降级方案）========================
class SimpleEmbedding:
    """
    轻量级文本向量化方案（纯CPU运行，不依赖GPU）
    使用基于词频的哈希向量化方法，无需下载大型模型
    仅在语义模型不可用时作为降级方案
    """

    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        # 停用词集合（必须在feature_words之前初始化）
        self.stop_words = set("的了在是有一和我对他不也但这那要于就都会而没吧吗啊呢之与及以所则或且乃即")
        # 构建常用中文字词特征词典
        self.feature_words = self._build_feature_dict()

    def _build_feature_dict(self) -> List[str]:
        """构建景区相关特征词词典（扩展版）"""
        # 灵山胜境核心景点词汇
        scene_words = [
            "灵山", "大佛", "灵山大佛", "梵宫", "灵山梵宫", "九龙灌浴", "九龙",
            "拈花湾", "五印坛城", "坛城", "曼飞龙塔", "祥符禅寺", "禅寺",
            "灵山精舍", "精舍", "佛足坛", "阿育王柱", "天下第一掌", "百子戏弥勒",
            "抱佛脚", "菩提大道", "菩提", "香水海", "灵山照壁", "照壁",
            "放生池", "钟楼", "鼓楼", "大雄宝殿", "藏经楼", "灵山塔"
        ]
        
        # 服务相关词汇
        service_words = [
            "门票", "门票价格", "票价", "优惠", "打折", "学生票", "老人票",
            "儿童票", "团体票", "年卡", "季卡", "开放时间", "闭园时间",
            "营业时间", "停车", "停车场", "停车费", "交通", "公交", "地铁",
            "自驾", "导航", "路线", "地址", "电话", "联系", "客服", "咨询",
            "预约", "预订", "购票", "退票", "改签", "讲解", "导游", "导览",
            "观光车", "电瓶车", "游船", "表演", "演出", "时间", "场次",
            "素斋", "素食", "餐厅", "餐饮", "住宿", "酒店", "民宿", "露营"
        ]
        
        # 文化历史词汇
        culture_words = [
            "佛教", "佛法", "禅宗", "禅意", "修行", "祈福", "开光", "法会",
            "文化", "历史", "古代", "朝代", "传统", "习俗", "典故", "由来",
            "传说", "故事", "起源", "发展", "传承", "艺术", "建筑", "雕塑",
            "壁画", "彩绘", "工艺", "非遗", "文物", "古迹"
        ]
        
        # 游览相关词汇
        tour_words = [
            "景点", "介绍", "讲解词", "景观", "风景", "风光", "全景",
            "游览", "参观", "游玩", "旅行", "旅游", "攻略", "推荐",
            "最佳", "路线规划", "行程", "时长", "距离", "海拔", "高度",
            "拍照", "摄影", "打卡", "必看", "必去", "特色", "亮点",
            "季节", "天气", "气候", "注意事项", "提示", "安全"
        ]
        
        # FAQ疑问词
        faq_words = [
            "如何", "怎么", "怎样", "什么", "哪个", "哪些", "多少", "多久",
            "哪里", "何时", "是否", "能不能", "可以吗", "需要吗", "必须吗",
            "吗", "呢", "吧", "啊", "?", "？"
        ]
        
        # 地理相关词汇
        geo_words = [
            "无锡", "太湖", "江苏", "苏州", "常州", "南京", "上海",
            "长三角", "江南", "水乡", "园林", "古镇"
        ]
        
        # 合并所有词汇
        all_words = scene_words + service_words + culture_words + tour_words + faq_words + geo_words
        
        # 扩展特征词（双字词拆单字）
        expanded = []
        for w in all_words:
            expanded.append(w)
            if len(w) == 2 and w not in self.stop_words:
                expanded.append(w[0])
                expanded.append(w[1])
        
        # 去重
        return list(set(expanded))

    def embed(self, text: str) -> List[float]:
        """
        将文本转换为向量
        使用哈希特征 + TF权重的方法
        """
        if not text or not text.strip():
            return [0.0] * self.dimension

        # 初始化向量
        vector = [0.0] * self.dimension
        total_features = 0

        # 提取文本中的特征词
        for i, word in enumerate(self.feature_words):
            if word in text:
                # 计算词频权重
                count = text.count(word)
                # 使用哈希确定向量位置
                pos = self._hash_to_pos(word, i)
                vector[pos] += count
                total_features += count

        # 对单个字符做补充匹配
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':  # 中文字符范围
                pos = self._hash_to_pos(ch, ord(ch))
                vector[pos] += 0.5

        # L2归一化
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def _hash_to_pos(self, text: str, seed: int = 0) -> int:
        """将文本哈希到向量维度范围内的位置"""
        hash_str = f"{text}_{seed}"
        hash_bytes = hashlib.md5(hash_str.encode("utf-8")).digest()
        pos = int.from_bytes(hash_bytes[:4], "big") % self.dimension
        return pos


# ======================== BM25 检索器（替代向量检索） ========================
class BM25Retriever:
    """
    BM25 文本检索器
    基于词频 + 逆文档频率的经典检索算法，比 SimpleEmbedding 哈希匹配更准确
    使用 jieba 分词，无需 GPU，CPU 运行 <1ms
    """

    def __init__(self):
        self.bm25 = None
        self.documents = []  # 保持与 VectorDatabase 一致的文档格式 [{id, text, metadata}]

    def build(self, documents: List[Dict[str, Any]]):
        """全量构建 BM25 索引"""
        self.documents = documents
        if not documents:
            self.bm25 = None
            return
        corpus = [list(jieba.cut(d["text"])) for d in documents]
        self.bm25 = BM25Okapi(corpus)

    def add_documents(self, documents: List[Dict[str, Any]]):
        """增量添加文档（实际是追加后重建索引）"""
        self.documents.extend(documents)
        if not self.documents:
            self.bm25 = None
            return
        corpus = [list(jieba.cut(d["text"])) for d in self.documents]
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        检索与查询最相关的文档（含查询扩展）

        返回：
            检索结果列表，每项包含 {id, text, metadata, score}
        """
        if not self.bm25 or not self.documents:
            return []

        # 查询扩展：将常见词汇映射为文档中实际出现的词汇
        expanded_query = self._expand_query(query)
        tokenized_query = list(jieba.cut(expanded_query))
        scores = self.bm25.get_scores(tokenized_query)

        # 按 BM25 分数降序排列
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    "id": self.documents[idx]["id"],
                    "text": self.documents[idx]["text"],
                    "metadata": self.documents[idx]["metadata"],
                    "score": float(scores[idx]),
                    "distance": 1.0 - float(scores[idx])  # 兼容旧接口的 distance 字段
                })

        return results

    def _expand_query(self, query: str) -> str:
        """查询扩展：将用户常用词映射为文档中实际出现的词汇"""
        expansions = {
            "门票": "票种 价格 票价 成人票 半价票 免票 联票",
            "票价": "票种 价格 成人票 半价票 联票",
            "多少钱": "票种 价格",
            "价格": "票种 价格 元",
            "大佛": "灵山大佛 大佛 88米",
            "梵宫": "灵山梵宫 梵宫",
            "交通": "公交 地铁 自驾 停车",
            "怎么去": "交通 公交 自驾 地铁",
            "停车": "停车场 停车费",
            "演出": "演艺 演出 场次 时间",
            "几点": "开放时间 闭园时间 演出时间",
            "怎么": "交通 路线 攻略",
        }

        expanded = query
        for word, mapping in expansions.items():
            if word in query:
                expanded = expanded.replace(word, mapping)
        return expanded

    def get_document_count(self) -> int:
        return len(self.documents)


# ======================== ChromaDB向量数据库封装 ========================
class VectorDatabase:
    """
    ChromaDB本地向量数据库封装
    提供文档入库、相似度检索功能
    """

    def __init__(self):
        self.embedding = SemanticEmbedding()  # 语义嵌入模型
        self.bm25 = BM25Retriever()           # BM25 检索器（降级方案）
        self.collection = None
        self._init_chromadb()

    def _init_chromadb(self):
        """初始化ChromaDB客户端和集合（自动处理维度变更）"""
        try:
            import chromadb
            from chromadb.config import Settings

            # 确保持久化目录存在
            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

            # 创建chromadb客户端（持久化模式）
            self.client = chromadb.PersistentClient(
                path=CHROMA_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False)
            )

            # 获取或创建集合
            try:
                self.collection = self.client.get_collection(CHROMA_COLLECTION_NAME)
                print(f"[RAG] 加载已有向量库：{CHROMA_COLLECTION_NAME}")

                # 检查维度是否匹配（语义模型 768 vs 旧版 SimpleEmbedding 384）
                try:
                    count = self.collection.count()
                    if count > 0:
                        sample = self.collection.get(limit=1, include=["embeddings"])
                        if sample is not None:
                            emb_list = sample.get("embeddings")
                            if emb_list is not None and len(emb_list) > 0:
                                emb = emb_list[0]
                                existing_dim = int(len(emb))  # int() 确保 Python 原生 int 类型
                                if existing_dim != self.embedding.dimension:
                                    print(f"[RAG] 检测到向量维度变化 {existing_dim}→{self.embedding.dimension}，重建集合...")
                                    self.client.delete_collection(CHROMA_COLLECTION_NAME)
                                    self.collection = self.client.create_collection(
                                        name=CHROMA_COLLECTION_NAME,
                                        metadata={"description": "灵山胜境景区知识库（语义检索）"}
                                    )
                                    print(f"[RAG] 已重建向量库，新维度：{self.embedding.dimension}")
                except Exception as e:
                    print(f"[RAG] 维度检查跳过：{e}")
            except Exception:
                self.collection = self.client.create_collection(
                    name=CHROMA_COLLECTION_NAME,
                    metadata={"description": "灵山胜境景区知识库（语义检索）"}
                )
                print(f"[RAG] 创建新向量库：{CHROMA_COLLECTION_NAME}")

        except ImportError:
            print("[RAG] 警告：chromadb未安装，使用内存模式")
            self.client = None
            self.collection = None
        except Exception as e:
            print(f"[RAG] 警告：ChromaDB初始化失败：{e}")
            self.client = None
            self.collection = None

        # 从已有向量库加载文档，构建 BM25 索引
        self._rebuild_bm25_index()

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        将文档列表添加到向量库，并更新 BM25 索引

        参数：
            documents: 文档字典列表，每项包含 {id, text, metadata}
        """
        if self.collection is None:
            print("[RAG] 向量库未初始化，跳过入库")
            return

        if not documents:
            return

        ids = []
        texts = []
        metadatas = []
        embeddings = []

        for doc in documents:
            doc_id = doc.get("id", str(hash(doc["text"])))
            text = doc["text"]
            metadata = doc.get("metadata", {})

            # 生成语义向量
            vector = self.embedding.embed(text)

            ids.append(doc_id)
            texts.append(text)
            metadatas.append(metadata)
            embeddings.append(vector)

        # 批量添加（使用自带向量，避免ChromaDB再次嵌入）
        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )

        print(f"[RAG] 成功入库 {len(documents)} 条文档")

        # 重建 BM25 索引（包含新入库的文档）
        self._rebuild_bm25_index()

    def search(self, query: str, top_k: int = None, categories: List[str] = None) -> List[Dict[str, Any]]:
        """
        混合检索：语义向量检索 + BM25 关键词检索 + RRF 融合排序

        参数：
            query: 查询文本
            top_k: 返回结果数量
            categories: 目标知识分类列表（如 ["faq", "route"]），None 或含 "all" 表示不过滤

        返回：
            检索结果列表，每项包含 {id, text, metadata, score, distance}
        """
        if top_k is None:
            top_k = CHROMA_TOP_K

        # 并行获取语义检索和 BM25 检索结果
        semantic_results = []
        bm25_results = []

        # 1. 语义检索
        if self.collection is not None:
            try:
                query_vector = self.embedding.embed(query)
                results = self.collection.query(
                    query_embeddings=[query_vector],
                    n_results=top_k * 2,  # 取更多候选
                    include=["documents", "metadatas", "distances"]
                )

                if results and results.get("ids") and len(results["ids"]) > 0 and len(results["ids"][0]) > 0:
                    for i in range(len(results["ids"][0])):
                        doc_id = results["ids"][0][i]
                        doc_text = results["documents"][0][i] if results.get("documents") else ""
                        metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                        distance = results["distances"][0][i] if results.get("distances") else 0.0
                        score = 1.0 / (1.0 + distance)
                        semantic_results.append({
                            "id": doc_id,
                            "text": doc_text,
                            "metadata": metadata,
                            "score": score,
                            "distance": float(distance),
                            "source": "semantic"
                        })
            except Exception as e:
                print(f"[RAG] 语义检索失败：{e}")

        # 2. BM25 检索
        bm25_results = self.bm25.search(query, top_k * 2)

        # 3. RRF 融合排序（Reciprocal Rank Fusion）
        # 对每个结果计算 RRF 分数 = Σ 1/(k + rank)，k=60 为常数
        rrf_scores = {}
        for i, r in enumerate(semantic_results):
            doc_id = r["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (60 + i + 1)
        for i, r in enumerate(bm25_results):
            doc_id = r["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (60 + i + 1)

        # 合并所有结果，按 RRF 分数排序
        all_results = {}
        for r in semantic_results:
            all_results[r["id"]] = r
        for r in bm25_results:
            all_results[r["id"]] = r

        # 4. 查询意图加分：根据查询关键词提升相关类别的权重
        intent_boost = self._get_intent_boost(query)

        for r in all_results.values():
            meta = r.get("metadata", {})
            cat = meta.get("category", "")
            if cat in intent_boost:
                r["score"] = r.get("score", 0) * intent_boost[cat]

        sorted_results = sorted(all_results.values(), key=lambda x: x.get("score", 0), reverse=True)

        # 动态路由：按知识分类过滤（由路由层决定检索哪个分类）
        if categories:
            target_cats = [c for c in categories if c != "all"]
            if target_cats:
                filtered = [r for r in sorted_results
                            if (r.get("metadata") or {}).get("category") in target_cats]
                if filtered:
                    sorted_results = filtered

        # 精排层（cross-encoder）：粗排候选 → 精排 → 取最终 top_k（失败自动降级为粗排原序）
        try:
            from services.rerank_service import rerank
            from config import RERANK_ENABLED, RERANK_TOP_K
            if RERANK_ENABLED and len(sorted_results) > top_k:
                sorted_results = rerank(query, sorted_results[:RERANK_TOP_K], top_k=top_k)
        except Exception as e:
            print(f"[RAG] 精排降级（返回粗排原序）：{e}")

        return sorted_results[:top_k]

    def _get_intent_boost(self, query: str) -> Dict[str, float]:
        """根据查询关键词返回类别加分倍数"""
        boosts = {}

        # 门票/价格相关
        if any(kw in query for kw in ["门票", "票价", "多少钱", "价格", "购票", "买票", "优惠", "折扣"]):
            boosts["basic_info"] = 2.0

        # 交通/怎么去
        if any(kw in query for kw in ["怎么去", "交通", "自驾", "公交", "地铁", "停车", "导航", "路线", "地址"]):
            boosts["basic_info"] = 2.0

        # 演出/表演
        if any(kw in query for kw in ["表演", "演出", "九条龙", "吉祥颂", "几点", "时间", "场次"]):
            boosts["scene_intro"] = 1.5

        # 住宿/餐饮
        if any(kw in query for kw in ["住", "吃", "餐厅", "美食", "住宿", "酒店", "素斋", "素面"]):
            boosts["basic_info"] = 2.0

        return boosts

    def _rebuild_bm25_index(self):
        """从 ChromaDB 中加载所有文档，重建 BM25 索引"""
        if self.collection is None:
            print("[RAG] 向量库未初始化，跳过 BM25 索引重建")
            return

        try:
            all_docs = self.collection.get()
            if all_docs and all_docs["ids"] and len(all_docs["ids"]) > 0:
                documents = []
                for i in range(len(all_docs["ids"])):
                    documents.append({
                        "id": all_docs["ids"][i],
                        "text": all_docs["documents"][i],
                        "metadata": all_docs["metadatas"][i] if all_docs["metadatas"] else {}
                    })
                self.bm25.build(documents)
                print(f"[RAG] BM25 索引已加载，共 {len(documents)} 条文档")
            else:
                self.bm25.build([])
                print("[RAG] 向量库为空，BM25 索引为空")
        except Exception as e:
            print(f"[RAG] BM25 索引重建失败：{e}")
            self.bm25.build([])

    def delete_collection(self):
        """删除当前集合并重新创建"""
        if self.client and self.collection:
            try:
                self.client.delete_collection(CHROMA_COLLECTION_NAME)
                print(f"[RAG] 已删除向量库：{CHROMA_COLLECTION_NAME}")
                # 重新创建集合
                self.collection = self.client.create_collection(
                    name=CHROMA_COLLECTION_NAME,
                    metadata={"description": "灵山胜境景区知识库"}
                )
                print(f"[RAG] 已重新创建向量库：{CHROMA_COLLECTION_NAME}")
                self.bm25.build([])  # 清空 BM25 索引
            except Exception as e:
                print(f"[RAG] 删除向量库失败：{e}")

    def delete_documents_by_id_prefix(self, prefix: str) -> int:
        """
        删除ID以指定前缀开头的所有文档（从 ChromaDB 和 BM25 中同步清理）
        用于清理已删除知识条目对应的向量文档块
        
        参数：
            prefix: 文档ID前缀，如 "upload_xxx.docx_" 或 "doc_xxx_"
        
        返回：
            删除的文档数量
        """
        if self.collection is None:
            return 0

        try:
            all_docs = self.collection.get()
            if not all_docs or not all_docs.get("ids"):
                return 0

            ids = all_docs["ids"]
            # 找出以指定前缀开头的ID
            to_delete = [doc_id for doc_id in ids if doc_id.startswith(prefix)]
            if not to_delete:
                return 0

            # 删除 ChromaDB 中的文档
            self.collection.delete(ids=to_delete)
            print(f"[RAG] 已从向量库删除 {len(to_delete)} 条文档（前缀: {prefix}）")

            # 同步清理 BM25 索引
            self._rebuild_bm25_index()

            return len(to_delete)
        except Exception as e:
            print(f"[RAG] 删除向量文档失败：{e}")
            return 0

    def delete_documents_by_ids(self, doc_ids: List[str]) -> int:
        """
        删除指定ID的文档
        """
        if self.collection is None:
            return 0

        if not doc_ids:
            return 0

        try:
            all_docs = self.collection.get()
            if not all_docs or not all_docs.get("ids"):
                return 0

            existing_ids = set(all_docs["ids"])
            to_delete = [doc_id for doc_id in doc_ids if doc_id in existing_ids]
            if not to_delete:
                return 0

            self.collection.delete(ids=to_delete)
            print(f"[RAG] 已从向量库删除 {len(to_delete)} 条指定文档")

            # 同步清理 BM25 索引
            self._rebuild_bm25_index()

            return len(to_delete)
        except Exception as e:
            print(f"[RAG] 删除向量文档失败：{e}")
            return 0

    def get_document_count(self) -> int:
        """获取文档总数（优先使用 BM25 计数）"""
        bm25_count = self.bm25.get_document_count()
        if bm25_count > 0:
            return bm25_count
        # 降级：从 ChromaDB 获取
        if self.collection is None:
            return 0
        try:
            return self.collection.count()
        except Exception:
            return 0


# ======================== 文档切割与知识库构建 ========================
class KnowledgeProcessor:
    """
    知识库文档处理器
    负责读取文档、切片、构建向量库
    """

    def __init__(self):
        self.vector_db = VectorDatabase()
        # 查询缓存：缓存最近 50 个查询的上下文结果
        self._context_cache = {}
        self._cache_max = 50

    def _extract_file_text(self, file_path: str) -> str:
        """根据文件类型提取文本"""
        filename = os.path.basename(file_path)
        if filename.endswith(".docx"):
            return self.extract_text_from_docx(file_path)
        elif filename.endswith(".xlsx"):
            return self.extract_text_from_xlsx(file_path)
        elif filename.endswith(".txt"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"[RAG] 读取txt失败 {file_path}: {e}")
        return ""

    def extract_text_from_docx(self, file_path: str) -> str:
        """从docx文件提取纯文本（包含表格内容）"""
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = []
            for p in doc.paragraphs:
                text = p.text.strip()
                if text:
                    paragraphs.append(text)
            # 提取表格内容
            table_texts = []
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join([cell.text.strip() for cell in row.cells])
                    if row_text.strip():
                        table_texts.append(row_text)
            return "\n".join(paragraphs) + "\n" + "\n".join(table_texts)
        except Exception as e:
            print(f"[RAG] 读取docx失败 {file_path}: {e}")
            return ""

    def extract_text_from_xlsx(self, file_path: str, max_rows: int = 500, target_spots: List[str] = None) -> str:
        """从xlsx文件提取文本数据（限制行数，防止超大文件）
        target_spots: 只提取包含这些关键词的行（用于过滤无关景点数据）
        """
        if target_spots is None:
            target_spots = ["灵山", "灵山胜境", "拈花湾"]
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True)
            texts = []
            total_rows = 0
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                for row in ws.iter_rows(values_only=True):
                    if total_rows >= max_rows:
                        break
                    row_text = " ".join([str(cell) for cell in row if cell is not None])
                    if row_text.strip():
                        # 只保留包含目标景点关键词的行
                        if any(spot in row_text for spot in target_spots):
                            texts.append(row_text)
                    total_rows += 1
                if total_rows >= max_rows:
                    break
            return "\n".join(texts)
        except Exception as e:
            print(f"[RAG] 读取xlsx失败 {file_path}: {e}")
            return ""

    def split_text_to_chunks(self, text: str, chunk_size: int = 200, overlap: int = 50) -> List[str]:
        """
        将长文本分割成文档块

        参数：
            text: 原始文本
            chunk_size: 每块字符数
            overlap: 块间重叠字符数

        返回：
            文档块列表
        """
        if not text:
            return []

        # 按句子切分
        sentences = re.split(r"([。！？\n])", text)
        chunks = []
        current_chunk = ""

        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")

            if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                # 重叠处理：保留最后一部分
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + sentence
            else:
                current_chunk += sentence

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text]

    def build_knowledge_base(self, knowledge_dir: str = None) -> int:
        """
        从知识库目录读取所有文档，构建向量库（同时创建数据库知识条目）

        参数：
            knowledge_dir: 知识库文档目录路径

        返回：
            入库的文档块数量
        """
        if knowledge_dir is None:
            knowledge_dir = KOWLEDGE_DIR

        if not os.path.exists(knowledge_dir):
            print(f"[RAG] 知识库目录不存在：{knowledge_dir}")
            return 0

        # 文件黑名单关键词（跳过行为分析、统计数据等对游客无用的文件）
        blacklist_keywords = ["分析", "行为", "统计", "日志", "报表", "记录", "csv", "log"]

        # 扫描目录下的所有文档，按文件组织知识条目
        knowledge_entries = []
        file_info = []

        for filename in os.listdir(knowledge_dir):
            file_path = os.path.join(knowledge_dir, filename)
            if not os.path.isfile(file_path):
                continue

            # 对xlsx文件，检查是否包含行为/分析类关键词（这些是行为分析数据，对游客无用）
            is_blacklisted = False
            if filename.endswith(".xlsx"):
                lower_name = filename.lower()
                # 只有同时包含"数据"+("分析"或"行为")才跳过
                if "数据" in lower_name and any(kw in lower_name for kw in ["分析", "行为", "统计"]):
                    is_blacklisted = True
            
            if is_blacklisted:
                print(f"[RAG] 跳过行为分析类文件：{filename}")
                continue

            # 检查文件是否已经处理过（防止重复同步导致数据重复）
            # 但如果向量库为空（首次构建或重建），则忽略此检查，允许重新处理所有文件
            try:
                from models import Knowledge as KnowledgeModel
                existing = KnowledgeModel.query.filter_by(source_file=filename).first()
                if existing:
                    # 向量库非空才跳过；向量库为空说明需要重建
                    if self.vector_db.get_document_count() > 0:
                        print(f"[RAG] 文件已处理，跳过：{filename}")
                        continue
                    else:
                        print(f"[RAG] 向量库为空，将重新处理：{filename}")
            except Exception as e:
                print(f"[RAG] 检查文件处理状态失败（将重新处理）：{filename} - {e}")

            if filename.endswith(".docx"):
                entries = self._parse_docx_to_entries(file_path, filename)
                knowledge_entries.extend(entries)
            elif filename.endswith(".xlsx"):
                entries = self._parse_xlsx_to_entries(file_path, filename)
                knowledge_entries.extend(entries)
            elif filename.endswith(".txt"):
                entries = self._parse_txt_to_entries(file_path, filename)
                knowledge_entries.extend(entries)

            if entries:
                file_info.append({"filename": filename, "size": len(entries)})
                print(f"[RAG] 读取文档：{filename} ({len(entries)}条知识条目)")

        if not knowledge_entries:
            print("[RAG] 未读取到任何有效文档内容")
            return 0

        print(f"[RAG] 文档解析完成：共 {len(knowledge_entries)} 条知识条目")

        # 构建入库数据（向量库仍按文档块存储）
        documents = []
        all_chunks = []
        
        for i, entry in enumerate(knowledge_entries):
            text = entry["content"]
            chunks = self.split_text_to_chunks(text, chunk_size=200, overlap=50)
            for j, chunk in enumerate(chunks):
                doc_id = f"doc_{i}_{j}_{hash(chunk) % 1000000}"
                documents.append({
                    "id": doc_id,
                    "text": chunk,
                    "metadata": {
                        "source": "knowledge_base",
                        "entry_index": i,
                        "chunk_index": j,
                        "total_chunks": len(chunks),
                        "filename": entry["filename"],
                        "title": entry["title"],
                        "category": entry["category"]
                    }
                })
                all_chunks.append({
                    "text": chunk,
                    "filename": entry["filename"],
                    "title": entry["title"],
                    "category": entry["category"]
                })

        # 入库到向量库
        self.vector_db.add_documents(documents)

        # 同步创建数据库知识条目（按语义单元创建，而非按文档块）
        self._create_knowledge_entries(file_info, knowledge_entries)

        return len(documents)

    def _create_knowledge_entries(self, file_info: List[Dict], knowledge_entries: List[Dict]):
        """
        将知识条目同步创建为数据库知识条目（每个语义单元一条）
        """
        try:
            from models import db, Knowledge, KnowledgeCategory

            created_count = 0
            for entry in knowledge_entries:
                content = entry["content"].strip()
                filename = entry.get("filename", "unknown")
                title = entry.get("title", "")
                category_code = entry.get("category", "")
                
                if not content or len(content) < 20:
                    continue
                
                cat = KnowledgeCategory.query.filter_by(code=category_code).first()
                if not cat:
                    detected_code = _detect_category(content)
                    cat = KnowledgeCategory.query.filter_by(code=detected_code).first()
                    if not cat:
                        cat = KnowledgeCategory.query.filter_by(code="basic_info").first()
                
                keywords = _extract_keywords(content)
                
                if not title:
                    title = content[:50].replace("\n", " ") + "..." if len(content) > 50 else content
                
                knowledge = Knowledge(
                    category_id=cat.id if cat else 1,
                    title=title,
                    content=content,
                    tags=", ".join(keywords),
                    source_file=filename,
                    keywords=", ".join(keywords),
                    vector_sync=True,
                    is_active=True
                )
                db.session.add(knowledge)
                created_count += 1

            db.session.commit()
            print(f"[RAG] 已创建 {created_count} 条数据库知识条目")
        except Exception as e:
            print(f"[RAG] 创建数据库知识条目失败：{e}")
            try:
                db.session.rollback()
            except:
                pass

    def _parse_docx_to_entries(self, file_path: str, filename: str) -> List[Dict]:
        """将docx文档解析为知识条目列表"""
        entries = []
        try:
            from docx import Document
            doc = Document(file_path)
            
            # 检测文档类型
            detected_category = self._detect_file_category(filename)
            
            # 按表格行解析（景点数据）
            for table in doc.tables:
                if len(table.rows) < 2:
                    continue
                
                headers = [cell.text.strip() for cell in table.rows[0].cells]
                
                for row in table.rows[1:]:
                    row_data = [cell.text.strip() for cell in row.cells]
                    if not any(row_data):
                        continue
                    
                    row_dict = dict(zip(headers, row_data))
                    entry = self._build_entry_from_row(row_dict, filename, detected_category)
                    if entry:
                        entries.append(entry)
            
            # 如果没有表格，按段落结构解析（支持按空行分组或按标题样式分组）
            if not entries:
                entries = self._parse_docx_paragraphs_to_entries(doc, filename, detected_category)

            # 如果仍然没有解析出条目，回退到简单文本模式
            if not entries:
                paragraphs = []
                for p in doc.paragraphs:
                    text = p.text.strip()
                    if text:
                        paragraphs.append(text)
                if paragraphs:
                    content = "\n".join(paragraphs)
                    title = paragraphs[0][:50] if paragraphs else filename
                    entries.append({
                        "title": title,
                        "content": content,
                        "filename": filename,
                        "category": detected_category
                    })
            
        except Exception as e:
            print(f"[RAG] 解析docx失败 {file_path}: {e}")
            text = self.extract_text_from_docx(file_path)
            if text:
                entries.append({
                    "title": filename,
                    "content": text,
                    "filename": filename,
                    "category": detected_category
                })
        
        return entries

    def _parse_docx_paragraphs_to_entries(self, doc, filename: str, detected_category: str) -> List[Dict]:
        """
        将docx文档的段落结构解析为多个知识条目
        
        策略：
        1. 检测标题样式（Heading 1-3）或字体特征（加粗/大字号）来识别章节
        2. 将同一章节下的段落分组为一个知识条目
        3. 用标题作为条目标题，分组段落作为内容
        """
        entries = []
        
        try:
            paragraphs = []
            for p in doc.paragraphs:
                text = p.text.strip()
                if text:
                    # 检测是否为标题段落
                    is_heading = self._is_heading_paragraph(p)
                    paragraphs.append({
                        "text": text,
                        "is_heading": is_heading,
                        "style": p.style.name if p.style else "",
                        "font_size": self._get_paragraph_font_size(p),
                        "is_bold": self._is_paragraph_bold(p)
                    })
            
            if not paragraphs:
                return entries
            
            # 按标题分组段落
            sections = []
            current_section = {"title": "", "paragraphs": []}
            
            for para in paragraphs:
                if para["is_heading"]:
                    # 如果当前章节有内容，保存
                    if current_section["paragraphs"]:
                        sections.append(current_section)
                    # 开始新章节
                    current_section = {"title": para["text"], "paragraphs": []}
                else:
                    current_section["paragraphs"].append(para["text"])
            
            # 保存最后一个章节
            if current_section["paragraphs"]:
                sections.append(current_section)
            
            # 如果没有检测到任何标题，按空行或长段落分组
            if len(sections) == 0:
                # 回退策略：按段落长度分组
                current_section = {"title": filename, "paragraphs": []}
                for para in paragraphs:
                    current_section["paragraphs"].append(para["text"])
                if current_section["paragraphs"]:
                    sections.append(current_section)
            
            # 构建知识条目
            for section in sections:
                title = section["title"] if section["title"] else filename
                content = "\n".join(section["paragraphs"])
                
                # 过滤过短的内容
                if len(content) < 20:
                    continue
                
                entries.append({
                    "title": title,
                    "content": content,
                    "filename": filename,
                    "category": detected_category
                })
            
            print(f"[RAG] docx段落解析完成：{filename} 生成 {len(entries)} 个知识条目")
            
        except Exception as e:
            print(f"[RAG] 解析docx段落结构失败 {filename}: {e}")
        
        return entries
    
    def _is_heading_paragraph(self, paragraph) -> bool:
        """检测段落是否为标题"""
        # 1. 检查样式名称
        style_name = paragraph.style.name if paragraph.style else ""
        if any(keyword in style_name.lower() for keyword in ["heading", "标题"]):
            return True
        
        # 2. 检查字体特征：加粗且字号较大
        if self._is_paragraph_bold(paragraph):
            font_size = self._get_paragraph_font_size(paragraph)
            if font_size >= 16:  # 16pt 及以上认为是标题
                return True
        
        return False
    
    def _get_paragraph_font_size(self, paragraph) -> int:
        """获取段落的字体大小（pt）"""
        try:
            if paragraph.runs:
                # 取第一个run的字号
                run = paragraph.runs[0]
                if run.font.size:
                    # run.font.size 是 EMU (1/914400 inch)，转换为 pt
                    return int(run.font.size.pt)
        except:
            pass
        return 11  # 默认字号
    
    def _is_paragraph_bold(self, paragraph) -> bool:
        """检测段落是否加粗"""
        try:
            if paragraph.runs:
                return paragraph.runs[0].bold
        except:
            pass
        return False

    def _parse_xlsx_to_entries(self, file_path: str, filename: str) -> List[Dict]:
        """将xlsx文档解析为知识条目列表"""
        entries = []
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path)
            
            detected_category = self._detect_file_category(filename)
            
            for sheet in wb.worksheets:
                if sheet.max_row < 2:
                    continue
                
                headers = [cell.value for cell in sheet[1]]
                headers = [str(h).strip() if h else "" for h in headers]
                
                for row in sheet.iter_rows(min_row=2):
                    row_data = [cell.value for cell in row]
                    row_data = [str(d).strip() if d else "" for d in row_data]
                    
                    # 行级过滤：跳过空行和碎片数据
                    if not any(row_data):
                        continue
                    
                    # 有效字段数检查：至少3个非空字段
                    valid_fields = [d for d in row_data if d]
                    if len(valid_fields) < 3:
                        continue
                    
                    # 总内容长度检查：至少30字符
                    total_length = sum(len(d) for d in valid_fields)
                    if total_length < 30:
                        continue
                    
                    row_dict = dict(zip(headers, row_data))
                    entry = self._build_entry_from_row(row_dict, filename, detected_category)
                    if entry:
                        entries.append(entry)
        
        except Exception as e:
            print(f"[RAG] 解析xlsx失败 {file_path}: {e}")
            text = self.extract_text_from_xlsx(file_path)
            if text:
                entries.append({
                    "title": filename,
                    "content": text,
                    "filename": filename,
                    "category": detected_category
                })
        
        return entries

    def _parse_txt_to_entries(self, file_path: str, filename: str) -> List[Dict]:
        """将txt文档解析为知识条目列表"""
        entries = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            
            detected_category = self._detect_file_category(filename)
            
            # 按空行分割段落
            sections = re.split(r"\n\s*\n", text.strip())
            for section in sections:
                section = section.strip()
                if len(section) < 20:
                    continue
                
                lines = section.split("\n")
                title = lines[0][:60] if lines else filename
                content = section
                
                entries.append({
                    "title": title,
                    "content": content,
                    "filename": filename,
                    "category": detected_category
                })
        
        except Exception as e:
            print(f"[RAG] 解析txt失败 {file_path}: {e}")
        
        return entries

    def _detect_file_category(self, filename: str) -> str:
        """根据文件名检测知识分类（委托给全局函数）"""
        return _detect_file_category(filename)

    def _build_entry_from_row(self, row_dict: Dict, filename: str, detected_category: str) -> Dict:
        """从表格行数据构建知识条目"""
        title = ""
        content_parts = []
        first_value = ""  # 记录第一个有效字段值，作为标题备选
        
        for key, value in row_dict.items():
            if not value:
                continue
            
            # 识别标题字段：优先使用"名称"/"标题"/"问题"/"景点"列
            if any(t in key for t in ["名称", "景点", "标题", "问题", "主题"]):
                title = value
            elif any(d in key for d in ["介绍", "内容", "详情", "描述", "说明", "特色", "亮点"]):
                content_parts.append(f"{key}：{value}")
            else:
                content_parts.append(f"{key}：{value}")
            
            if not first_value:
                first_value = value
        
        # 生成标题：优先使用表格中的名称列；否则从内容中提取有意义的短句
        if not title:
            # 尝试从内容中提取第一个有意义的描述作为标题
            for part in content_parts:
                # 取 "：/" 后面的内容前50字
                if "：" in part:
                    desc = part.split("：", 1)[1].strip()
                    if desc:
                        title = desc[:50]
                        break
            if not title:
                # 取第一个有效字段值
                title = first_value[:60] if first_value else filename
        
        content = "\n".join(content_parts)
        
        if len(content) < 20:
            return None
        
        # 景区相关性检查：内容需包含以下关键词至少一个
        relevant_keywords = [
            "灵山", "拈花湾", "灵山胜境", "景区", "景点", "门票", "路线", 
            "开放时间", "交通", "价格", "地址", "游览", "攻略", "行程",
            "大佛", "梵宫", "坛城", "禅意小镇", "九龙灌浴", "阿育王柱", "祥符禅寺"
        ]
        
        all_text = title + content
        if not any(kw in all_text for kw in relevant_keywords):
            return None
        
        # 从内容检测分类（不再仅依赖文件名）
        content_category = _detect_category_from_text(all_text, filename)
        
        return {
            "title": title,
            "content": content,
            "filename": filename,
            "category": content_category
        }

    def search_knowledge(self, query: str, top_k: int = None, categories: List[str] = None) -> List[Dict[str, Any]]:
        """检索知识库（可选按分类过滤）"""
        return self.vector_db.search(query, top_k, categories)

    def get_document_count(self) -> int:
        """获取向量库文档总数"""
        return self.vector_db.get_document_count()

    def get_knowledge_context(self, query: str, top_k: int = None, categories: List[str] = None) -> str:
        """
        检索知识库并组装为上下文文本（带缓存）

        参数：
            query: 用户查询
            top_k: 检索数量
            categories: 目标知识分类列表（如 ["faq", "route"]），None 或 ["all"] 表示不过滤

        返回：
            拼接后的上下文文本，供LLM使用
        """
        cache_key = f"{query}|{','.join(categories or [])}"
        if cache_key in self._context_cache:
            print(f"[RAG] 缓存命中：{query[:30]}...")
            return self._context_cache[cache_key]

        results = self.search_knowledge(query, top_k, categories)
        if not results:
            context = ""
        else:
            context_parts = [f"[参考{i + 1}] {r['text']}" for i, r in enumerate(results)]
            context = "\n\n".join(context_parts)

        # 知识图谱增强：按查询实体做邻域扩展，补充关联三元组
        if context:
            try:
                from services.graph_service import get_knowledge_graph
                graph_ctx = get_knowledge_graph().retrieve_context(query)
                if graph_ctx:
                    context += "\n\n" + graph_ctx
            except Exception as e:
                print(f"[RAG] 图谱增强失败：{e}")

        # 写入缓存，LRU 淘汰
        if len(self._context_cache) >= self._cache_max:
            self._context_cache.pop(next(iter(self._context_cache)))
        self._context_cache[cache_key] = context
        return context


# ======================== 全局单例 ========================
_knowledge_processor = None


def get_knowledge_processor() -> KnowledgeProcessor:
    """获取知识库处理器单例"""
    global _knowledge_processor
    if _knowledge_processor is None:
        _knowledge_processor = KnowledgeProcessor()
    return _knowledge_processor
