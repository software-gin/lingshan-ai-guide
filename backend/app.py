"""
==============================================================
【灵山胜境AI数字人导游系统】Flask主应用入口
==============================================================
"""

import os
import sys

# 确保项目目录在路径中
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_sock import Sock

# 结构化日志（最早初始化，保证后续启动日志落盘）
from log_config import setup_logging, init_request_tracking
setup_logging()

import logging
logger = logging.getLogger(__name__)

# 导入配置
from config import (
    SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS,
    SECRET_KEY,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH,
    SESSION_TYPE,
    CORS_ORIGINS,
    SENTRY_DSN,
    SENTRY_TRACES_SAMPLE_RATE,
    WAITRESS_THREADS,
    WAITRESS_CHANNEL_TIMEOUT,
    WAITRESS_CONNECTION_LIMIT
)

# 导入数据库模型
from models import db
from models import KnowledgeCategory

# 导入路由
from routes.admin_routes import admin_bp
from routes.user_routes import user_bp
from routes.consumption_routes import admin_bp_consumption

# 导入WebSocket
from websocket.chat_ws import register_websocket

# 导入RAG服务
from services.rag_service import get_knowledge_processor


def _check_knowledge_base():
    """启动时仅检查知识库状态，不自动构建"""
    rag = get_knowledge_processor()
    count = rag.get_document_count()
    print(f"\n[RAG] 知识库状态：共 {count} 个文档块（请通过管理后台手动同步向量库）\n")


def create_app():
    """创建并配置Flask应用"""
    app = Flask(__name__)

    # ===== 错误追踪（Sentry，DSN 留空时禁用） =====
    if SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[FlaskIntegration()],
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        )
        logger.info("[Sentry] 错误追踪已启用")

    # ===== 请求追踪（request_id 注入日志） =====
    init_request_tracking(app)

    # ===== 基础配置 =====
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS
    # 【高可用】SQLite busy_timeout 15s：worker 与请求线程并发写时排队等待而非立刻报错
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 15}}
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH  # 从环境变量读取，默认10MB
    app.config["SESSION_TYPE"] = SESSION_TYPE  # 从环境变量读取，默认filesystem
    app.config["STARTED_AT"] = __import__("time").time()  # 供 /metrics 计算 uptime

    # ===== 跨域配置 =====
    # CORS_ORIGINS 支持逗号分隔的多来源列表
    _cors_origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()] if isinstance(CORS_ORIGINS, str) else CORS_ORIGINS
    CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": _cors_origins}})

    # ===== 安全响应头 =====
    @app.after_request
    def _set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # ===== 初始化数据库 =====
    db.init_app(app)

    # ===== 注册蓝图 =====
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp_consumption)

    # ===== 注册WebSocket =====
    sock = Sock(app)
    register_websocket(app, sock)

    # ===== 图片静态文件路由 =====
    @app.route('/uploads/<path:filename>')
    def serve_uploaded_file(filename):
        """提供上传文件的静态访问"""
        return send_from_directory(UPLOAD_FOLDER, filename)

    # ===== 健康检查 =====
    @app.route("/api/health")
    def health_check():
        """健康检查接口"""
        return jsonify({
            "status": "ok",
            "message": "灵山胜境AI数字人导游系统运行中",
            "version": "1.0.0"
        })

    # ===== 创建上传目录 =====
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # ===== 确保数据库表创建（幂等：仅创建缺失的表，如新增的 user_memory / job） =====
    with app.app_context():
        db.create_all()
        # 【高可用】SQLite 开启 WAL：读写不互斥，提升并发可靠性（设置一次即持久生效）
        try:
            mode = db.session.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL")).scalar()
            logger.info(f"[DB] SQLite journal_mode={mode}")
        except Exception as e:
            logger.warning(f"[DB] WAL 设置失败（不影响启动）：{e}")

    # ===== 启动持久化任务队列 worker（消费 graph_build / memory_compress 等后台任务） =====
    from services.job_service import start_worker
    start_worker(app)

    print(f"\n{'='*60}")
    print(f"  灵山胜境AI数字人导游系统 v1.0")
    print(f"  ⏳ 系统正在初始化中，请耐心等待...")
    print(f"{'='*60}\n")

    return app


# ======================== 应用入口 ========================
app = create_app()


