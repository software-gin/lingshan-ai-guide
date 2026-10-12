"""
==============================================================
【灵山胜境AI数字人导游系统】全局配置文件
==============================================================
所有配置项优先从环境变量读取（.env 文件），
未设置时使用代码中的默认值兜底。

环境变量文件位置：backend/.env（自动加载）
==============================================================
"""

import os
import json

# ======================== 加载 .env 文件 ========================
from dotenv import load_dotenv

# 当前文件所在目录（backend/）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 加载 .env 文件（显式指定路径，优先加载）
dotenv_path = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path, override=True)

# 本地真实密钥文件 backend/.env.local（已被 .gitignore 排除，不进 git）
# 在 .env 之后加载，override=True 用真实值覆盖 .env 中的空占位，保证本地可运行
_local_env = os.path.join(BASE_DIR, ".env.local")
if os.path.exists(_local_env):
    load_dotenv(_local_env, override=True)

# ======================== 辅助函数 ========================
def _env_str(key: str, default: str) -> str:
    """读取字符串环境变量"""
    return os.environ.get(key, default)

def _env_int(key: str, default: int) -> int:
    """读取整数环境变量"""
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default

def _env_float(key: str, default: float) -> float:
    """读取浮点数环境变量"""
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default

def _env_bool(key: str, default: bool) -> bool:
    """读取布尔环境变量"""
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")

def _env_list(key: str, default: list) -> list:
    """读取JSON数组格式的环境变量"""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        parsed = json.loads(val)
        if isinstance(parsed, list):
            return parsed
        return default
    except (json.JSONDecodeError, TypeError):
        # 尝试逗号分隔
        return [v.strip() for v in val.split(",") if v.strip()]

def _env_set(key: str, default: set) -> set:
    """读取集合环境变量（逗号分隔）"""
    val = os.environ.get(key)
    if val is None:
        return default
    return {v.strip() for v in val.split(",") if v.strip()}


# ======================== 基础路径配置 ========================
KOWLEDGE_DIR = os.path.join(os.path.dirname(BASE_DIR), "knowledge")  # 知识库文档存放目录

# ======================== 数据库配置 ========================
SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "lingshan.db")
SQLALCHEMY_TRACK_MODIFICATIONS = False

# ======================== 会话密钥 ========================
# 【安全】禁止在源码中硬编码密钥；未配置时生成一次性随机 key（仅开发态可用）
# 生产环境必须通过环境变量/密钥管理服务注入稳定的 SECRET_KEY，否则 session 会随重启失效
SECRET_KEY = _env_str("SECRET_KEY", "")
if not SECRET_KEY:
    import secrets as _secrets
    SECRET_KEY = _secrets.token_hex(32)
    print("[config] 警告：未配置 SECRET_KEY，已生成一次性随机值（生产环境请显式配置）")

# ======================== Flask 运行配置 ========================
FLASK_HOST = _env_str("FLASK_HOST", "0.0.0.0")
FLASK_PORT = _env_int("FLASK_PORT", 5001)
# 【安全】生产环境必须关闭 debug，否则 Werkzeug debugger 可被远程利用执行代码
FLASK_DEBUG = _env_bool("FLASK_DEBUG", False)
SESSION_TYPE = _env_str("SESSION_TYPE", "filesystem")
# 【安全】默认仅放行本地开发端口；生产环境通过 .env 显式配置允许的域名
CORS_ORIGINS = _env_str(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
)

# ======================== 【重要】多模态大模型配置（通义千问 Qwen） ========================
LLM_API_KEY = _env_str("LLM_API_KEY", "")
LLM_API_BASE = _env_str("LLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL_NAME = _env_str("LLM_MODEL_NAME", "qwen3.5-omni-flash")
LLM_VISION_MODEL = _env_str("LLM_VISION_MODEL", "qwen3.5-omni-flash")
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 1024)
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.7)
LLM_STREAM_CHUNK_THRESHOLD = _env_int("LLM_STREAM_CHUNK_THRESHOLD", 20)

