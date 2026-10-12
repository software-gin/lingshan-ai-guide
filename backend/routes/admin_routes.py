"""
==============================================================
管理员路由模块
提供管理员相关的RESTful API接口
==============================================================
"""

import os
import sys
import json
import re
import time
import requests
from datetime import datetime, timedelta
from functools import wraps
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, session, current_app
from config import UPLOAD_FOLDER, MAX_CONTENT_LENGTH
from models import db, Admin, User, ChatLog, DigitalHuman, Knowledge, KnowledgeCategory, KnowledgeVersion, KnowledgeTriple, Route, RouteSpot
from services.rag_service import get_knowledge_processor
from services.llm_service import get_llm_service
from services.graph_service import build_graph_async

# 创建管理员蓝图
admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ======================== 管理员登录鉴权装饰器 ========================
def admin_required(f):
    """要求管理员登录的装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_id = session.get("admin_id")
        if not admin_id:
            return jsonify({"code": 401, "message": "请先登录"}), 401
        admin = Admin.query.get(admin_id)
        if not admin:
            return jsonify({"code": 401, "message": "管理员不存在"}), 401
        return f(*args, **kwargs)
    return decorated


# ======================== 1. 管理员登录/登出 ========================
@admin_bp.route("/login", methods=["POST"])
def admin_login():
    """管理员登录"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "message": "请求参数不能为空"})

    username = data.get("username", "")
    password = data.get("password", "")

    admin = Admin.query.filter_by(username=username).first()
    if not admin or not admin.check_password(password):
        return jsonify({"code": 401, "message": "账号或密码错误"})

    # 保存登录态
    session["admin_id"] = admin.id
    session["admin_username"] = admin.username

    return jsonify({
        "code": 200,
        "message": "登录成功",
        "data": admin.to_dict()
    })


@admin_bp.route("/logout", methods=["POST"])
@admin_required
def admin_logout():
    """管理员登出"""
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    return jsonify({"code": 200, "message": "已退出登录"})


@admin_bp.route("/info", methods=["GET"])
@admin_required
def admin_info():
    """获取当前管理员信息"""
    admin = Admin.query.get(session["admin_id"])
    return jsonify({"code": 200, "data": admin.to_dict()})


# ======================== 2. 管理员账号管理 ========================
@admin_bp.route("/admins", methods=["GET"])
@admin_required
def list_admins():
    """获取管理员列表"""
    admins = Admin.query.all()
    return jsonify({
        "code": 200,
        "data": [a.to_dict() for a in admins]
    })


@admin_bp.route("/admins", methods=["POST"])
@admin_required
def create_admin():
    """创建新管理员"""
    data = request.get_json()
    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"code": 400, "message": "用户名和密码不能为空"})

    if Admin.query.filter_by(username=data["username"]).first():
        return jsonify({"code": 400, "message": "用户名已存在"})

    admin = Admin(username=data["username"])
    admin.set_password(data["password"])
    db.session.add(admin)
    db.session.commit()

    return jsonify({"code": 200, "message": "创建成功", "data": admin.to_dict()})


# ======================== 3. 游客用户管理 ========================
@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    """获取游客用户列表（支持分页）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    keyword = request.args.get("keyword", "")

    query = User.query
    if keyword:
        query = query.filter(
            User.username.contains(keyword) |
            User.phone.contains(keyword) |
            User.email.contains(keyword)
        )

    pagination = query.order_by(User.registered_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "code": 200,
        "data": {
            "items": [u.to_dict() for u in pagination.items],
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages
        }
    })


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    """删除游客用户"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"code": 404, "message": "用户不存在"})

    db.session.delete(user)
    db.session.commit()
    return jsonify({"code": 200, "message": "删除成功"})


# ======================== 4. 数字人配置管理 ========================
@admin_bp.route("/digital-humans", methods=["GET"])
@admin_required
def list_digital_humans():
    """获取数字人列表"""
    humans = DigitalHuman.query.order_by(DigitalHuman.id).all()
    return jsonify({
        "code": 200,
        "data": [h.to_dict() for h in humans]
    })


@admin_bp.route("/digital-humans", methods=["POST"])
@admin_required
def create_digital_human():
    """创建数字人配置"""
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"code": 400, "message": "数字人名称不能为空"})

    dh = DigitalHuman(
        name=data["name"],
        model_path=data.get("model_path", "/live2d_models/default/"),
        default_speed=data.get("default_speed", 1.0),
        default_pitch=data.get("default_pitch", 1.0),
        default_voice=data.get("default_voice", "zh-CN-XiaoxiaoNeural"),
        is_active=data.get("is_active", True)
    )
    db.session.add(dh)
    db.session.commit()

    return jsonify({"code": 200, "message": "创建成功", "data": dh.to_dict()})


@admin_bp.route("/digital-humans/<int:dh_id>", methods=["PUT"])
@admin_required
def update_digital_human(dh_id):
    """更新数字人配置"""
    dh = DigitalHuman.query.get(dh_id)
    if not dh:
        return jsonify({"code": 404, "message": "数字人不存在"})

    data = request.get_json()
    if data.get("name") is not None:
        dh.name = data["name"]
    if data.get("model_path") is not None:
        dh.model_path = data["model_path"]
    if data.get("default_speed") is not None:
        dh.default_speed = float(data["default_speed"])
    if data.get("default_pitch") is not None:
        dh.default_pitch = float(data["default_pitch"])
    if data.get("default_voice") is not None:
        dh.default_voice = data["default_voice"]
    if data.get("personality") is not None:
        dh.personality = data["personality"]
    if data.get("is_active") is not None:
        dh.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify({"code": 200, "message": "更新成功", "data": dh.to_dict()})


@admin_bp.route("/digital-humans/<int:dh_id>", methods=["DELETE"])
@admin_required
def delete_digital_human(dh_id):
    """删除数字人配置"""
    dh = DigitalHuman.query.get(dh_id)
    if not dh:
        return jsonify({"code": 404, "message": "数字人不存在"})

    db.session.delete(dh)
    db.session.commit()
    return jsonify({"code": 200, "message": "删除成功"})