if __name__ == "__main__":
    # 在一切初始化之前设置 HF_TOKEN，确保所有模型下载都使用认证
    from config import HF_TOKEN
    import os
    os.environ.setdefault("HF_TOKEN", HF_TOKEN)

    # 启动前初始化数据库
    with app.app_context():
        db.create_all()
        print("[✓] 数据库表已确保创建")

        # 数据库迁移：给已有 user 表添加 digital_human_id 列（如果不存在）
        import sqlalchemy as sa
        try:
            inspector = sa.inspect(db.engine)
            user_columns = [c['name'] for c in inspector.get_columns('user')]
            if 'digital_human_id' not in user_columns:
                db.session.execute(sa.text('ALTER TABLE "user" ADD COLUMN digital_human_id INTEGER DEFAULT 1'))
                db.session.commit()
                print("[✓] 数据库迁移：user 表已添加 digital_human_id 列")
        except Exception as e:
            print(f"[!] 数据库迁移检查（可忽略）: {e}")

        # 检查是否需要初始化默认数据
        from models import Admin, DigitalHuman
        from config import DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD

        # 【安全】默认密码未配置时不创建默认管理员，避免弱口令后门
        if DEFAULT_ADMIN_PASSWORD and not Admin.query.filter_by(username=DEFAULT_ADMIN_USERNAME).first():
            admin = Admin(username=DEFAULT_ADMIN_USERNAME)
            admin.set_password(DEFAULT_ADMIN_PASSWORD)
            db.session.add(admin)
            print(f"[✓] 默认管理员已创建：{DEFAULT_ADMIN_USERNAME}")
        elif not DEFAULT_ADMIN_PASSWORD:
            print("[!] 未配置 DEFAULT_ADMIN_PASSWORD，跳过默认管理员创建（请通过环境变量设置）")

        # 初始化默认数字人（model_path = LiveTalking data/avatars/ 下的文件夹名）
        if DigitalHuman.query.count() == 0:
            default_dh = [
                DigitalHuman(name="灵韵（默认导游）", model_path="wav2lip256_avatar1", is_active=True),
                DigitalHuman(name="慧心（禅意导游）", model_path="wav2lip256_avatar1", default_speed=0.9, default_pitch=1.1, default_voice="zh-CN-XiaoyiNeural", is_active=True),
                DigitalHuman(name="明远（文化导游）", model_path="wav2lip256_avatar1", default_speed=1.1, default_pitch=0.9, default_voice="zh-CN-YunxiNeural", is_active=True),
            ]
            for dh in default_dh:
                db.session.add(dh)
            print(f"[✓] 默认数字人已创建（请在管理后台更新 Avatar文件夹 为你实际的 avatar 目录名）")

        # 数据库迁移：给已有 chat_log 表添加 image_urls 列（如果不存在）
        import sqlalchemy as sa
        try:
            inspector = sa.inspect(db.engine)
            chat_log_columns = [c['name'] for c in inspector.get_columns('chat_log')]
            if 'image_urls' not in chat_log_columns:
                db.session.execute(sa.text('ALTER TABLE "chat_log" ADD COLUMN image_urls TEXT'))
                db.session.commit()
                print("[✓] 数据库迁移：chat_log 表已添加 image_urls 列")
        except Exception as e:
            print(f"[!] 数据库迁移检查（可忽略）: {e}")

        # 初始化知识分类
        KnowledgeCategory.init_defaults()

        # 数据库迁移：给已有 route 表添加 bg_image 列（如果不存在）
        import sqlalchemy as sa
        try:
            inspector = sa.inspect(db.engine)
            route_columns = [c['name'] for c in inspector.get_columns('route')]
            if 'bg_image' not in route_columns:
                db.session.execute(sa.text('ALTER TABLE "route" ADD COLUMN bg_image VARCHAR(512)'))
                db.session.commit()
                print("[✓] 数据库迁移：route 表已添加 bg_image 列")
        except Exception as e:
            print(f"[!] 数据库迁移检查（可忽略）: {e}")

        # 迁移硬编码路线到数据库（仅首次运行时）
        from routes.admin_routes import seed_routes_from_preserved
        seeded = seed_routes_from_preserved()
        if seeded > 0:
            print(f"[✓] 已从硬编码数据迁移 {seeded} 条路线到数据库")

        # 生成/更新路线主题图片（PIL，仅首次或无图片时）
        try:
            from scripts.seed_route_images import seed_route_images
            img_count = seed_route_images()
            if img_count > 0:
                print(f"[✓] 已生成 {img_count} 张路线主题图片")
        except Exception as e:
            print(f"[!] 路线图片生成失败（不影响启动）: {e}")

        db.session.commit()

        # 检查知识库状态（不再自动构建，请通过管理后台手动同步）
        _check_knowledge_base()

    # 预加载 ASR 模型（避免首次语音识别等待，首次加载可能需要较长时间）
    from services.asr_service import get_asr_service
    asr = get_asr_service()
    print("[ASR] 正在加载语音识别模型（首次加载可能需要 2-3分钟，请耐心等待）...")
    print("[ASR] 提示：如网络较慢，建议使用 HuggingFace 镜像加速下载（详见配置文件）或挂加速器下载")
    asr._load_model()
    print("[✓] ASR 模型已预加载\n")

    # 打印启动完成信息
    print(f"\n{'='*60}")
    print(f"  ✅ 系统初始化完成，服务已就绪！")
    print(f"  Flask服务器启动: http://{FLASK_HOST}:{FLASK_PORT}")
    print(f"  WebSocket服务: ws://{FLASK_HOST}:{FLASK_PORT}/ws/chat")
    print(f"  数据库: SQLite (lingshan.db)")
    print(f"{'='*60}\n")

    # ===== 启动服务器 =====
    # 生产环境使用 waitress（多线程 WSGI），开发环境仍用 Flask 自带
    if FLASK_DEBUG:
        app.run(host=FLASK_HOST, port=FLASK_PORT, debug=True, threaded=True)
    else:
        from waitress import serve
        threads = WAITRESS_THREADS or (os.cpu_count() or 4) * 4
        logger.info(f"[Server] waitress 启动：threads={threads}")
        serve(
            app,
            host=FLASK_HOST,
            port=FLASK_PORT,
            threads=threads,
            channel_timeout=WAITRESS_CHANNEL_TIMEOUT,
            connection_limit=WAITRESS_CONNECTION_LIMIT,
        )