# ======================== LLM 可靠性配置（重试/超时/熔断/并发/预算） ========================
# 请求最大重试次数（指数退避，429/5xx/超时/连接错误才重试）
LLM_MAX_RETRIES = _env_int("LLM_MAX_RETRIES", 3)
# HTTP 连接超时（秒）—— 建立 TCP 连接的上限
LLM_CONNECT_TIMEOUT = _env_float("LLM_CONNECT_TIMEOUT", 10)
# HTTP 读取超时（秒）—— 等待响应数据的上限（流式场景读第一个 chunk）
LLM_READ_TIMEOUT = _env_float("LLM_READ_TIMEOUT", 120)
# 熔断器：连续失败 N 次后触发熔断，在恢复期内快速失败（避免雪崩式重试耗尽 quota）
LLM_CIRCUIT_BREAKER_THRESHOLD = _env_int("LLM_CIRCUIT_BREAKER_THRESHOLD", 5)
# 熔断器恢复时间（秒）—— 熔断后等待多久放一个探测请求
LLM_CIRCUIT_BREAKER_RECOVERY = _env_int("LLM_CIRCUIT_BREAKER_RECOVERY", 30)
# 并发上限：同时进行的 LLM 请求数（防止模型侧限流雪崩）
LLM_CONCURRENCY_LIMIT = _env_int("LLM_CONCURRENCY_LIMIT", 4)
# Quota 预算告警阈值：累计 token 消耗达到该值时打 WARN 日志（0 表示关闭）
LLM_TOKEN_BUDGET_WARN = _env_int("LLM_TOKEN_BUDGET_WARN", 0)

# ======================== Agent（ReAct）配置 ========================
# ReAct 循环最大轮数（思考→调工具→观察 为一轮），超限后强制收敛生成最终回答
AGENT_MAX_ROUNDS = _env_int("AGENT_MAX_ROUNDS", 4)
# 子 Agent（检索专员/行程专员）内部 ReAct 最大轮数
SUBAGENT_MAX_ROUNDS = _env_int("SUBAGENT_MAX_ROUNDS", 3)

# ======================== memoryAgent 记忆层配置 ========================
# 短期记忆窗口：单会话注入的最大历史轮数（超过窗口的对话由长期记忆摘要承接）
MEMORY_SHORT_TERM_TURNS = _env_int("MEMORY_SHORT_TERM_TURNS", 10)
# 长期记忆召回：每次提问注入的相关记忆条数上限
MEMORY_RECALL_TOP_K = _env_int("MEMORY_RECALL_TOP_K", 3)

# ReAct 前置预判：轻量路由先判断"无需检索"的问题直接流式回答（省一轮工具调用协议开销）
ROUTER_PRECHECK = _env_bool("ROUTER_PRECHECK", True)

# ======================== 视频理解配置（降级方案：关键帧+单帧理解+ASR+融合） ========================
VIDEO_ALLOWED_EXTENSIONS = _env_set("VIDEO_ALLOWED_EXTENSIONS", {"mp4", "avi", "mov", "mkv", "webm"})
VIDEO_MAX_SIZE = _env_int("VIDEO_MAX_SIZE", 128 * 1024 * 1024)  # 128MB，与 MAX_CONTENT_LENGTH 保持一致
VIDEO_MAX_KEYFRAMES = _env_int("VIDEO_MAX_KEYFRAMES", 6)        # 关键帧抽提上限