# ======================== 4b. 获取 LiveTalking 已生成的 Avatar 列表（代理远端） ========================
@admin_bp.route("/digital-humans/avatars-on-disk", methods=["GET"])
@admin_required
def list_avatars_on_disk():
    """从 LiveTalking 服务器获取所有可用的 avatar 文件夹列表"""
    import logging
    log = logging.getLogger(__name__)
    from config import LIVETALKING_AVATARS_API_URL

    try:
        resp = requests.get(LIVETALKING_AVATARS_API_URL, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return jsonify({"code": 200, "data": data.get("data", [])})
        log.warning(f"[Avatar扫描] 远端响应异常: {resp.status_code}")
    except requests.RequestException as e:
        log.warning(f"[Avatar扫描] 无法连接 LiveTalking 服务: {e}")

    return jsonify({"code": 200, "data": []})


# ======================== 4c. 头像图片服务（代理远端 LiveTalking） ========================
from flask import Response

@admin_bp.route("/digital-humans/avatars/<folder>/preview", methods=["GET"])
@admin_required
def get_avatar_preview(folder):
    """
    从 LiveTalking 服务器获取指定 avatar 的第一张预览图，代理返回给前端
    """
    from config import LIVETALKING_AVATARS_API_URL

    url = f"{LIVETALKING_AVATARS_API_URL}/{folder}/preview"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200 and resp.headers.get('Content-Type', '').startswith('image/'):
            return Response(resp.content, mimetype=resp.headers['Content-Type'])
        elif resp.status_code == 404:
            abort(404, "未找到头像图片")
        else:
            abort(resp.status_code, "头像获取失败")
    except requests.RequestException:
        abort(502, "无法连接 LiveTalking 服务")


# ======================== 5. 知识库管理 ========================
@admin_bp.route("/knowledge", methods=["GET"])
@admin_required
def list_knowledge():
    """旧版接口，重定向至新版 /knowledge/list"""
    return list_knowledge_v2()


@admin_bp.route("/knowledge", methods=["POST"])
@admin_required
def create_knowledge():
    """旧版接口，重定向至新版 /knowledge/item"""
    return create_knowledge_v2()


@admin_bp.route("/knowledge/<int:k_id>", methods=["PUT"])
@admin_required
def update_knowledge(k_id):
    """旧版接口，重定向至新版 /knowledge/item/<id>"""
    return update_knowledge_v2(k_id)


@admin_bp.route("/knowledge/<int:k_id>", methods=["DELETE"])
@admin_required
def delete_knowledge(k_id):
    """旧版接口，重定向至新版 /knowledge/item/<id>"""
    return delete_knowledge_v2(k_id)


def _deduplicate_knowledge() -> int:
    """
    去重知识库中的重复条目
    以 (source_file, content) 为唯一键，保留最早创建的条目
    返回删除的重复条目数
    """
    try:
        # 查询所有条目，按ID升序排列（保留最早的）
        all_entries = Knowledge.query.order_by(Knowledge.id.asc()).all()
        
        seen_keys = {}  # (source_file, content) -> id
        duplicate_ids = []
        
        for entry in all_entries:
            key = (entry.source_file or '', entry.content)
            if key in seen_keys:
                duplicate_ids.append(entry.id)
            else:
                seen_keys[key] = entry.id
        
        if duplicate_ids:
            Knowledge.query.filter(Knowledge.id.in_(duplicate_ids)).delete(synchronize_session=False)
            db.session.commit()
            print(f"[RAG] 已删除 {len(duplicate_ids)} 条重复知识条目")
        
        return len(duplicate_ids)
    except Exception as e:
        print(f"[RAG] 去重失败：{e}")
        try:
            db.session.rollback()
        except:
            pass
        return 0


def _cleanup_file_derived_knowledge():
    """
    删除由文档文件自动生成的Knowledge条目
    用于重建向量库时，让build_knowledge_base()能从文件重新创建
    """
    try:
        from config import KOWLEDGE_DIR
        if not os.path.exists(KOWLEDGE_DIR):
            return
        for filename in os.listdir(KOWLEDGE_DIR):
            file_path = os.path.join(KOWLEDGE_DIR, filename)
            if os.path.isfile(file_path):
                Knowledge.query.filter_by(source_file=filename).delete()
        db.session.commit()
        print(f"[RAG] 已清理文件衍生的知识条目")
    except Exception as e:
        print(f"[RAG] 清理文件衍生条目失败：{e}")
        try:
            db.session.rollback()
        except:
            pass


@admin_bp.route("/knowledge/sync", methods=["POST"])
@admin_required
def sync_knowledge():
    """一键同步知识库到向量库（自动去重，防止重复同步）"""
    try:
        processor = get_knowledge_processor()

        # 0. 去重知识库中的重复条目
        dedup_count = _deduplicate_knowledge()

        # 后台重建知识图谱（GraphRAG），不阻塞向量同步
        try:
            build_graph_async(current_app._get_current_object())
        except RuntimeError:
            pass  # 不在 Flask 请求上下文中时忽略

        # 如果有重复数据被清理，需要重建整个向量库
        if dedup_count > 0:
            print(f"[RAG] 检测到 {dedup_count} 条重复数据，正在重建向量库...")
            
            # 清空向量库
            processor.vector_db.delete_collection()
            
            # 删除之前由文档自动生成的Knowledge条目（使build_knowledge_base能重新处理文件）
            _cleanup_file_derived_knowledge()
            
            # 1. 重新从文档目录构建（此时文件会被完整处理、分块入库）
            # build_knowledge_base 会读取 knowledge/ 目录下的文件，
            # 将文件内容分块后存入向量库，并自动创建对应的 Knowledge 条目
            doc_count = processor.build_knowledge_base()
            
            # 2. 同步知识库中未同步的条目（手动新增的，vector_sync=False）
            unsynced_knowledge = Knowledge.query.filter_by(vector_sync=False, is_active=True).all()
            knowledge_docs = []
            for k in unsynced_knowledge:
                knowledge_docs.append({
                    "id": f"knowledge_{k.id}",
                    "text": f"标题：{k.title}\n内容：{k.content}",
                    "metadata": {
                        "source": k.category.name if k.category else "未知",
                        "type": k.category.code if k.category else "unknown",
                        "id": k.id
                    }
                })
            
            if knowledge_docs:
                processor.vector_db.add_documents(knowledge_docs)
            Knowledge.query.filter_by(vector_sync=False, is_active=True).update({Knowledge.vector_sync: True})
            db.session.commit()

            message = f"向量库同步完成（已清理 {dedup_count} 条重复数据）"
            message += f"，文档{doc_count}条 + 知识库{len(knowledge_docs)}条"

            return jsonify({
                "code": 200,
                "message": message,
                "data": {
                    "doc_count": doc_count,
                    "knowledge_count": len(knowledge_docs),
                    "reverse_sync_count": 0,
                    "dedup_count": dedup_count
                }
            })
        else:
            # 没有重复数据，正常增量同步
            # 0. 如果数据库知识条目为空，但向量库有数据，反向同步到数据库
            existing_knowledge_count = Knowledge.query.count()
            vector_doc_count = processor.vector_db.get_document_count()

            reverse_sync_count = 0
            if existing_knowledge_count == 0 and vector_doc_count > 0:
                reverse_sync_count = _sync_vector_to_database(processor)

            # 1. 同步文档目录（跳过已处理文件）
            doc_count = processor.build_knowledge_base()

            # 2. 同步知识库中未同步的条目
            unsynced_knowledge = Knowledge.query.filter_by(vector_sync=False, is_active=True).all()
            knowledge_docs = []
            for k in unsynced_knowledge:
                knowledge_docs.append({
                    "id": f"knowledge_{k.id}",
                    "text": f"标题：{k.title}\n内容：{k.content}",
                    "metadata": {
                        "source": k.category.name if k.category else "未知",
                        "type": k.category.code if k.category else "unknown",
                        "id": k.id
                    }
                })

            if knowledge_docs:
                processor.vector_db.add_documents(knowledge_docs)
            Knowledge.query.filter_by(vector_sync=False, is_active=True).update({Knowledge.vector_sync: True})
            db.session.commit()

            message = f"向量库同步完成"
            if reverse_sync_count > 0:
                message += f"，从向量库反向同步{reverse_sync_count}条知识到数据库"
            message += f"，文档{doc_count}条 + 知识库{len(knowledge_docs)}条"

            return jsonify({
                "code": 200,
                "message": message,
                "data": {
                    "doc_count": doc_count,
                    "knowledge_count": len(knowledge_docs),
                    "reverse_sync_count": reverse_sync_count,
                    "dedup_count": 0
                }
            })
    except Exception as e:
        return jsonify({"code": 500, "message": f"同步失败：{str(e)}"})


def _sync_vector_to_database(processor):
    """
    将向量库中的文档反向同步到数据库知识表
    用于修复数据库为空但向量库有数据的情况
    """
    try:
        vd = processor.vector_db
        if vd.collection is None:
            return 0

        # 获取向量库中所有文档
        all_docs = vd.collection.get()
        if not all_docs or not all_docs.get("documents"):
            return 0

        docs = all_docs["documents"]
        metadatas = all_docs.get("metadatas", [])
        ids = all_docs.get("ids", [])

        count = 0
        for i, doc_text in enumerate(docs):
            doc_id = ids[i] if i < len(ids) else str(i)
            metadata = metadatas[i] if i < len(metadatas) else {}
            
            # 跳过已存在的文档（通过ID判断）
            if Knowledge.query.filter_by(source_file=doc_id).first():
                continue

            source = metadata.get("source", "knowledge_base")
            
            # 检测分类
            detected_cat_code = _detect_category_for_sync(doc_text, metadata)
            cat = KnowledgeCategory.query.filter_by(code=detected_cat_code).first()
            if not cat:
                cat = KnowledgeCategory.query.filter_by(code="basic_info").first()
            
            # 提取关键词
            keywords = _extract_keywords_for_sync(doc_text)
            
            # 从文档内容提取标题（前50字符）
            title = doc_text[:50]
            if len(doc_text) > 50:
                title += "..."
            
            knowledge = Knowledge(
                category_id=cat.id if cat else 1,
                title=title,
                content=doc_text[:5000],
                tags=", ".join(keywords),
                source_file=doc_id,
                keywords=", ".join(keywords),
                vector_sync=True,
                is_active=True
            )
            db.session.add(knowledge)
            count += 1

        if count > 0:
            db.session.commit()
            print(f"[RAG] 从向量库反向同步 {count} 条知识到数据库")
        
        return count
    except Exception as e:
        print(f"[RAG] 反向同步失败：{e}")
        try:
            db.session.rollback()
        except:
            pass
        return 0


def _detect_category_for_sync(text: str, metadata: Dict) -> str:
    """根据文本和元数据检测知识分类"""
    type_from_meta = metadata.get("type", "")
    if type_from_meta in ["faq", "scene_intro", "history", "basic_info", "route"]:
        return type_from_meta
    
    scores = {}
    keywords_map = {
        "scene_intro": ["景点", "讲解", "介绍", "景观", "建筑", "佛像", "大佛", "梵宫", "坛城"],
        "history": ["历史", "文化", "古代", "佛教", "传统", "典故", "由来", "传说"],
        "basic_info": ["门票", "交通", "停车", "开放时间", "价格", "游玩时间", "费用"],
        "route": ["路线", "行程", "攻略", "游览", "推荐路线"],
        "faq": ["如何", "怎么", "什么", "吗", "?", "？"]
    }
    
    for cat_code, keywords in keywords_map.items():
        scores[cat_code] = sum(1 for kw in keywords if kw in text)
    
    detected = max(scores, key=scores.get)
    if scores[detected] == 0:
        return "basic_info"
    return detected


def _extract_keywords_for_sync(text: str) -> List[str]:
    """从文本中提取关键词"""
    keywords = []
    all_keywords = [
        "灵山", "大佛", "梵宫", "九龙灌浴", "拈花湾", "佛足坛",
        "门票", "交通", "路线", "表演", "素斋", "住宿",
        "文化", "历史", "景点", "参观", "推荐", "攻略", "预约"
    ]
    for kw in all_keywords:
        if kw in text and kw not in keywords:
            keywords.append(kw)
    return keywords[:8]


# ======================== 知识图谱（GraphRAG）管理 ========================

@admin_bp.route("/knowledge/graph/build", methods=["POST"])
@admin_required
def build_knowledge_graph():
    """手动触发知识图谱构建（后台异步执行：LLM 逐条抽取三元组）"""
    data = request.get_json(silent=True) or {}
    limit = data.get("limit")
    try:
        limit = int(limit) if limit else None
    except (TypeError, ValueError):
        limit = None

    job_id = build_graph_async(current_app._get_current_object(), limit=limit)
    scope = f"前 {limit} 条" if limit else "全量"
    return jsonify({
        "code": 200,
        "message": f"知识图谱构建已启动（持久化队列后台执行，{scope}）",
        "data": {"async": True, "limit": limit, "job_id": job_id}
    })


@admin_bp.route("/knowledge/graph/build", methods=["GET"])
@admin_required
def knowledge_graph_build_status():
    """查询知识图谱统计（三元组数、实体数、高频关系/实体、样例）"""
    try:
        triples = KnowledgeTriple.query.filter_by(is_active=True).all()
        entities = set()
        relations = {}
        degree = {}
        for t in triples:
            entities.add(t.head)
            entities.add(t.tail)
            relations[t.relation] = relations.get(t.relation, 0) + 1
            degree[t.head] = degree.get(t.head, 0) + 1
            degree[t.tail] = degree.get(t.tail, 0) + 1

        top_relations = sorted(relations.items(), key=lambda x: -x[1])[:10]
        top_entities = sorted(degree.items(), key=lambda x: -x[1])[:10]

        return jsonify({
            "code": 200,
            "data": {
                "triple_count": len(triples),
                "entity_count": len(entities),
                "top_relations": [{"relation": r, "count": c} for r, c in top_relations],
                "top_entities": [{"entity": e, "degree": d} for e, d in top_entities],
                "sample_triples": [t.to_dict() for t in triples[:10]],
            }
        })
    except Exception as e:
        return jsonify({"code": 500, "message": f"查询失败：{str(e)}"})


# ======================== 持久化任务队列状态 ========================

@admin_bp.route("/jobs", methods=["GET"])
@admin_required
def list_jobs():
    """查询持久化任务队列（默认最近 50 条，可用 ?type=graph_build 过滤）"""
    from services.job_service import list_recent_jobs
    job_type = request.args.get("type")
    return jsonify({"code": 200, "data": list_recent_jobs(job_type=job_type)})


@admin_bp.route("/metrics", methods=["GET"])
@admin_required
def metrics():
    """运行指标：任务队列统计 / LLM token 累计 / 服务 uptime"""
    from models import Job
    from services.llm_service import get_llm_service

    # 任务队列按状态计数
    rows = (db.session.query(Job.status, db.func.count())
            .group_by(Job.status).all())
    job_stats = {status: cnt for status, cnt in rows}

    # LLM token 累计消耗
    try:
        total_tokens = get_llm_service().get_token_usage()
    except Exception:
        total_tokens = 0

    uptime = int(__import__("time").time() - current_app.config.get("STARTED_AT", 0))
    return jsonify({
        "code": 200,
        "data": {
            "uptime_seconds": uptime,
            "jobs": {
                "pending": job_stats.get("pending", 0),
                "running": job_stats.get("running", 0),
                "done": job_stats.get("done", 0),
                "failed": job_stats.get("failed", 0),
            },
            "llm_total_tokens": total_tokens,
        }
    })


@admin_bp.route("/knowledge/upload", methods=["POST"])
@admin_required
def upload_knowledge_file():
    """上传知识文档文件，自动提取内容并入库"""
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "未上传文件"})

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"code": 400, "message": "文件为空"})

    # 检查文件扩展名
    allowed_extensions = {"docx", "xlsx", "txt", "pdf"}
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_extensions:
        return jsonify({"code": 400, "message": f"不支持的文件类型，仅支持: {', '.join(allowed_extensions)}"})

    # 保存上传文件到knowledge目录
    knowledge_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "../knowledge")
    knowledge_dir = os.path.abspath(knowledge_dir)
    os.makedirs(knowledge_dir, exist_ok=True)

    file_path = os.path.join(knowledge_dir, file.filename)
    file.save(file_path)

    # 提取文本并入库
    try:
        processor = get_knowledge_processor()

        # 使用结构化解析：根据文件类型解析为多个知识条目
        if ext == "docx":
            from docx import Document
            doc = Document(file_path)
            entries = processor._parse_docx_to_entries(file_path, file.filename)
            if not entries:
                # 回退：如果结构化解析失败，使用简单文本模式
                text = processor.extract_text_from_docx(file_path)
                detected_category = processor._detect_file_category(file.filename)
                entries = [{
                    "title": f"【文件】{file.filename}",
                    "content": text,
                    "filename": file.filename,
                    "category": detected_category
                }]
        elif ext == "xlsx":
            entries = processor._parse_xlsx_to_entries(file_path, file.filename)
            if not entries:
                text = processor.extract_text_from_xlsx(file_path, target_spots=["灵山", "灵山胜境", "拈花湾"])
                detected_category = processor._detect_file_category(file.filename)
                entries = [{
                    "title": f"【文件】{file.filename}",
                    "content": text,
                    "filename": file.filename,
                    "category": detected_category
                }]
        elif ext == "txt":
            entries = processor._parse_txt_to_entries(file_path, file.filename)
            if not entries:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                detected_category = processor._detect_file_category(file.filename)
                entries = [{
                    "title": f"【文件】{file.filename}",
                    "content": text,
                    "filename": file.filename,
                    "category": detected_category
                }]
        elif ext == "pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                text = "\n".join([page.get_text() for page in doc])
            except ImportError:
                return jsonify({"code": 500, "message": "服务器缺少PyMuPDF库，无法解析PDF文件"})
            except Exception as e:
                return jsonify({"code": 500, "message": f"PDF解析失败：{str(e)}"})
            detected_category = processor._detect_file_category(file.filename)
            entries = [{
                "title": f"【文件】{file.filename}",
                "content": text,
                "filename": file.filename,
                "category": detected_category
            }]
        else:
            return jsonify({"code": 400, "message": f"不支持的文件类型：{ext}"})

        if not entries:
            os.unlink(file_path)
            return jsonify({"code": 400, "message": "文件中未提取到有效文本内容"})

        # 将所有条目的内容分割为文档块，并添加到向量库
        total_chunks = 0
        documents = []
        for entry_idx, entry in enumerate(entries):
            text = entry["content"]
            chunks = processor.split_text_to_chunks(text, chunk_size=200, overlap=50)
            for chunk_idx, chunk in enumerate(chunks):
                # 文档ID包含文件名，便于后续清理
                doc_id = f"upload_{file.filename}_{entry_idx}_{chunk_idx}"
                documents.append({
                    "id": doc_id,
                    "text": chunk,
                    "metadata": {
                        "source": f"文件上传: {file.filename}",
                        "filename": file.filename,
                        "entry_index": entry_idx,
                        "chunk_index": chunk_idx,
                        "total_chunks": len(chunks)
                    }
                })
            total_chunks += len(chunks)

        processor.vector_db.add_documents(documents)

        # 创建多个知识条目（每个结构化段落一个条目）
        category_map = {
            "faq": "faq", "scene_intro": "scene_intro",
            "history": "history", "basic_info": "basic_info", "route": "route"
        }
        
        created_count = 0
        for entry in entries:
            # 使用条目自己的分类，如果没有则检测
            entry_category = entry.get("category", "")
            if not entry_category:
                detected_type = processor._detect_file_category(file.filename)
                entry_category = detected_type
            
            cat = KnowledgeCategory.query.filter_by(code=category_map.get(entry_category, "faq")).first()
            if not cat:
                cat = KnowledgeCategory.query.filter_by(code="faq").first()
            
            if cat:
                keywords = _extract_keywords(entry["content"], top_k=8)
                knowledge = Knowledge(
                    category_id=cat.id,
                    title=entry.get("title", f"【文件】{file.filename}"),
                    content=entry["content"][:2000] + ("..." if len(entry["content"]) > 2000 else ""),
                    tags=", ".join(keywords),
                    source_file=file.filename,
                    keywords=", ".join(keywords),
                    vector_sync=True,
                    is_active=True
                )
                db.session.add(knowledge)
                created_count += 1
        
        db.session.commit()

        return jsonify({
            "code": 200,
            "message": f"文件上传成功，共创建 {created_count} 个知识条目，{total_chunks} 个文档块",
            "data": {
                "entries": created_count,
                "chunks": total_chunks,
                "filename": file.filename
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"code": 500, "message": f"文件处理失败：{str(e)}"})


@admin_bp.route("/knowledge/graph", methods=["GET"])
@admin_required
def knowledge_graph():
    """获取知识库图谱数据（节点和边）- 基于数据库所有有效知识条目"""
    try:
        # 1. 从数据库读取所有有效知识条目
        knowledge_entries = Knowledge.query.filter_by(is_active=True).order_by(Knowledge.category_id).all()

        if not knowledge_entries:
            processor = get_knowledge_processor()
            return jsonify({
                "code": 200,
                "data": {
                    "nodes": [],
                    "edges": [],
                    "doc_count": processor.vector_db.get_document_count() if processor.vector_db.collection else 0
                }
            })

        # 2. 构建节点列表（以标题为标签，去重）
        processor = get_knowledge_processor()
        embedding = processor.vector_db.embedding  # 复用 SemanticEmbedding 实例（语义嵌入）

        nodes = []
        node_labels = set()
        for k in knowledge_entries:
            label = k.title.strip()[:40]  # 截断长标题
            if label in node_labels:
                continue
            node_labels.add(label)

            nodes.append({
                "id": f"knowledge_{k.id}",
                "label": label,
                "text": k.content[:80] if k.content else "",
                "category": k.category.name if k.category else "知识",
                "tags": k.tags or "",
                "category_code": k.category.code if k.category else "unknown"
            })

        # 3. 使用 SemanticEmbedding 计算每个节点的向量
        node_ids = [n["id"] for n in nodes]
        node_embeddings = {}
        for n in nodes:
            text_for_embed = f"{n['label']} {n['text']} {n['tags']}"
            node_embeddings[n["id"]] = embedding.embed(text_for_embed)

        # 4. 计算节点间语义相似度，构建边
        SIMILARITY_THRESHOLD = 0.28
        edges = []
        processed_pairs = set()

        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                id1, id2 = node_ids[i], node_ids[j]
                pair_key = tuple(sorted([id1, id2]))
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)

                sim = _cosine_similarity(node_embeddings[id1], node_embeddings[id2])

                if sim >= SIMILARITY_THRESHOLD:
                    # 同分类节点用分类名，不同分类用"关联"
                    cat_code1 = nodes[i]["category_code"]
                    cat_code2 = nodes[j]["category_code"]
                    if cat_code1 == cat_code2:
                        edge_cat = nodes[i]["category"]
                    else:
                        edge_cat = "关联"

                    edges.append({
                        "source": nodes[i]["label"],
                        "target": nodes[j]["label"],
                        "category": edge_cat,
                        "label": f"sim:{sim:.2f}",
                        "similarity": round(sim, 3)
                    })

        # 按相似度排序，保留Top 120条边防止图过于密集
        edges.sort(key=lambda x: x["similarity"], reverse=True)
        edges = edges[:120]

        # 5. 统计信息
        doc_count = processor.vector_db.get_document_count() if processor.vector_db.collection else 0
        knowledge_count = len(knowledge_entries)

        return jsonify({
            "code": 200,
            "data": {
                "nodes": nodes,
                "edges": edges,
                "doc_count": doc_count,
                "knowledge_count": knowledge_count
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"code": 500, "message": f"获取图谱数据失败：{str(e)}"})


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


@admin_bp.route("/knowledge/stats", methods=["GET"])
@admin_required
def knowledge_stats():
    """获取知识库统计信息"""
    try:
        processor = get_knowledge_processor()
        vd = processor.vector_db
        doc_count = vd.get_document_count() if vd.collection else 0
        knowledge_count = Knowledge.query.filter_by(is_active=True).count()
        category_count = KnowledgeCategory.query.filter_by(is_active=True).count()

        # 按分类统计
        category_stats = {}
        for cat in KnowledgeCategory.query.filter_by(is_active=True).all():
            count = Knowledge.query.filter_by(category_id=cat.id, is_active=True).count()
            category_stats[cat.code] = {"name": cat.name, "count": count}

        return jsonify({
            "code": 200,
            "data": {
                "vector_doc_count": doc_count,
                "knowledge_count": knowledge_count,
                "category_count": category_count,
                "category_stats": category_stats
            }
        })
    except Exception as e:
        return jsonify({"code": 500, "message": f"统计失败：{str(e)}"})


# ======================== 知识库分类管理 ========================
@admin_bp.route("/knowledge/categories", methods=["GET"])
@admin_required
def list_categories():
    """获取知识分类列表"""
    categories = KnowledgeCategory.query.filter_by(is_active=True).order_by(KnowledgeCategory.sort_order).all()
    return jsonify({
        "code": 200,
        "data": [c.to_dict() for c in categories]
    })


@admin_bp.route("/knowledge/categories", methods=["POST"])
@admin_required
def create_category():
    """创建知识分类"""
    data = request.get_json()
    if not data or not data.get("name") or not data.get("code"):
        return jsonify({"code": 400, "message": "分类名称和编码不能为空"})

    existing = KnowledgeCategory.query.filter_by(code=data["code"]).first()
    if existing:
        return jsonify({"code": 400, "message": "分类编码已存在"})

    cat = KnowledgeCategory(
        name=data["name"],
        code=data["code"],
        description=data.get("description", ""),
        icon=data.get("icon", ""),
        sort_order=data.get("sort_order", 0),
        is_active=data.get("is_active", True)
    )
    db.session.add(cat)
    db.session.commit()
    return jsonify({"code": 200, "message": "创建成功", "data": cat.to_dict()})


@admin_bp.route("/knowledge/categories/<int:cat_id>", methods=["PUT"])
@admin_required
def update_category(cat_id):
    """更新知识分类"""
    cat = KnowledgeCategory.query.get(cat_id)
    if not cat:
        return jsonify({"code": 404, "message": "分类不存在"})

    data = request.get_json()
    if data.get("name") is not None:
        cat.name = data["name"]
    if data.get("description") is not None:
        cat.description = data["description"]
    if data.get("icon") is not None:
        cat.icon = data["icon"]
    if data.get("sort_order") is not None:
        cat.sort_order = data["sort_order"]
    if data.get("is_active") is not None:
        cat.is_active = data["is_active"]

    db.session.commit()
    return jsonify({"code": 200, "message": "更新成功", "data": cat.to_dict()})


@admin_bp.route("/knowledge/categories/<int:cat_id>", methods=["DELETE"])
@admin_required
def delete_category(cat_id):
    """删除知识分类"""
    cat = KnowledgeCategory.query.get(cat_id)
    if not cat:
        return jsonify({"code": 404, "message": "分类不存在"})

    # 检查是否有关联的知识条目
    count = Knowledge.query.filter_by(category_id=cat_id).count()
    if count > 0:
        return jsonify({"code": 400, "message": f"该分类下还有 {count} 条知识内容，请先迁移或删除"})

    db.session.delete(cat)
    db.session.commit()
    return jsonify({"code": 200, "message": "删除成功"})


# ======================== 通用知识库管理 ========================
@admin_bp.route("/knowledge/list", methods=["GET"])
@admin_required
def list_knowledge_v2():
    """获取知识库列表（新版，合并展示 knowledge 表 + faq_knowledge 表）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # 筛选条件
    category = request.args.get("category", "")        # 分类编码
    keyword = request.args.get("keyword", "")           # 关键词搜索
    tags = request.args.get("tags", "")                 # 标签筛选
    is_active = request.args.get("is_active")           # 状态筛选
    sort_by = request.args.get("sort_by", "created_at") # 排序字段
    sort_order = request.args.get("sort_order", "desc")  # 排序方向

    query = Knowledge.query

    # 分类筛选
    if category:
        cat = KnowledgeCategory.query.filter_by(code=category).first()
        if cat:
            query = query.filter_by(category_id=cat.id)
        else:
            query = query.filter_by(category_id=-1)

    # 关键词搜索
    if keyword:
        query = query.filter(
            db.or_(
                Knowledge.title.contains(keyword),
                Knowledge.content.contains(keyword),
                Knowledge.tags.contains(keyword),
                Knowledge.keywords.contains(keyword)
            )
        )

    # 标签筛选
    if tags:
        query = query.filter(Knowledge.tags.contains(tags))

    # 状态筛选
    if is_active and is_active.strip():
        query = query.filter_by(is_active=(is_active.lower() in ("true", "1", "yes")))

    # 排序
    SORT_FIELDS = {
        "created_at": Knowledge.created_at,
        "updated_at": Knowledge.updated_at,
        "title": Knowledge.title,
    }
    sort_col = SORT_FIELDS.get(sort_by, Knowledge.created_at)
    if sort_order.lower() == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # SQL 层分页
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for k in pagination.items:
        items.append({
            "id": k.id,
            "category_id": k.category_id,
            "category": k.category.to_dict() if k.category else None,
            "title": k.title,
            "content": k.content,
            "tags": k.tags,
            "source_file": k.source_file or "",
            "keywords": k.keywords,
            "version": k.version,
            "vector_sync": k.vector_sync,
            "is_active": k.is_active,
            "sort_order": k.sort_order,
            "created_at": k.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": k.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return jsonify({
        "code": 200,
        "data": {
            "items": items,
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages
        }
    })


@admin_bp.route("/knowledge/item", methods=["POST"])
@admin_required
def create_knowledge_v2():
    """创建知识条目（新版）"""
    data = request.get_json()
    if not data or not data.get("title") or not data.get("content"):
        return jsonify({"code": 400, "message": "标题和内容不能为空"})

    # 获取分类
    category_id = data.get("category_id")
    if not category_id:
        return jsonify({"code": 400, "message": "请选择知识分类"})

    cat = KnowledgeCategory.query.get(category_id)
    if not cat:
        return jsonify({"code": 404, "message": "知识分类不存在"})

    knowledge = Knowledge(
        category_id=category_id,
        title=data["title"],
        content=data["content"],
        tags=data.get("tags", ""),
        source_file=data.get("source_file", ""),
        keywords=data.get("keywords", ""),
        sort_order=data.get("sort_order", 0),
        is_active=data.get("is_active", True)
    )
    db.session.add(knowledge)
    db.session.commit()

    # 自动添加到向量库
    try:
        processor = get_knowledge_processor()
        processor.vector_db.add_documents([{
            "id": f"knowledge_{knowledge.id}",
            "text": f"标题：{knowledge.title}\n内容：{knowledge.content}",
            "metadata": {"source": cat.name, "type": cat.code, "id": knowledge.id}
        }])
        knowledge.vector_sync = True
        db.session.commit()
    except Exception as e:
        print(f"[Warning] 向量库自动同步失败：{e}")

    return jsonify({"code": 200, "message": "创建成功", "data": knowledge.to_dict()})


@admin_bp.route("/knowledge/item/<int:k_id>", methods=["PUT"])
@admin_required
def update_knowledge_v2(k_id):
    """更新知识条目（新版，带版本控制）"""
    knowledge = Knowledge.query.get(k_id)
    if not knowledge:
        return jsonify({"code": 404, "message": "知识条目不存在"})

    data = request.get_json()

    # 保存版本历史
    version_record = KnowledgeVersion(
        knowledge_id=knowledge.id,
        version=knowledge.version,
        title=knowledge.title,
        content=knowledge.content,
        tags=knowledge.tags,
        keywords=knowledge.keywords
    )
    db.session.add(version_record)

    # 更新字段
    if data.get("category_id") is not None:
        knowledge.category_id = data["category_id"]
    if data.get("title") is not None:
        knowledge.title = data["title"]
    if data.get("content") is not None:
        knowledge.content = data["content"]
    if data.get("tags") is not None:
        knowledge.tags = data["tags"]
    if data.get("keywords") is not None:
        knowledge.keywords = data["keywords"]
    if data.get("sort_order") is not None:
        knowledge.sort_order = data["sort_order"]
    if data.get("is_active") is not None:
        knowledge.is_active = data["is_active"]

    knowledge.version += 1
    knowledge.vector_sync = False  # 标记需要重新同步
    db.session.commit()

    return jsonify({"code": 200, "message": "更新成功", "data": knowledge.to_dict()})


@admin_bp.route("/knowledge/item/<int:k_id>", methods=["DELETE"])
@admin_required
def delete_knowledge_v2(k_id):
    """删除知识条目（新版）"""
    knowledge = Knowledge.query.get(k_id)
    if not knowledge:
        return jsonify({"code": 404, "message": "知识条目不存在"})

    source_file = knowledge.source_file

    # 同时删除版本历史
    KnowledgeVersion.query.filter_by(knowledge_id=k_id).delete()
    db.session.delete(knowledge)
    db.session.commit()

    # 同步清理向量库中对应文档块
    try:
        processor = get_knowledge_processor()
        if source_file:
            # 删除以 "upload_{filename}_" 开头的所有向量文档块
            deleted_count = processor.vector_db.delete_documents_by_id_prefix(f"upload_{source_file}_")
            if deleted_count > 0:
                print(f"[Admin] 已从向量库清理 {deleted_count} 条文档块（文件: {source_file}）")
    except Exception as e:
        print(f"[Warning] 清理向量库失败：{e}")

    return jsonify({"code": 200, "message": "删除成功"})


@admin_bp.route("/knowledge/item/<int:k_id>/versions", methods=["GET"])
@admin_required
def get_knowledge_versions(k_id):
    """获取知识条目的版本历史"""
    knowledge = Knowledge.query.get(k_id)
    if not knowledge:
        return jsonify({"code": 404, "message": "知识条目不存在"})

    versions = KnowledgeVersion.query.filter_by(knowledge_id=k_id).order_by(KnowledgeVersion.version.desc()).all()
    return jsonify({
        "code": 200,
        "data": {
            "current_version": knowledge.version,
            "versions": [v.to_dict() for v in versions]
        }
    })


@admin_bp.route("/knowledge/item/<int:k_id>/restore/<int:version_id>", methods=["POST"])
@admin_required
def restore_knowledge_version(k_id, version_id):
    """恢复到指定版本"""
    knowledge = Knowledge.query.get(k_id)
    if not knowledge:
        return jsonify({"code": 404, "message": "知识条目不存在"})

    version = KnowledgeVersion.query.get(version_id)
    if not version or version.knowledge_id != k_id:
        return jsonify({"code": 404, "message": "版本不存在"})

    # 保存当前版本为历史
    current_record = KnowledgeVersion(
        knowledge_id=knowledge.id,
        version=knowledge.version,
        title=knowledge.title,
        content=knowledge.content,
        tags=knowledge.tags,
        keywords=knowledge.keywords
    )
    db.session.add(current_record)

    # 恢复
    knowledge.title = version.title
    knowledge.content = version.content
    knowledge.tags = version.tags
    knowledge.keywords = version.keywords
    knowledge.version += 1
    knowledge.vector_sync = False
    db.session.commit()

    return jsonify({"code": 200, "message": f"已恢复到版本 v{version.version}", "data": knowledge.to_dict()})


# ======================== 批量操作 ========================
@admin_bp.route("/knowledge/batch/import", methods=["POST"])
@admin_required
def batch_import_knowledge():
    """批量导入知识条目（JSON格式）"""
    data = request.get_json()
    if not data or not isinstance(data.get("items"), list):
        return jsonify({"code": 400, "message": "请提供 items 数组"})

    items = data["items"]
    category_id = data.get("category_id")
    if not category_id:
        return jsonify({"code": 400, "message": "请选择知识分类"})

    cat = KnowledgeCategory.query.get(category_id)
    if not cat:
        return jsonify({"code": 404, "message": "知识分类不存在"})

    created = 0
    failed = 0
    errors = []

    for idx, item in enumerate(items):
        try:
            title = item.get("title", f"条目{idx+1}")
            content = item.get("content", "")
            if not content:
                failed += 1
                errors.append(f"第{idx+1}条：内容不能为空")
                continue

            knowledge = Knowledge(
                category_id=category_id,
                title=title,
                content=content,
                tags=item.get("tags", ""),
                keywords=item.get("keywords", ""),
                is_active=item.get("is_active", True)
            )
            db.session.add(knowledge)
            db.session.flush()
            created += 1
        except Exception as e:
            failed += 1
            errors.append(f"第{idx+1}条：{str(e)}")

    db.session.commit()

    # 批量同步向量库
    if created > 0:
        try:
            processor = get_knowledge_processor()
            batch_docs = []
            for item in items[:created]:
                batch_docs.append({
                    "id": f"knowledge_batch_{idx}",
                    "text": f"标题：{item.get('title', '')}\n内容：{item.get('content', '')}",
                    "metadata": {"source": cat.name, "type": cat.code}
                })
            if batch_docs:
                processor.vector_db.add_documents(batch_docs)
        except Exception as e:
            print(f"[Warning] 批量向量同步失败：{e}")

    return jsonify({
        "code": 200,
        "message": f"批量导入完成：成功{created}条，失败{failed}条",
        "data": {"created": created, "failed": failed, "errors": errors[:10]}
    })


@admin_bp.route("/knowledge/batch/export", methods=["GET"])
@admin_required
def batch_export_knowledge():
    """批量导出知识条目（JSON格式）"""
    category = request.args.get("category", "")
    keyword = request.args.get("keyword", "")

    query = Knowledge.query.filter_by(is_active=True)

    if category:
        cat = KnowledgeCategory.query.filter_by(code=category).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    if keyword:
        query = query.filter(
            db.or_(
                Knowledge.title.contains(keyword),
                Knowledge.content.contains(keyword)
            )
        )

    items = query.order_by(Knowledge.created_at.desc()).all()
    return jsonify({
        "code": 200,
        "data": {
            "items": [
                {
                    "title": k.title,
                    "content": k.content,
                    "tags": k.tags,
                    "keywords": k.keywords,
                    "source_file": k.source_file,
                    "category": k.category.to_dict() if k.category else None
                }
                for k in items
            ]
        }
    })


@admin_bp.route("/knowledge/batch/delete", methods=["POST"])
@admin_required
def batch_delete_knowledge():
    """批量删除知识条目"""
    data = request.get_json()
    if not data or not isinstance(data.get("ids"), list):
        return jsonify({"code": 400, "message": "请提供 ids 数组"})

    ids = data["ids"]
    deleted = 0
    source_files = set()  # 收集需要清理的源文件名
    for k_id in ids:
        k = Knowledge.query.get(k_id)
        if k:
            if k.source_file:
                source_files.add(k.source_file)
            KnowledgeVersion.query.filter_by(knowledge_id=k_id).delete()
            db.session.delete(k)
            deleted += 1
    db.session.commit()

    # 同步清理向量库中对应文档块
    if source_files:
        try:
            processor = get_knowledge_processor()
            total_cleaned = 0
            for source_file in source_files:
                count = processor.vector_db.delete_documents_by_id_prefix(f"upload_{source_file}_")
                total_cleaned += count
            if total_cleaned > 0:
                print(f"[Admin] 已从向量库清理 {total_cleaned} 条文档块（{len(source_files)} 个文件）")
        except Exception as e:
            print(f"[Warning] 批量清理向量库失败：{e}")

    return jsonify({"code": 200, "message": f"已删除 {deleted} 条知识", "data": {"deleted": deleted}})


@admin_bp.route("/knowledge/batch/sync", methods=["POST"])
@admin_required
def batch_sync_knowledge():
    """批量同步未同步的知识到向量库"""
    unsynced = Knowledge.query.filter_by(vector_sync=False, is_active=True).all()
    synced = 0

    try:
        processor = get_knowledge_processor()
        for k in unsynced:
            processor.vector_db.add_documents([{
                "id": f"knowledge_{k.id}",
                "text": f"标题：{k.title}\n内容：{k.content}",
                "metadata": {
                    "source": k.category.name if k.category else "未知",
                    "type": k.category.code if k.category else "unknown",
                    "id": k.id
                }
            }])
            k.vector_sync = True
            synced += 1
        db.session.commit()
    except Exception as e:
        return jsonify({"code": 500, "message": f"同步失败：{str(e)}"})

    return jsonify({"code": 200, "message": f"同步完成，共{synced}条", "data": {"synced": synced}})


@admin_bp.route("/knowledge/search", methods=["GET"])
@admin_required
def search_knowledge():
    """多维度搜索知识条目"""
    keyword = request.args.get("keyword", "")
    category = request.args.get("category", "")
    tags = request.args.get("tags", "")

    if not keyword and not category and not tags:
        return jsonify({"code": 400, "message": "至少提供一个搜索条件"})

    query = Knowledge.query.filter_by(is_active=True)

    if keyword:
        query = query.filter(
            db.or_(
                Knowledge.title.contains(keyword),
                Knowledge.content.contains(keyword),
                Knowledge.tags.contains(keyword),
                Knowledge.keywords.contains(keyword)
            )
        )

    if category:
        cat = KnowledgeCategory.query.filter_by(code=category).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    if tags:
        query = query.filter(Knowledge.tags.contains(tags))

    results = query.order_by(Knowledge.created_at.desc()).limit(50).all()

    return jsonify({
        "code": 200,
        "data": {
            "total": len(results),
            "items": [k.to_dict() for k in results]
        }
    })


@admin_bp.route("/knowledge/detect", methods=["POST"])
@admin_required
def detect_knowledge_type():
    """上传文件后自动检测知识类型并提取关键信息"""
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "未上传文件"})

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"code": 400, "message": "文件为空"})

    # 检查文件扩展名
    allowed_extensions = {"docx", "xlsx", "txt", "pdf"}
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_extensions:
        return jsonify({"code": 400, "message": f"不支持的文件类型，仅支持: {', '.join(allowed_extensions)}"})

    # 保存上传文件
    knowledge_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "../knowledge")
    knowledge_dir = os.path.abspath(knowledge_dir)
    os.makedirs(knowledge_dir, exist_ok=True)

    file_path = os.path.join(knowledge_dir, file.filename)
    file.save(file_path)

    # 提取文本
    try:
        processor = get_knowledge_processor()

        if ext == "docx":
            text = processor.extract_text_from_docx(file_path)
        elif ext == "xlsx":
            text = processor.extract_text_from_xlsx(file_path, target_spots=["灵山", "灵山胜境", "拈花湾"])
        elif ext == "txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif ext == "pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                text = "\n".join([page.get_text() for page in doc])
            except ImportError:
                return jsonify({"code": 500, "message": "服务器缺少PyMuPDF库，无法解析PDF文件"})
            except Exception as e:
                return jsonify({"code": 500, "message": f"PDF解析失败：{str(e)}"})
        else:
            return jsonify({"code": 400, "message": "不支持的文件类型"})

        if not text or len(text) < 10:
            return jsonify({"code": 400, "message": "文件内容为空或过短"})

        # 自动检测类型
        detected_type = "faq"
        suggested_category = "faq"

        scene_keywords = ["景点", "讲解", "介绍", "景观", "建筑", "佛像", "大佛", "梵宫"]
        history_keywords = ["历史", "文化", "古代", "朝代", "佛教", "传统", "习俗", "典故"]
        info_keywords = ["门票", "交通", "停车", "开放时间", "价格", "门票价格", "游玩时间"]
        route_keywords = ["路线", "行程", "攻略", "游览", "推荐路线", "游玩顺序"]

        text_lower = text.lower()
        scores = {
            "faq": sum(1 for q in ["如何", "怎么", "什么", "吗", "?", "？"] if q in text_lower),
            "scene_intro": sum(1 for kw in scene_keywords if kw in text_lower),
            "history": sum(1 for kw in history_keywords if kw in text_lower),
            "basic_info": sum(1 for kw in info_keywords if kw in text_lower),
            "route": sum(1 for kw in route_keywords if kw in text_lower),
        }

        best_type = max(scores, key=scores.get)
        detected_type = best_type
        suggested_category = best_type

        # 提取关键词（前10个高频词）
        keywords = _extract_keywords(text, top_k=10)

        # 截断预览
        preview = text[:500] + ("..." if len(text) > 500 else "")

        return jsonify({
            "code": 200,
            "message": "文件分析完成",
            "data": {
                "filename": file.filename,
                "text_length": len(text),
                "preview": preview,
                "detected_type": detected_type,
                "suggested_category": suggested_category,
                "category_scores": scores,
                "keywords": keywords
            }
        })
    except Exception as e:
        return jsonify({"code": 500, "message": f"文件处理失败：{str(e)}"})


def _extract_keywords(text, top_k=10):
    """简单的关键词提取（高频词）"""
    # 分词
    import re
    words = re.findall(r'[\u4e00-\u9fff]+', text)
    # 过滤短词
    words = [w for w in words if len(w) >= 2]
    # 统计词频
    from collections import Counter
    counter = Counter(words)
    # 排除常见停用词
    stopwords = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
                 "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
                 "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些", "什么", "怎么",
                 "哪", "谁", "为什么", "因为", "所以", "但是", "如果", "可以", "这样", "那样",
                 "这个", "那个", "这些", "那些", "来", "过", "做", "用", "比", "对", "给",
                 "从", "被", "把", "让", "把", "得", "地", "还", "只", "又", "再", "很",
                 "非常", "已经", "可能", "应该", "不会", "不能", "还是", "或者", "以及"}
    filtered = {w: c for w, c in counter.items() if w not in stopwords}
    return [w for w, _ in Counter(filtered).most_common(top_k)]


# ======================== 6. 对话日志管理 ========================
@admin_bp.route("/chat-logs", methods=["GET"])
@admin_required
def list_chat_logs():
    """获取对话日志列表（支持分页、筛选、时间检索）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    keyword = request.args.get("keyword", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = ChatLog.query

    if keyword:
        query = query.filter(
            ChatLog.question_text.contains(keyword) |
            ChatLog.answer_text.contains(keyword)
        )

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(ChatLog.question_time >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(ChatLog.question_time < dt_to)
        except ValueError:
            pass

    pagination = query.order_by(ChatLog.question_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "code": 200,
        "data": {
            "items": [log.to_dict() for log in pagination.items],
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages
        }
    })


# ======================== 6. 对话日志导出 ========================
@admin_bp.route("/chat-logs/export", methods=["GET"])
@admin_required
def chat_log_export():
    """导出对话日志为Excel文件"""
    try:
        from sqlalchemy import func
        # 参数
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        keyword = request.args.get("keyword", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")

        query = ChatLog.query

        if keyword:
            query = query.filter(
                ChatLog.question_text.contains(keyword) |
                ChatLog.answer_text.contains(keyword)
            )

        if date_from:
            try:
                dt_from = datetime.strptime(date_from, "%Y-%m-%d")
                query = query.filter(ChatLog.question_time >= dt_from)
            except ValueError:
                pass

        if date_to:
            try:
                dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(ChatLog.question_time < dt_to)
            except ValueError:
                pass

        logs = query.order_by(ChatLog.question_time.desc()).all()

        try:
            import openpyxl
            from openpyxl.styles import Font, Alignment, PatternFill

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "对话日志"

            # 表头
            headers = ["ID", "用户ID", "提问内容", "AI回答", "提问时间", "情绪标签", "语音时长", "数字人ID", "音色"]
            header_font = Font(bold=True, color="FFFFFF")
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            # 数据行
            for row_idx, log in enumerate(logs, 2):
                ws.cell(row=row_idx, column=1, value=log.id)
                ws.cell(row=row_idx, column=2, value=log.user_id)
                ws.cell(row=row_idx, column=3, value=log.question_text)
                ws.cell(row=row_idx, column=4, value=log.answer_text)
                ws.cell(row=row_idx, column=5, value=log.question_time.strftime("%Y-%m-%d %H:%M:%S"))
                ws.cell(row=row_idx, column=6, value=log.emotion_label)
                ws.cell(row=row_idx, column=7, value=log.voice_duration)
                ws.cell(row=row_idx, column=8, value=log.digital_human_id)
                ws.cell(row=row_idx, column=9, value=log.tts_voice)

            # 调整列宽
            ws.column_dimensions["A"].width = 8
            ws.column_dimensions["B"].width = 10
            ws.column_dimensions["C"].width = 40
            ws.column_dimensions["D"].width = 60
            ws.column_dimensions["E"].width = 20
            ws.column_dimensions["F"].width = 12
            ws.column_dimensions["G"].width = 12
            ws.column_dimensions["H"].width = 12
            ws.column_dimensions["I"].width = 25

            # 保存到临时文件
            import tempfile
            tmp_path = os.path.join(tempfile.gettempdir(), f"chat_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
            wb.save(tmp_path)

            # 返回文件下载
            from flask import send_file
            return send_file(
                tmp_path,
                as_attachment=True,
                download_name=f"灵山胜境对话日志_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except ImportError:
            return jsonify({"code": 500, "message": "服务器缺少openpyxl库，无法导出Excel"})

    except Exception as e:
        return jsonify({"code": 500, "message": f"导出失败：{str(e)}"})


# ========================================
# 游客感受度报告 - 降级生成函数（大模型不可用时使用）
# ========================================

def _generate_default_kw_analysis(top5_kw, satisfaction, total):
    """大模型调用失败时的降级生成：游客关注点分析"""
    if not top5_kw:
        return "暂无游客关注点数据，系统仍在收集中。"

    top1 = top5_kw[0]
    top2 = top5_kw[1] if len(top5_kw) > 1 else top5_kw[0]
    return (
        f"根据近期游客交互数据分析，游客最关注的是「{top1['keyword']}」（{top1['count']}次）和「{top2['keyword']}」（{top2['count']}次）。"
        f"整体满意度为{satisfaction}%，游客主要围绕景区核心景点和服务设施进行咨询，"
        f"建议针对性优化高频问题对应的服务内容和知识库覆盖范围。"
    )


def _generate_default_trend_analysis(emotion_trend):
    """大模型调用失败时的降级生成：情感趋势分析"""
    if not emotion_trend:
        return "近7天情感趋势数据较少，系统仍在收集中。"

    latest = emotion_trend[-1]
    top_emotion = max(latest.get("data", {}), key=latest.get("data", {}).get, default="微笑")
    return (
        f"近7天情感趋势显示，「{top_emotion}」为最常见情感，"
        f"整体情感分布较为稳定。建议持续优化服务体验，保持正面情感占比，"
        f"同时关注负面情感波动，及时调整服务策略。"
    )


def _generate_default_suggestions(keyword_counts, satisfaction, total):
    """大模型调用失败时的降级生成：服务建议"""
    suggestions = []
    if keyword_counts and keyword_counts[0]["count"] > 0:
        top_kw = keyword_counts[0]["keyword"]
        if top_kw == "交通":
            suggestions.append("交通问题咨询较多，建议在首页增加交通指引卡片和公交/自驾路线图")
        elif top_kw == "门票":
            suggestions.append("门票价格咨询频繁，建议增设自动播报入口和优惠政策提醒")
        elif top_kw == "路线":
            suggestions.append("游客对路线规划需求较高，建议优化推荐路线算法，提供定制化游览方案")
        elif top_kw == "大佛":
            suggestions.append("灵山大佛为热门景点，建议增加互动讲解和文化故事推送")
        elif top_kw == "素斋":
            suggestions.append("素斋服务受关注，建议发布素斋菜单和预订信息")
        else:
            suggestions.append(f"「{top_kw}」关注度高，建议针对性优化相关服务")

    if satisfaction < 60:
        suggestions.append(f"游客满意度偏低（{satisfaction}%），建议加强情感识别和问题解决能力，提升服务温度")
    elif satisfaction < 80:
        suggestions.append(f"游客满意度一般（{satisfaction}%），建议优化数字人交互话术，增加个性化服务")

    if not suggestions:
        suggestions.append("当前服务运行良好，游客满意度较高，建议继续保持高质量互动，定期更新知识库内容")

    return suggestions


# ======================== 7. 数据大屏统计 ========================
@admin_bp.route("/dashboard/stats", methods=["GET"])
@admin_required
def dashboard_stats():
    """获取数据大屏统计信息"""
    try:
        # 总对话数
        total_chats = ChatLog.query.count()
        # 总用户数
        total_users = User.query.count()
        # 今日对话数
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_chats = ChatLog.query.filter(ChatLog.question_time >= today_start).count()
        # 知识库条目数
        total_knowledge = Knowledge.query.filter_by(is_active=True).count()
        # 数字人数
        total_digital_humans = DigitalHuman.query.count()

        # 热门问题TOP10
        from sqlalchemy import func
        hot_questions = db.session.query(
            ChatLog.question_text,
            func.count(ChatLog.id).label("count")
        ).group_by(ChatLog.question_text).order_by(
            func.count(ChatLog.id).desc()
        ).limit(10).all()

        # 情绪分布
        emotion_stats = db.session.query(
            ChatLog.emotion_label,
            func.count(ChatLog.id).label("count")
        ).group_by(ChatLog.emotion_label).all()

        # 近7天对话趋势
        seven_days_ago = today_start - timedelta(days=6)
        daily_chats = db.session.query(
            func.date(ChatLog.question_time).label("date"),
            func.count(ChatLog.id).label("count")
        ).filter(ChatLog.question_time >= seven_days_ago).group_by(
            func.date(ChatLog.question_time)
        ).order_by(func.date(ChatLog.question_time)).all()

        # 满意度估算（正面情感 / 总对话数）
        positive_labels = ["微笑", "热情", "开心", "热情满意"]
        total_for_satisfaction = total_chats or 1
        positive_count = ChatLog.query.filter(ChatLog.emotion_label.in_(positive_labels)).count()
        satisfaction = round(positive_count / total_for_satisfaction * 100, 1) if total_chats > 0 else 96.8

        return jsonify({
            "code": 200,
            "data": {
                "total_chats": total_chats,
                "total_users": total_users,
                "today_chats": today_chats,
                "total_knowledge": total_knowledge,
                "total_digital_humans": total_digital_humans,
                "satisfaction": satisfaction,
                "hot_questions": [
                    {"question": q[0][:50] + "..." if len(q[0]) > 50 else q[0], "count": q[1]}
                    for q in hot_questions
                ],
                "emotion_stats": {e[0]: e[1] for e in emotion_stats},
                "daily_chats": [
                    {"date": d[0], "count": d[1]} for d in daily_chats
                ]
            }
        })
    except Exception as e:
        print(f"[Dashboard] 统计失败：{e}")
        return jsonify({"code": 500, "message": f"统计失败：{str(e)}"})


# ======================== 8. AI参数配置 ========================
@admin_bp.route("/ai-config", methods=["GET"])
@admin_required
def get_ai_config():
    """获取当前AI配置"""
    llm = get_llm_service()
    return jsonify({
        "code": 200,
        "data": llm.get_config()
    })


@admin_bp.route("/ai-config", methods=["PUT"])
@admin_required
def update_ai_config():
    """更新AI配置"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "message": "请求参数不能为空"})

    llm = get_llm_service()
    llm.update_config(
        api_key=data.get("api_key"),
        api_base=data.get("api_base"),
        model_name=data.get("model_name"),
        vision_model=data.get("vision_model")
    )

    return jsonify({
        "code": 200,
        "message": "AI配置更新成功，全局生效",
        "data": llm.get_config()
    })


# 报告缓存（避免重复LLM调用）
_report_cache = {"data": None, "timestamp": 0}
_REPORT_CACHE_TTL = 300  # 缓存5分钟


@admin_bp.route("/emotion/report", methods=["GET"])
@admin_required
def emotion_report():
    """游客感受度报告 - 返回基于数据统计的结构化分析（纯数据驱动，不调用大模型）"""
    from sqlalchemy import func, case, Integer as SA_Integer

    # 1. 尝试返回缓存
    now = time.time()
    if _report_cache["data"] and (now - _report_cache["timestamp"]) < _REPORT_CACHE_TTL:
        return jsonify({"code": 200, "data": _report_cache["data"], "cached": True})

    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = today_start - timedelta(days=6)

        # ---- 情感统计 ----
        emotion_stats = db.session.query(
            ChatLog.emotion_label,
            func.count(ChatLog.id).label("count")
        ).group_by(ChatLog.emotion_label).all()
        emotion_dict = {e[0]: e[1] for e in emotion_stats}

        # ---- 今日情感统计 ----
        today_emotion = db.session.query(
            ChatLog.emotion_label,
            func.count(ChatLog.id).label("count")
        ).filter(ChatLog.question_time >= today_start).group_by(ChatLog.emotion_label).all()
        today_emotion_dict = {e[0]: e[1] for e in today_emotion}

        # ---- 近7天情感趋势 ----
        emotion_trend_raw = db.session.query(
            func.date(ChatLog.question_time).label("date"),
            ChatLog.emotion_label,
            func.count(ChatLog.id).label("count")
        ).filter(ChatLog.question_time >= seven_days_ago).group_by(
            func.date(ChatLog.question_time), ChatLog.emotion_label
        ).order_by(func.date(ChatLog.question_time)).all()

        trend_data = {}
        emotion_types = list(emotion_dict.keys())
        for row in emotion_trend_raw:
            date_str = row[0]
            if date_str not in trend_data:
                trend_data[date_str] = {e: 0 for e in emotion_types}
            trend_data[date_str][row[1]] = row[2]

        all_dates = []
        current = seven_days_ago
        while current <= today_start:
            date_str = current.strftime("%Y-%m-%d")
            all_dates.append(date_str)
            if date_str not in trend_data:
                trend_data[date_str] = {e: 0 for e in emotion_types}
            current += timedelta(days=1)

        emotion_trend = []
        for date_str in all_dates:
            emotion_trend.append({
                "date": date_str,
                "data": trend_data.get(date_str, {})
            })

        # ---- 游客关注点分析（单次批量查询） ----
        keywords = ["门票", "交通", "路线", "景点", "表演", "素斋", "住宿", "大佛", "梵宫", "拈花湾"]
        cases = [
            func.sum(case((ChatLog.question_text.contains(kw), 1), else_=0).cast(SA_Integer)).label(kw)
            for kw in keywords
        ]
        row = db.session.query(*cases).first()
        keyword_counts = [{"keyword": kw, "count": getattr(row, kw) or 0} for kw in keywords]
        keyword_counts.sort(key=lambda x: x["count"], reverse=True)

        # ---- 满意度估算（将「平静」归为中性，不参与正负面计算） ----
        positive_labels = ["微笑", "热情", "开心", "热情满意"]
        negative_labels = ["困惑", "不满"]
        total = ChatLog.query.count()
        positive = ChatLog.query.filter(ChatLog.emotion_label.in_(positive_labels)).count()
        satisfaction = round(positive / total * 100, 1) if total > 0 else 0

        # ---- 模拟3秒延迟，让用户能看到加载状态 ----
        time.sleep(3)

        # ---- 使用纯数据驱动生成分析文本（不调用大模型） ----
        kw_analysis = _generate_default_kw_analysis(
            keyword_counts[:5] if keyword_counts else [], satisfaction, total
        )
        trend_analysis = _generate_default_trend_analysis(emotion_trend)
        suggestions = _generate_default_suggestions(keyword_counts, satisfaction, total)

        result = {
            "emotion_stats": emotion_dict,
            "today_emotion": today_emotion_dict,
            "emotion_trend": emotion_trend,
            "keyword_counts": keyword_counts,
            "satisfaction": satisfaction,
            "total_chats": total,
            "kw_analysis": kw_analysis,
            "trend_analysis": trend_analysis,
            "suggestions": suggestions
        }

        # 写入缓存
        _report_cache["data"] = result
        _report_cache["timestamp"] = time.time()

        return jsonify({"code": 200, "data": result, "cached": False})
    except Exception as e:
        # 兜底：如果缓存还有，返回陈旧缓存而非报错
        if _report_cache["data"]:
            return jsonify({"code": 200, "data": _report_cache["data"], "cached": True, "stale": True})
        return jsonify({"code": 500, "message": f"报告生成失败：{str(e)}"})


@admin_bp.route("/dashboard/pref", methods=["GET"])
@admin_required
def dashboard_pref():
    """获取游览偏好数据（数据大屏用）"""
    try:
        from sqlalchemy import func
        # 数字人使用统计
        dh_stats = db.session.query(
            ChatLog.digital_human_id,
            DigitalHuman.name,
            func.count(ChatLog.id).label("count")
        ).join(DigitalHuman, ChatLog.digital_human_id == DigitalHuman.id).group_by(
            ChatLog.digital_human_id, DigitalHuman.name
        ).order_by(func.count(ChatLog.id).desc()).all()

        # 音色使用统计
        voice_stats = db.session.query(
            ChatLog.tts_voice,
            func.count(ChatLog.id).label("count")
        ).group_by(ChatLog.tts_voice).order_by(func.count(ChatLog.id).desc()).limit(5).all()

        return jsonify({
            "code": 200,
            "data": {
                "digital_humans": [{"name": d[1], "count": d[2]} for d in dh_stats],
                "voices": [{"voice": v[0], "count": v[1]} for v in voice_stats]
            }
        })
    except Exception as e:
        return jsonify({"code": 500, "message": f"数据获取失败：{str(e)}"})


# ======================== 9. 路线规划管理 ========================

@admin_bp.route("/routes", methods=["GET"])
@admin_required
def list_routes():
    """获取路线列表（支持分页和筛选）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    style = request.args.get("style", "")
    keyword = request.args.get("keyword", "")
    is_active = request.args.get("is_active")
    sort_by = request.args.get("sort_by", "sort_order")
    sort_order_dir = request.args.get("sort_order", "asc")

    query = Route.query

    if style:
        query = query.filter_by(style=style)
    if keyword:
        query = query.filter(Route.title.contains(keyword) | Route.description.contains(keyword))
    if is_active and is_active.strip():
        query = query.filter_by(is_active=(is_active.lower() in ("true", "1", "yes")))

    SORT_FIELDS = {
        "sort_order": Route.sort_order,
        "created_at": Route.created_at,
        "updated_at": Route.updated_at,
        "title": Route.title,
        "duration": Route.duration,
        "rating": Route.rating,
    }
    sort_col = SORT_FIELDS.get(sort_by, Route.sort_order)
    if sort_order_dir.lower() == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "code": 200,
        "data": {
            "items": [r.to_dict() for r in pagination.items],
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages
        }
    })


@admin_bp.route("/routes/brief", methods=["GET"])
@admin_required
def list_routes_brief():
    """获取精简路线列表（不含spots）"""
    style = request.args.get("style", "")
    query = Route.query.filter_by(is_active=True)
    if style:
        query = query.filter_by(style=style)
    routes = query.order_by(Route.sort_order).all()
    return jsonify({
        "code": 200,
        "data": [r.to_brief() for r in routes]
    })


@admin_bp.route("/routes/<int:route_id>", methods=["GET"])
@admin_required
def get_route(route_id):
    """获取单条路线完整详情"""
    route = Route.query.get(route_id)
    if not route:
        return jsonify({"code": 404, "message": "路线不存在"})
    return jsonify({"code": 200, "data": route.to_dict()})


@admin_bp.route("/routes", methods=["POST"])
@admin_required
def create_route():
    """创建路线"""
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"code": 400, "message": "路线名称不能为空"})

    route = Route(
        title=data["title"],
        subtitle=data.get("subtitle", ""),
        style=data.get("style", "culture"),
        style_label=data.get("style_label", ""),
        tags=data.get("tags", ""),
        icon=data.get("icon", ""),
        color=data.get("color", "#5b8c5a"),
        description=data.get("description", ""),
        duration=data.get("duration", ""),
        difficulty=data.get("difficulty", "低"),
        best_time=data.get("best_time", ""),
        tips=data.get("tips", ""),
        distance_km=data.get("distance_km", 0.0),
        is_active=data.get("is_active", True),
        sort_order=data.get("sort_order", 0),
        rating=data.get("rating", 0.0),
        bg_image=data.get("bg_image")
    )

    # 处理途经景点
    spots_data = data.get("spots", [])
    for i, spot in enumerate(spots_data):
        route.spots.append(RouteSpot(
            name=spot.get("name", ""),
            description=spot.get("description", ""),
            sort_order=spot.get("sort_order", i),
            latitude=spot.get("latitude"),
            longitude=spot.get("longitude")
        ))

    db.session.add(route)
    db.session.commit()

    # 同步路线到知识库（游览路线分类）
    _sync_route_to_knowledge(route)

    return jsonify({"code": 200, "message": "创建成功", "data": route.to_dict()})


@admin_bp.route("/routes/<int:route_id>", methods=["PUT"])
@admin_required
def update_route(route_id):
    """更新路线"""
    route = Route.query.get(route_id)
    if not route:
        return jsonify({"code": 404, "message": "路线不存在"})

    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "message": "请求数据不能为空"})

    # 更新基本字段
    for field in ["title", "subtitle", "style", "style_label", "icon", "color",
                   "description", "duration", "difficulty", "best_time", "tips",
                   "is_active", "sort_order", "rating", "bg_image"]:
        if field in data:
            setattr(route, field, data[field])

    if "distance_km" in data:
        route.distance_km = float(data["distance_km"])
    if "tags" in data:
        tags = data["tags"]
        route.tags = ",".join(tags) if isinstance(tags, list) else tags

    # 更新途经景点（全量替换）
    if "spots" in data:
        RouteSpot.query.filter_by(route_id=route_id).delete()
        for i, spot in enumerate(data["spots"]):
            db.session.add(RouteSpot(
                route_id=route_id,
                name=spot.get("name", ""),
                description=spot.get("description", ""),
                sort_order=spot.get("sort_order", i),
                latitude=spot.get("latitude"),
                longitude=spot.get("longitude")
            ))

    db.session.commit()

    # 同步更新知识库
    _sync_route_to_knowledge(route)

    # 清除缓存
    _clear_route_cache()

    return jsonify({"code": 200, "message": "更新成功", "data": route.to_dict()})


