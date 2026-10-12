"""
==============================================================
数据库模型定义
使用 Flask-SQLAlchemy ORM 管理
密码存储强制使用 Werkzeug 哈希加密
==============================================================
"""

import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ======================== 1. 管理员表 ========================
class Admin(db.Model):
    """管理员账号表"""
    __tablename__ = "admin"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False, comment="管理员账号")
    password_hash = db.Column(db.String(256), nullable=False, comment="密码哈希值")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")

    def set_password(self, password: str):
        """使用 Werkzeug 加密存储密码"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """校验密码"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        return f"<Admin {self.username}>"


# ======================== 2. 游客用户表 ========================
class User(db.Model):
    """游客用户表"""
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False, comment="用户名")
    password_hash = db.Column(db.String(256), nullable=False, comment="登录密码哈希")
    phone = db.Column(db.String(20), nullable=True, comment="手机号")
    email = db.Column(db.String(128), nullable=True, comment="邮箱")
    registered_at = db.Column(db.DateTime, default=datetime.now, comment="注册时间")
    digital_human_id = db.Column(db.Integer, default=1, comment="用户选中的数字人ID")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "phone": self.phone,
            "email": self.email,
            "registered_at": self.registered_at.strftime("%Y-%m-%d %H:%M:%S"),
            "digital_human_id": self.digital_human_id
        }

    def __repr__(self):
        return f"<User {self.username}>"


# ======================== 3. 对话日志表 ========================
class ChatLog(db.Model):
    """对话日志表 —— 记录每一次用户与AI数字人的完整问答"""
    __tablename__ = "chat_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(64), default="", comment="会话ID（同一会话的多轮对话共享）")
    user_id = db.Column(db.Integer, nullable=False, comment="用户唯一标识")
    question_text = db.Column(db.Text, nullable=False, comment="用户提问文本")
    answer_text = db.Column(db.Text, nullable=False, comment="AI完整回答文本")
    question_time = db.Column(db.DateTime, default=datetime.now, comment="提问时间")
    emotion_label = db.Column(db.String(32), default="平静", comment="AI回复情绪标签（平静/微笑/热情）")
    voice_duration = db.Column(db.Float, default=0.0, comment="语音播放时长（秒）")
    digital_human_id = db.Column(db.Integer, default=1, comment="使用数字人形象ID")
    tts_voice = db.Column(db.String(64), default="zh-CN-XiaoxiaoNeural", comment="使用TTS音色ID")
    image_path = db.Column(db.String(256), nullable=True, comment="用户上传的图片路径（可选，兼容旧数据）")
    image_urls = db.Column(db.Text, nullable=True, comment="用户上传的图片URL列表（JSON数组）")
    route_data = db.Column(db.Text, nullable=True, comment="路线规划JSON数据（可选）")

    def to_dict(self):
        image_urls = None
        if self.image_urls:
            try:
                image_urls = json.loads(self.image_urls)
            except Exception:
                image_urls = None
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "question_time": self.question_time.strftime("%Y-%m-%d %H:%M:%S"),
            "emotion_label": self.emotion_label,
            "voice_duration": self.voice_duration,
            "digital_human_id": self.digital_human_id,
            "tts_voice": self.tts_voice,
            "image_path": self.image_path,
            "image_urls": image_urls,
            "route_data": json.loads(self.route_data) if self.route_data else None
        }

    def __repr__(self):
        return f"<ChatLog {self.id} by user {self.user_id}>"


# ======================== 3b. 用户长期记忆表 ========================
class UserMemory(db.Model):
    """用户长期记忆表 —— memoryAgent 持久化存储（会话摘要/用户画像/关键事实）
    合规边界：仅存业务相关信息（景点偏好、出行习惯等），不存敏感个人数据；
    用户可通过接口查看与一键清除自己的全部记忆。
    """
    __tablename__ = "user_memory"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True, comment="用户ID（游客为0，共享公共记忆池）")
    memory_type = db.Column(db.String(32), nullable=False, comment="记忆类型：summary=会话摘要 / profile=用户偏好画像 / fact=关键事实")
    content = db.Column(db.Text, nullable=False, comment="记忆内容（LLM 压缩后的关键信息）")
    source_session_id = db.Column(db.String(64), default="", comment="来源会话ID（summary 类型用于去重）")
    is_active = db.Column(db.Boolean, default=True, comment="是否有效（软删除标记）")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 向量库中的文档ID（与 Chroma lingshan_user_memory 集合同步）
    @property
    def vector_id(self):
        return f"mem_{self.user_id}_{self.id}"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "source_session_id": self.source_session_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def __repr__(self):
        return f"<UserMemory {self.id} type={self.memory_type} by user {self.user_id}>"