# ======================== Whisper ASR 配置 ========================
WHISPER_MODEL_SIZE = _env_str("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = _env_str("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = _env_str("WHISPER_COMPUTE_TYPE", "int8")

# ASR 初始提示词 —— 告诉 Whisper 这段话里可能出现哪些词
# 包含灵山胜境核心专有名词，引导模型正确识别
# 保持硬编码不变（多行长文本不适合放在 .env 中）
ASR_INITIAL_PROMPT = (
    "灵山胜境 灵山大佛 梵宫 九龙灌浴 拈花湾 五印坛城 祥符禅寺 灵山精舍 "
    "佛足坛 阿育王柱 天下第一掌 百子戏弥勒 菩提大道 香水海 放生池 "
    "门票 价格 开放时间 路线 怎么走 推荐 讲解 介绍"
)

# ======================== Edge-TTS 配置 ========================
TTS_VOICE = _env_str("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
TTS_VOICE_LIST = _env_list("TTS_VOICE_LIST", [
    "zh-CN-XiaoxiaoNeural",   # 晓晓（女声，推荐）
    "zh-CN-YunxiNeural",      # 云希（男声）
    "zh-CN-YunyangNeural",    # 云扬（男声，情感丰富）
    "zh-CN-XiaoyiNeural",     # 晓伊（女声，活泼）
    "zh-CN-XiaohanNeural",    # 晓涵（女声，温柔）
])

# ======================== ChromaDB 向量库配置 ========================
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")
CHROMA_COLLECTION_NAME = _env_str("CHROMA_COLLECTION_NAME", "lingshan_knowledge")
CHROMA_TOP_K = _env_int("CHROMA_TOP_K", 5)

# ======================== 知识图谱增强 RAG（GraphRAG）配置 ========================
# 是否开启图谱增强检索（检索知识库时按实体邻域扩展，补充关联三元组）
GRAPH_ENHANCED_RAG = _env_bool("GRAPH_ENHANCED_RAG", True)
# 查询时图邻域扩展的跳数（1=直接邻居，2=二跳）
GRAPH_MAX_HOPS = _env_int("GRAPH_MAX_HOPS", 1)
# 查询时最多返回的关联三元组条数
GRAPH_TOP_K = _env_int("GRAPH_TOP_K", 5)

# ======================== RAG 精排层（bge-reranker，cross-encoder） ========================
# 开启后：语义+BM25+RRF 粗排取 top RERANK_TOP_K 候选 → cross-encoder 精排 → 取最终 top_k
RERANK_ENABLED = _env_bool("RERANK_ENABLED", True)
# 送入精排的候选数量（建议 20-50，过大拖慢延迟）
RERANK_TOP_K = _env_int("RERANK_TOP_K", 20)
# 精排模型（中文友好，可改为 bge-reranker-large 更准但更慢）
RERANK_MODEL = _env_str("RERANK_MODEL", "BAAI/bge-reranker-base")

# ======================== 可观测性（Langfuse，缺省关闭、零侵入） ========================
LANGFUSE_ENABLED = _env_bool("LANGFUSE_ENABLED", False)
LANGFUSE_PUBLIC_KEY = _env_str("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = _env_str("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = _env_str("LANGFUSE_HOST", "http://localhost:3000")

# ======================== 错误追踪（Sentry，留空=禁用） ========================
# 分工：Sentry 管应用层异常告警，Langfuse 管 LLM 链路 trace，二者并存不冲突
SENTRY_DSN = _env_str("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = _env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1)

# ======================== HuggingFace 配置 ========================
# 【安全】禁止在源码中硬编码 token；必须通过环境变量注入
HF_TOKEN = _env_str("HF_TOKEN", "")
# 语义嵌入模型路径（优先使用本地缓存，避免网络下载）
EMBEDDING_MODEL_PATH = _env_str("EMBEDDING_MODEL_PATH", "shibing624/text2vec-base-chinese")
# 国内网络直连 huggingface.co 不稳定，使用镜像加速下载（可通过 .env 覆盖）
os.environ["HF_ENDPOINT"] = _env_str("HF_ENDPOINT", "https://hf-mirror.com")

# ======================== LiveTalking 3D 数字人配置 ========================
LIVETALKING_API_URL = _env_str("LIVETALKING_API_URL", "http://172.19.165.3:8010")
LIVETALKING_ENABLED = _env_bool("LIVETALKING_ENABLED", True)
# Avatar 头像通过 LiveTalking 服务器的 API 获取（非本地磁盘）
LIVETALKING_AVATARS_API_URL = f"{LIVETALKING_API_URL}/api/avatars"

# ======================== WebSocket 配置 ========================
WS_PING_INTERVAL = _env_int("WS_PING_INTERVAL", 30)
WS_PING_TIMEOUT = _env_int("WS_PING_TIMEOUT", 10)

# ======================== 分句与流式配置 ========================
SENTENCE_SPLIT_PATTERN = r"[。！？\n！？]+"     # 分句正则（正则表达式不适合放 .env）
STREAM_CHUNK_SIZE = _env_int("STREAM_CHUNK_SIZE", 50)

# ======================== 默认管理员账号 ========================
DEFAULT_ADMIN_USERNAME = _env_str("DEFAULT_ADMIN_USERNAME", "admin")
# 【安全】默认密码留空，由 .env 或环境变量注入；留空时跳过默认管理员创建
DEFAULT_ADMIN_PASSWORD = _env_str("DEFAULT_ADMIN_PASSWORD", "")

# ======================== 文件上传配置 ========================
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = _env_set("ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif", "webp"})
MAX_CONTENT_LENGTH = _env_int("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)

# ======================== 生产服务器配置（waitress） ========================
# 【高可用】worker 线程数：默认 auto（CPU 核心数×4），可显式覆盖
WAITRESS_THREADS = _env_int("WAITRESS_THREADS", 0)  # 0 = auto
WAITRESS_CHANNEL_TIMEOUT = _env_int("WAITRESS_CHANNEL_TIMEOUT", 120)
WAITRESS_CONNECTION_LIMIT = _env_int("WAITRESS_CONNECTION_LIMIT", 100)

# ======================== 地图配置 ========================
# 【安全】禁止在源码中硬编码密钥；必须通过环境变量注入
MAP_KEY = _env_str("MAP_KEY", "")