@admin_bp.route("/routes/<int:route_id>", methods=["DELETE"])
@admin_required
def delete_route(route_id):
    """删除路线"""
    route = Route.query.get(route_id)
    if not route:
        return jsonify({"code": 404, "message": "路线不存在"})

    # 同时删除关联的知识库条目
    Knowledge.query.filter(
        Knowledge.category_id == KnowledgeCategory.query.filter_by(code="route").first().id,
        Knowledge.title.like(f"{route.title}%")
    ).delete()

    db.session.delete(route)
    db.session.commit()

    _clear_route_cache()

    return jsonify({"code": 200, "message": "删除成功"})


@admin_bp.route("/routes/batch/delete", methods=["POST"])
@admin_required
def batch_delete_routes():
    """批量删除路线"""
    data = request.get_json()
    if not data or not isinstance(data.get("ids"), list):
        return jsonify({"code": 400, "message": "请提供 ids 数组"})

    ids = data["ids"]
    deleted = 0
    route_cat = KnowledgeCategory.query.filter_by(code="route").first()

    for rid in ids:
        route = Route.query.get(rid)
        if route:
            if route_cat:
                Knowledge.query.filter(
                    Knowledge.category_id == route_cat.id,
                    Knowledge.title.like(f"{route.title}%")
                ).delete()
            db.session.delete(route)
            deleted += 1
    db.session.commit()
    _clear_route_cache()
    return jsonify({"code": 200, "message": f"已删除 {deleted} 条路线", "data": {"deleted": deleted}})