# ======================== 4. 知识分类表 ========================
class KnowledgeCategory(db.Model):
    """知识分类表 —— 管理知识内容的分类信息"""
    __tablename__ = "knowledge_category"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), unique=True, nullable=False, comment="分类名称")
    code = db.Column(db.String(32), unique=True, nullable=False, comment="分类编码")
    description = db.Column(db.String(256), nullable=True, comment="分类描述")
    icon = db.Column(db.String(64), default="", comment="图标类名")
    sort_order = db.Column(db.Integer, default=0, comment="排序权重")
    is_active = db.Column(db.Boolean, default=True, comment="是否启用")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")

    # 支持的录入字段模板
    FIELD_TEMPLATES = {
        "faq": ["question", "answer", "doc_source"],
        "scene_intro": ["title", "content", "tags"],
        "history": ["title", "period", "content", "tags"],
        "basic_info": ["title", "content", "tags"],
        "route": ["title", "content", "tags"],
    }

    DEFAULT_CATEGORIES = [
        {"name": "常见问答", "code": "faq", "description": "游客常见问题的问答对", "icon": "ChatDotRound", "sort_order": 1},
        {"name": "景点讲解词", "code": "scene_intro", "description": "各景点的详细讲解文案", "icon": "LocationInformation", "sort_order": 2},
        {"name": "文史资料", "code": "history", "description": "景区历史文化背景资料", "icon": "Document", "sort_order": 3},
        {"name": "基本信息", "code": "basic_info", "description": "门票、交通、开放时间等", "icon": "InfoFilled", "sort_order": 4},
        {"name": "游览路线", "code": "route", "description": "推荐游览路线规划", "icon": "Connection", "sort_order": 5},
    ]

    @classmethod
    def init_defaults(cls):
        """初始化默认分类"""
        if cls.query.count() > 0:
            return
        for cat in cls.DEFAULT_CATEGORIES:
            cls.query.session.add(cls(
                name=cat["name"],
                code=cat["code"],
                description=cat["description"],
                icon=cat["icon"],
                sort_order=cat["sort_order"]
            ))
        cls.query.session.commit()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "icon": self.icon,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "field_templates": self.FIELD_TEMPLATES.get(self.code, ["title", "content"]),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        return f"<KnowledgeCategory {self.name}>"