@admin_bp.route("/routes/sync/knowledge", methods=["POST"])
@admin_required
def sync_routes_to_knowledge():
    """一键同步所有路线到知识库"""
    route_cat = KnowledgeCategory.query.filter_by(code="route").first()
    if not route_cat:
        return jsonify({"code": 400, "message": "游览路线分类不存在，请先初始化知识分类"})

    routes = Route.query.filter_by(is_active=True).all()
    synced = 0
    for route in routes:
        if _sync_route_to_knowledge(route, route_cat):
            synced += 1

    return jsonify({"code": 200, "message": f"已同步 {synced} 条路线到知识库"})


@admin_bp.route("/routes/image/upload", methods=["POST"])
@admin_required
def upload_route_image():
    """上传路线背景图片"""
    if "image" not in request.files:
        return jsonify({"code": 400, "message": "未上传图片"})

    file = request.files["image"]
    if not file or not file.filename:
        return jsonify({"code": 400, "message": "文件为空"})

    allowed_ext = {"jpg", "jpeg", "png", "webp", "gif"}
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_ext:
        return jsonify({"code": 400, "message": f"不支持的文件类型，仅支持: {', '.join(allowed_ext)}"})

    # 检查文件大小
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_CONTENT_LENGTH:
        return jsonify({"code": 400, "message": f"图片超过 {MAX_CONTENT_LENGTH // (1024*1024)}MB 限制"})

    import uuid
    from werkzeug.utils import secure_filename

    upload_dir = os.path.join(UPLOAD_FOLDER, "route_images")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = secure_filename(f"{uuid.uuid4().hex}.{ext}")
    file_path = os.path.join(upload_dir, safe_name)
    file.save(file_path)

    image_path = f"/uploads/route_images/{safe_name}"
    return jsonify({"code": 200, "message": "上传成功", "data": {"path": image_path, "size": file_size}})


@admin_bp.route("/routes/image/<path:image_path>", methods=["DELETE"])
@admin_required
def delete_route_image(image_path):
    """删除路线背景图片"""
    full_path = os.path.join(UPLOAD_FOLDER, "route_images")
    full_path = os.path.abspath(os.path.join(full_path, os.path.basename(image_path)))
    if os.path.exists(full_path):
        os.unlink(full_path)
    return jsonify({"code": 200, "message": "删除成功"})


@admin_bp.route("/routes/<int:route_id>/image", methods=["PUT"])
@admin_required
def set_route_image(route_id):
    """为路线设置背景图片"""
    route = Route.query.get(route_id)
    if not route:
        return jsonify({"code": 404, "message": "路线不存在"})

    data = request.get_json()
    if not data or not data.get("bg_image"):
        return jsonify({"code": 400, "message": "请提供图片路径"})

    route.bg_image = data["bg_image"]
    db.session.commit()
    return jsonify({"code": 200, "message": "路线图片已更新", "data": {"bg_image": route.bg_image}})


@admin_bp.route("/routes/<int:route_id>/image", methods=["DELETE"])
@admin_required
def remove_route_image(route_id):
    """移除路线的背景图片"""
    route = Route.query.get(route_id)
    if not route:
        return jsonify({"code": 404, "message": "路线不存在"})

    # 删除旧图片文件
    if route.bg_image:
        try:
            # bg_image 形如 /uploads/route_images/xxx.png
            rel_path = route.bg_image.lstrip("/")
            full_path = os.path.join(UPLOAD_FOLDER, rel_path)
            full_path = os.path.abspath(full_path)
            # 安全检查：确保路径在 UPLOAD_FOLDER 内
            upload_abs = os.path.abspath(UPLOAD_FOLDER)
            if full_path.startswith(upload_abs) and os.path.exists(full_path):
                os.unlink(full_path)
        except Exception:
            pass

    route.bg_image = None
    db.session.commit()
    return jsonify({"code": 200, "message": "路线图片已移除"})