# ======================== 5. 通用知识库表 ========================
class Knowledge(db.Model):
    """通用知识库表 —— 支持多类型知识内容管理"""
    __tablename__ = "knowledge"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category_id = db.Column(db.Integer, db.ForeignKey("knowledge_category.id"), nullable=False, comment="分类ID")
    title = db.Column(db.String(256), nullable=False, comment="标题/问题")
    content = db.Column(db.Text, nullable=False, comment="内容/答案")
    tags = db.Column(db.String(512), default="", comment="标签（逗号分隔）")
    source_file = db.Column(db.String(256), nullable=True, comment="来源文件路径")
    keywords = db.Column(db.String(512), default="", comment="关键词（逗号分隔）")
    version = db.Column(db.Integer, default=1, comment="版本号")
    vector_sync = db.Column(db.Boolean, default=False, comment="向量库同步状态")
    is_active = db.Column(db.Boolean, default=True, comment="是否启用")
    sort_order = db.Column(db.Integer, default=0, comment="排序权重")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联分类
    category = db.relationship("KnowledgeCategory", backref=db.backref("knowledge_list", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "category": self.category.to_dict() if self.category else None,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "source_file": self.source_file,
            "keywords": self.keywords,
            "version": self.version,
            "vector_sync": self.vector_sync,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def __repr__(self):
        return f"<Knowledge {self.id}: {self.title[:30]}>"


# ======================== 5b. 知识图谱三元组表（GraphRAG） ========================
class KnowledgeTriple(db.Model):
    """知识图谱三元组 —— 从知识库内容中由 LLM 抽取的 (头实体, 关系, 尾实体)
    用于知识图谱增强 RAG：查询时按实体做邻域扩展，把向量检索命中的知识点关联起来。
    """
    __tablename__ = "knowledge_triple"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    knowledge_id = db.Column(db.Integer, db.ForeignKey("knowledge.id", ondelete="CASCADE"),
                             nullable=True, comment="来源知识条目ID（可为空，表示来自文档分块）")
    head = db.Column(db.String(128), nullable=False, index=True, comment="头实体")
    relation = db.Column(db.String(64), nullable=False, comment="关系")
    tail = db.Column(db.String(128), nullable=False, index=True, comment="尾实体")
    is_active = db.Column(db.Boolean, default=True, comment="是否有效（软删除）")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")

    def to_dict(self):
        return {
            "id": self.id,
            "knowledge_id": self.knowledge_id,
            "head": self.head,
            "relation": self.relation,
            "tail": self.tail,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def __repr__(self):
        return f"<KnowledgeTriple {self.head}-{self.relation}-{self.tail}>"


# ======================== 6. 知识版本历史表 ========================
class KnowledgeVersion(db.Model):
    """知识版本历史表 —— 记录知识条目的历史版本"""
    __tablename__ = "knowledge_version"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    knowledge_id = db.Column(db.Integer, db.ForeignKey("knowledge.id", ondelete="CASCADE"), nullable=False, comment="知识条目ID")
    version = db.Column(db.Integer, nullable=False, comment="版本号")
    title = db.Column(db.String(256), nullable=False, comment="标题/问题")
    content = db.Column(db.Text, nullable=False, comment="内容/答案")
    tags = db.Column(db.String(512), default="", comment="标签")
    keywords = db.Column(db.String(512), default="", comment="关键词")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")

    def to_dict(self):
        return {
            "id": self.id,
            "knowledge_id": self.knowledge_id,
            "version": self.version,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "keywords": self.keywords,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def __repr__(self):
        return f"<KnowledgeVersion {self.knowledge_id} v{self.version}>"


# ======================== 7. 数字人配置表 ========================
class DigitalHuman(db.Model):
    """数字人配置表 —— 管理Live2D数字人形象与参数"""
    __tablename__ = "digital_human"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(128), nullable=False, comment="数字人名称")
    model_path = db.Column(db.String(256), nullable=False, comment="Live2D模型文件存储路径（相对路径）")
    personality = db.Column(db.Text, nullable=True, comment="数字人性格描述（传递给大模型的风格指令）")
    default_speed = db.Column(db.Float, default=1.0, comment="默认语速（0.5-2.0）")
    default_pitch = db.Column(db.Float, default=1.0, comment="默认语调（0.5-2.0）")
    default_voice = db.Column(db.String(64), default="zh-CN-XiaoxiaoNeural", comment="默认音色")
    is_active = db.Column(db.Boolean, default=True, comment="启用状态")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "model_path": self.model_path,
            "personality": self.personality,
            "default_speed": self.default_speed,
            "default_pitch": self.default_pitch,
            "default_voice": self.default_voice,
            "is_active": self.is_active,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        return f"<DigitalHuman {self.name}>"


# ======================== 8. 路线规划表 ========================
class Route(db.Model):
    """路线规划表 —— 动态管理游览路线"""
    __tablename__ = "route"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(100), nullable=False, comment="路线名称")
    subtitle = db.Column(db.String(100), default="", comment="副标题")
    style = db.Column(db.String(50), default="culture", comment="风格编码(culture/nature/family...)")
    style_label = db.Column(db.String(20), default="", comment="风格中文标签")
    tags = db.Column(db.String(512), default="", comment="标签（逗号分隔）")
    icon = db.Column(db.String(10), default="", comment="Emoji图标")
    color = db.Column(db.String(10), default="#5b8c5a", comment="主题色")
    description = db.Column(db.Text, default="", comment="路线描述")
    duration = db.Column(db.String(50), default="", comment="预计时长")
    difficulty = db.Column(db.String(10), default="低", comment="难度(低/中/高)")
    best_time = db.Column(db.String(100), default="", comment="最佳游览时间")
    tips = db.Column(db.Text, default="", comment="小贴士")
    distance_km = db.Column(db.Float, default=0.0, comment="路线距离(km)")
    is_active = db.Column(db.Boolean, default=True, comment="是否启用")
    sort_order = db.Column(db.Integer, default=0, comment="排序权重")
    rating = db.Column(db.Float, default=0.0, comment="推荐指数(0-5)")
    bg_image = db.Column(db.String(512), nullable=True, comment="路线封面/背景图片路径")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    spots = db.relationship("RouteSpot", backref="route", lazy="joined",
                            order_by="RouteSpot.sort_order",
                            cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "style": self.style,
            "style_label": self.style_label,
            "tags": [t.strip() for t in self.tags.split(",") if t.strip()] if self.tags else [],
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            "duration": self.duration,
            "difficulty": self.difficulty,
            "best_time": self.best_time,
            "spots": [s.to_dict() for s in self.spots],
            "tips": self.tips,
            "distance_km": self.distance_km,
            "rating": self.rating,
            "bg_image": self.bg_image,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else "",
        }

    def to_brief(self):
        """精简版返回（不含spots详情）"""
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "style": self.style,
            "style_label": self.style_label,
            "tags": [t.strip() for t in self.tags.split(",") if t.strip()] if self.tags else [],
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            "duration": self.duration,
            "difficulty": self.difficulty,
            "best_time": self.best_time,
            "distance_km": self.distance_km,
            "rating": self.rating,
            "bg_image": self.bg_image,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }

    def __repr__(self):
        return f"<Route {self.id}: {self.title}>"


class RouteSpot(db.Model):
    """路线途经景点表"""
    __tablename__ = "route_spot"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    route_id = db.Column(db.Integer, db.ForeignKey("route.id", ondelete="CASCADE"), nullable=False, comment="所属路线ID")
    name = db.Column(db.String(100), nullable=False, comment="景点名称")
    description = db.Column(db.Text, default="", comment="景点介绍")
    sort_order = db.Column(db.Integer, default=0, comment="排序")
    latitude = db.Column(db.Float, nullable=True, comment="纬度")
    longitude = db.Column(db.Float, nullable=True, comment="经度")

    def to_dict(self):
        return {
            "id": self.id,
            "route_id": self.route_id,
            "name": self.name,
            "description": self.description,
            "sort_order": self.sort_order,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    def __repr__(self):
        return f"<RouteSpot {self.name} (route {self.route_id})>"


# ======================== 9. 持久化任务队列表 ========================
class Job(db.Model):
    """持久化后台任务队列 —— 替代裸 threading.Thread 的非实时任务（建图/记忆压缩等）
    任务先落库再由后台 worker 消费：进程重启后 pending 任务不丢失；
    上次退出时遗留的 running 任务由 worker 启动时回收为 pending 重跑。
    """
    __tablename__ = "job"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(64), nullable=False, index=True, comment="任务类型（graph_build/memory_compress）")
    payload = db.Column(db.Text, default="{}", comment="任务参数（JSON）")
    status = db.Column(db.String(16), default="pending", index=True, comment="pending/running/done/failed")
    retry_count = db.Column(db.Integer, default=0, comment="已重试次数")
    max_retries = db.Column(db.Integer, default=3, comment="最大重试次数")
    run_after = db.Column(db.DateTime, default=datetime.now, index=True, comment="下次可执行时间（指数退避调度）")
    result = db.Column(db.Text, nullable=True, comment="执行结果摘要（JSON）")
    error = db.Column(db.Text, nullable=True, comment="最近一次失败原因")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self):
        return {
            "id": self.id,
            "job_type": self.job_type,
            "payload": json.loads(self.payload) if self.payload else {},
            "status": self.status,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "result": json.loads(self.result) if self.result else None,
            "error": self.error,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else "",
        }

    def __repr__(self):
        return f"<Job {self.id} type={self.job_type} status={self.status}>"