@admin_bp.route("/routes/stats", methods=["GET"])
@admin_required
def list_route_styles():
    """获取路线风格分类统计"""
    from sqlalchemy import func
    stats = db.session.query(
        Route.style, Route.style_label, func.count(Route.id).label("count")
    ).filter_by(is_active=True).group_by(Route.style, Route.style_label).all()

    return jsonify({
        "code": 200,
        "data": [{"style": s[0], "label": s[1], "count": s[2]} for s in stats]
    })


@admin_bp.route("/routes/<int:route_id>/feedbacks", methods=["GET"])
@admin_required
def list_route_feedbacks(route_id):
    """获取指定路线的用户评价反馈（分页、排序、筛选）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    sort_by = request.args.get("sort_by", "time")   # time / rating
    sort_order = request.args.get("sort_order", "desc")  # asc / desc
    min_rating = request.args.get("min_rating", 0, type=int)  # 0-5，最低评分筛选

    # 查询该路线的评价记录
    query = ChatLog.query.filter(
        ChatLog.emotion_label == "反馈",
        ChatLog.question_text.like(f"路线评价 - 路线#{route_id}%")
    )

    total = query.count()

    # 排序
    if sort_by == "rating":
        # 按评分排序：从 answer_text 提取数值排序
        # 先用 CASE WHEN 表达式提取评分
        from sqlalchemy import case, desc, asc
        rating_expr = case(
            (ChatLog.answer_text.like("%评分: 5星%"), 5),
            (ChatLog.answer_text.like("%评分: 4星%"), 4),
            (ChatLog.answer_text.like("%评分: 3星%"), 3),
            (ChatLog.answer_text.like("%评分: 2星%"), 2),
            (ChatLog.answer_text.like("%评分: 1星%"), 1),
            else_=0
        )
        order_expr = desc(rating_expr) if sort_order == "desc" else asc(rating_expr)
        query = query.order_by(order_expr)
    else:
        # 默认按时间排序
        order_col = ChatLog.question_time.desc() if sort_order == "desc" else ChatLog.question_time.asc()
        query = query.order_by(order_col)

    # 分页
    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    # 组装返回数据
    feedbacks = []
    for log in logs:
        user = User.query.get(log.user_id)
        rating = _parse_rating_from_answer(log.answer_text or "")
        comment = _parse_comment_from_answer(log.answer_text or "")

        feedbacks.append({
            "id": log.id,
            "user_id": log.user_id,
            "username": user.username if user else "匿名用户",
            "rating": rating,
            "comment": comment,
            "question_time": log.question_time.strftime("%Y-%m-%d %H:%M:%S") if log.question_time else "",
            "session_id": log.session_id or ""
        })

    # 如果有评分筛选，在内存中过滤（因为评分是从文本解析的）
    if min_rating > 0:
        feedbacks = [f for f in feedbacks if f.get("rating", 0) >= min_rating]
        total = len(feedbacks)  # 注意：这是近似值

    return jsonify({
        "code": 200,
        "data": {
            "items": feedbacks,
            "total": total,
            "page": page,
            "per_page": per_page,
            "route_id": route_id
        }
    })


# ======================== 评价解析辅助函数 ========================

def _parse_rating_from_answer(answer_text: str) -> int:
    """从反馈文本中解析评分"""
    if not answer_text:
        return 0
    m = re.search(r"评分:\s*(\d+)星", answer_text)
    if m:
        return int(m.group(1))
    # 兼容旧格式：纯评分数字
    m2 = re.search(r"^(\d)\s*星?$", answer_text.strip())
    if m2:
        return int(m2.group(1))
    return 0


def _parse_comment_from_answer(answer_text: str) -> str:
    """从反馈文本中解析评论内容（去掉评分前缀）"""
    if not answer_text:
        return ""
    # 去掉 "评分: X星" 前缀
    cleaned = re.sub(r"评分:\s*\d+星\s*[\n\r]*", "", answer_text).strip()
    # 如果去掉前缀后为空，说明只有评分没有评论
    if not cleaned:
        return ""
    # 如果清理后的内容就是纯评分数字，则没有评论
    if re.match(r"^\d+\s*星?$", cleaned):
        return ""
    return cleaned


# ======================== 路线辅助函数 ========================

_route_cache = {}
_ROUTE_CACHE_TTL = 60  # 缓存有效期（秒）


def _clear_route_cache():
    """清除路线缓存"""
    _route_cache.clear()


def _sync_route_to_knowledge(route, route_cat=None):
    """将路线同步到知识库（游览路线分类），便于RAG检索"""
    try:
        if not route_cat:
            route_cat = KnowledgeCategory.query.filter_by(code="route").first()
        if not route_cat:
            return False

        spots_text = "\n".join([f"  {i+1}. {s.name} - {s.description}" for i, s in enumerate(route.spots)])
        content = (
            f"路线名称：{route.title}\n"
            f"副标题：{route.subtitle}\n"
            f"风格：{route.style_label}\n"
            f"时长：{route.duration}\n"
            f"难度：{route.difficulty}\n"
            f"距离：{route.distance_km}km\n"
            f"推荐指数：{route.rating}/5\n"
            f"描述：{route.description}\n"
            f"途经景点：\n{spots_text}\n"
            f"小贴士：{route.tips}\n"
            f"最佳时间：{route.best_time}"
        )

        # 查找是否已存在同名的知识条目
        existing = Knowledge.query.filter(
            Knowledge.category_id == route_cat.id,
            Knowledge.title == f"路线：{route.title}"
        ).first()

        if existing:
            existing.content = content
            existing.tags = route.tags
            existing.updated_at = datetime.now()
        else:
            knowledge = Knowledge(
                category_id=route_cat.id,
                title=f"路线：{route.title}",
                content=content,
                tags=route.tags,
                keywords=f"{route.style},{route.style_label},{route.title}",
                is_active=True
            )
            db.session.add(knowledge)

        db.session.commit()
        return True
    except Exception as e:
        print(f"[Route] 同步到知识库失败：{e}")
        db.session.rollback()
        return False


def seed_routes_from_preserved():
    """将硬编码的 PRESERVED_ROUTES 数据迁移到数据库（仅首次运行时）"""
    if Route.query.count() > 0:
        return 0

    from services.route_service import PRESERVED_ROUTES

    # 景点坐标映射（与前端 RouteMap.vue SPOT_COORDS 保持一致）
    SPOT_COORDS = {
        "南门": (31.4210, 120.1020),
        "南门（入口）": (31.4210, 120.1020),
        "景区入口": (31.4210, 120.1020),
        "佛足坛": (31.4200, 120.1035),
        "九龙灌浴": (31.4190, 120.1050),
        "菩提大道": (31.4185, 120.1040),
        "灵山大佛": (31.4170, 120.1080),
        "祥符禅寺": (31.4180, 120.1065),
        "梵宫": (31.4165, 120.1070),
        "五印坛城": (31.4155, 120.1085),
        "曼飞龙塔": (31.4160, 120.1090),
        "灵山精舍": (31.4150, 120.1075),
        "拈花湾": (31.4100, 120.1150),
        "佛手广场": (31.4195, 120.1045),
        "百子戏弥勒": (31.4188, 120.1055),
        "梵宫广场": (31.4163, 120.1072),
    }

    def _get_spot_coords(name: str):
        """根据景点名称获取坐标（精确+模糊匹配）"""
        exact = SPOT_COORDS.get(name)
        if exact:
            return exact
        for key, coord in SPOT_COORDS.items():
            if key in name or name in key:
                return coord
        return (None, None)

    count = 0
    for r in PRESERVED_ROUTES:
        route = Route(
            id=r["id"],
            title=r["title"],
            subtitle=r.get("subtitle", ""),
            style=r["style"],
            style_label=r.get("style_label", ""),
            tags=",".join(r.get("tags", [])),
            icon=r.get("icon", ""),
            color=r.get("color", "#5b8c5a"),
            description=r.get("description", ""),
            duration=r.get("duration", ""),
            difficulty=r.get("difficulty", "低"),
            best_time=r.get("best_time", ""),
            tips=r.get("tips", ""),
            distance_km=r.get("distance_km", 0.0),
            is_active=True,
            sort_order=r["id"],
            rating=4.5
        )

        for i, spot in enumerate(r.get("spots", [])):
            lat, lng = _get_spot_coords(spot["name"])
            route.spots.append(RouteSpot(
                name=spot["name"],
                description=spot.get("description", ""),
                sort_order=i,
                latitude=lat,
                longitude=lng
            ))

        db.session.add(route)
        count += 1

    db.session.commit()

    # 同步到知识库
    route_cat = KnowledgeCategory.query.filter_by(code="route").first()
    if route_cat:
        for r in Route.query.all():
            _sync_route_to_knowledge(r, route_cat)

    print(f"[Route] 已从 PRESERVED_ROUTES 导入 {count} 条路线到数据库")
    return count
