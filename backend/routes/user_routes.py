"""
==============================================================
游客用户路由模块
提供游客登录、注册、数字人、路线规划、图片上传等接口
==============================================================
"""

import os
import sys
import json
import uuid
import requests
import mimetypes
from datetime import datetime
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, session, g
from models import db, User, DigitalHuman, ChatLog
from config import MAP_KEY, UPLOAD_FOLDER, ALLOWED_EXTENSIONS, MAX_CONTENT_LENGTH, VIDEO_ALLOWED_EXTENSIONS, VIDEO_MAX_SIZE
from services.route_service import (
    get_all_routes, get_route_detail, get_default_route,
    get_llm_recommendation, analyze_user_preferences,
    collect_user_feedback, get_user_feedback_summary,
    get_routes_by_tags
)
from services.memory_service import get_memory_agent

user_bp = Blueprint("user", __name__, url_prefix="/api/user")


# ======================== 游客登录鉴权装饰器 ========================
def login_required(f):
    """要求游客登录的装饰器：校验 session 中的 user_id 并注入 g.current_user"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"code": 401, "message": "请先登录"}), 401
        user = User.query.get(user_id)
        if not user:
            session.pop("user_id", None)
            session.pop("username", None)
            return jsonify({"code": 401, "message": "用户不存在，请重新登录"}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


# ======================== 0. 图片上传 ========================
def _allowed_file(filename):
    """检查文件扩展名是否在允许列表中"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@user_bp.route("/upload-image", methods=["POST"])
@login_required
def upload_image():
    """
    上传图片（单次支持多文件上传）
    返回：{ "code": 200, "data": { "images": [ { "url": "...", "filename": "..." }, ... ] } }
    """
    user_id = g.current_user.id

    # 支持单文件和多文件
    files = request.files.getlist("file")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"code": 400, "message": "未选择任何文件"})

    images = []
    now = datetime.now()
    # 按日期分目录：uploads/2026/07/12/
    sub_dir = os.path.join(UPLOAD_FOLDER, now.strftime("%Y/%m/%d"))
    os.makedirs(sub_dir, exist_ok=True)

    for file in files:
        if not file.filename or not _allowed_file(file.filename):
            continue

        # 检查文件大小（bytes）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_CONTENT_LENGTH:
            continue  # 跳过超限文件，不中断整批上传

        # 生成唯一文件名
        ext = file.filename.rsplit(".", 1)[1].lower()
        new_filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(sub_dir, new_filename)

        try:
            file.save(save_path)
        except Exception as e:
            print(f"[Upload] 文件保存失败: {e}")
            continue

        # 构建可访问 URL
        # uploads/2026/07/12/abc123.jpg → /uploads/2026/07/12/abc123.jpg
        relative_path = os.path.relpath(save_path, UPLOAD_FOLDER)
        url = f"/uploads/{relative_path}"
        images.append({
            "url": url,
            "filename": new_filename,
            "original_name": file.filename,
            "size": file_size
        })

    if not images:
        return jsonify({"code": 400, "message": "所有文件上传失败，请检查格式和大小"})

    return jsonify({
        "code": 200,
        "message": "上传成功",
        "data": {
            "images": images,
            "count": len(images)
        }
    })


# ======================== 0b. 视频上传 ========================
def _allowed_video_file(filename):
    """检查视频扩展名是否在允许列表中"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in VIDEO_ALLOWED_EXTENSIONS


@user_bp.route("/upload-video", methods=["POST"])
@login_required
def upload_video():
    """
    上传视频（单文件），供多模态视频理解使用
    返回：{ "code": 200, "data": { "url": "...", "filename": "..." } }
    """
    user_id = g.current_user.id

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"code": 400, "message": "未选择视频文件"})

    if not _allowed_video_file(file.filename):
        return jsonify({"code": 400, "message": "不支持的视频格式，请上传 mp4/avi/mov/mkv/webm"})

    # 校验大小
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > VIDEO_MAX_SIZE:
        return jsonify({"code": 400, "message": f"视频超过大小限制（{VIDEO_MAX_SIZE // (1024*1024)}MB）"})

    # 按日期分目录：uploads/2026/10/11/
    now = datetime.now()
    sub_dir = os.path.join(UPLOAD_FOLDER, now.strftime("%Y/%m/%d"))
    os.makedirs(sub_dir, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[1].lower()
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(sub_dir, new_filename)

    try:
        file.save(save_path)
    except Exception as e:
        print(f"[Upload] 视频保存失败: {e}")
        return jsonify({"code": 500, "message": "视频保存失败，请稍后重试"})

    relative_path = os.path.relpath(save_path, UPLOAD_FOLDER)
    url = f"/uploads/{relative_path}"
    print(f"[Upload] 视频上传成功: {url} ({file_size / 1024 / 1024:.1f}MB)")

    return jsonify({
        "code": 200,
        "message": "上传成功",
        "data": {
            "url": url,
            "filename": new_filename,
            "original_name": file.filename,
            "size": file_size
        }
    })


# ======================== 1. 游客注册 ========================
@user_bp.route("/register", methods=["POST"])
def user_register():
    """游客注册"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "message": "请求参数不能为空"})

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()

    # 校验参数
    if not username or not password:
        return jsonify({"code": 400, "message": "用户名和密码不能为空"})
    if len(username) < 2 or len(username) > 32:
        return jsonify({"code": 400, "message": "用户名长度为2-32个字符"})
    if len(password) < 6:
        return jsonify({"code": 400, "message": "密码长度不能少于6位"})

    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({"code": 400, "message": "用户名已被注册"})

    # 创建用户
    user = User(username=username, phone=phone, email=email)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "code": 200,
        "message": "注册成功",
        "data": {
            "id": user.id,
            "username": user.username
        }
    })


# ======================== 2. 游客登录 ========================
@user_bp.route("/login", methods=["POST"])
def user_login():
    """游客登录"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "message": "请求参数不能为空"})

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"code": 400, "message": "用户名和密码不能为空"})

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"code": 401, "message": "用户名或密码错误"})

    # 保存登录态
    session["user_id"] = user.id
    session["username"] = user.username

    return jsonify({
        "code": 200,
        "message": "登录成功",
        "data": user.to_dict()
    })


# ======================== 3. 退出登录 ========================
@user_bp.route("/logout", methods=["POST"])
def user_logout():
    """游客退出登录，清除服务端 session"""
    session.pop("user_id", None)
    session.pop("username", None)
    return jsonify({"code": 200, "message": "已退出登录"})


# ======================== 4. 用户信息 ========================
@user_bp.route("/info", methods=["GET"])
@login_required
def user_info():
    """获取当前登录用户信息"""
    return jsonify({"code": 200, "data": g.current_user.to_dict()})


# ======================== 4a. 保存用户选中的数字人 ========================
@user_bp.route("/digital-human", methods=["PUT"])
@login_required
def save_user_digital_human():
    """保存当前用户选中的数字人ID"""
    user = g.current_user

    data = request.get_json()
    if not data or "digital_human_id" not in data:
        return jsonify({"code": 400, "message": "缺少 digital_human_id 参数"})

    dh_id = data["digital_human_id"]
    # 校验数字人是否存在
    dh = DigitalHuman.query.get(dh_id)
    if not dh:
        return jsonify({"code": 404, "message": "数字人不存在"})

    user.digital_human_id = dh_id
    db.session.commit()

    return jsonify({"code": 200, "message": "保存成功", "data": {"digital_human_id": dh_id}})


# ======================== 4b. 获取可用数字人列表 ========================
@user_bp.route("/digital-humans", methods=["GET"])
def get_digital_humans():
    """获取所有已启用的数字人形象"""
    humans = DigitalHuman.query.filter_by(is_active=True).all()
    return jsonify({
        "code": 200,
        "data": [h.to_dict() for h in humans]
    })


# ======================== 4b. 数字人头像预览（代理远端 LiveTalking） ========================
from flask import Response, abort

@user_bp.route("/avatars/<folder>/preview", methods=["GET"])
def get_avatar_preview(folder):
    """
    从 LiveTalking 服务器获取指定 avatar 的第一张预览图，代理返回给 H5 前端
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


# ======================== 5. 智能路线规划 ========================
@user_bp.route("/route-plan", methods=["GET"])
def get_route_plan():
    """获取路线规划（默认返回推荐路线，兼容旧版接口）"""
    user_id = session.get("user_id", 0)
    route_type = request.args.get("type", "")

    # 兼容旧版：type=all/culture/nature/family
    if route_type in ("all", "culture", "nature", "family"):
        route_map = {
            "all": None,
            "culture": 1,
            "nature": 2,
            "family": 3
        }
        target_id = route_map.get(route_type)
        if target_id:
            detail = get_route_detail(target_id)
            if detail:
                # 兼容旧版返回格式
                return jsonify({
                    "code": 200,
                    "data": {
                        route_type: {
                            "title": detail["title"],
                            "description": detail["description"],
                            "duration": detail["duration"],
                            "spots": detail["spots"],
                            "tips": detail["tips"]
                        }
                    }
                })
        return jsonify({"code": 200, "data": {
            "culture": {"title": "文化朝圣路线", "description": "经典文化游", "duration": "约3小时", "spots": [{"name": "灵山大佛", "description": "核心景点"}], "tips": "经典路线"},
            "nature": {"title": "自然风光路线", "description": "户外风景游", "duration": "约5小时", "spots": [{"name": "灵山大佛", "description": "核心景点"}], "tips": "自然风光"},
            "family": {"title": "亲子家庭路线", "description": "亲子互动游", "duration": "约4小时", "spots": [{"name": "灵山大佛", "description": "核心景点"}], "tips": "亲子家庭"}
        }})

    # 新版：返回默认推荐路线详情
    default_route = get_default_route()
    if default_route:
        return jsonify({"code": 200, "data": default_route})
    return jsonify({"code": 404, "message": "路线不存在"})


@user_bp.route("/route-plan/all", methods=["GET"])
def get_all_route_plans():
    """获取全部10条预设路线（简版）"""
    routes = get_all_routes()
    return jsonify({"code": 200, "data": routes})


@user_bp.route("/route-plan/<int:route_id>", methods=["GET"])
def get_route_plan_detail(route_id):
    """获取单条路线完整详情"""
    detail = get_route_detail(route_id)
    if detail:
        return jsonify({"code": 200, "data": detail})
    return jsonify({"code": 404, "message": "路线不存在"})


@user_bp.route("/route-plan/tags", methods=["GET"])
def get_routes_by_tag():
    """按标签筛选路线"""
    tags = request.args.get("tags", "").split(",")
    tags = [t.strip() for t in tags if t.strip()]
    if not tags:
        return jsonify({"code": 200, "data": get_all_routes()})
    routes = get_routes_by_tags(tags)
    return jsonify({"code": 200, "data": routes})


@user_bp.route("/route-recommend", methods=["POST"])
def get_route_recommendation():
    """调用大模型生成个性化路线推荐（支持未登录）"""
    user_id = session.get("user_id")
    if not user_id:
        user_id = 0  # 兼容未登录，使用默认偏好

    try:
        data = request.get_json() or {}
        preferences = data.get("preferences", {})

        # 调用 LLM 推荐
        recommendation = get_llm_recommendation(user_id, preferences)
        rec_id = recommendation.get("recommended_route_id", 1)
        detail = get_route_detail(rec_id)

        if detail:
            return jsonify({
                "code": 200,
                "data": {
                    "recommended": detail,
                    "reason": recommendation.get("reason", ""),
                    "alternatives": [get_route_detail(a) for a in recommendation.get("alternatives", []) if get_route_detail(a)]
                }
            })
        return jsonify({"code": 404, "message": "推荐路线不存在"})
    except Exception as e:
        print(f"[Route] 推荐异常: {e}")
        # 降级返回默认路线
        default = get_route_detail(1)
        return jsonify({
            "code": 200,
            "data": {
                "recommended": default,
                "reason": "为您推荐经典文化朝圣路线",
                "alternatives": [get_route_detail(2), get_route_detail(3)]
            }
        })


@user_bp.route("/route-plan/feedback", methods=["POST"])
@login_required
def submit_route_feedback():
    """收集用户对路线的评价反馈"""
    user_id = g.current_user.id

    data = request.get_json() or {}
    route_id = data.get("routeId") or data.get("route_id", 1)
    rating = data.get("rating", 5)
    comment = data.get("comment", "")

    result = collect_user_feedback(user_id, route_id, rating, comment)
    return jsonify(result)


@user_bp.route("/route-plan/feedbacks", methods=["GET"])
@login_required
def get_user_feedbacks():
    """获取用户历史反馈摘要"""
    user_id = g.current_user.id

    result = get_user_feedback_summary(user_id)
    return jsonify({"code": 200, "data": result})


@user_bp.route("/route-plan/preferences", methods=["GET"])
def get_user_preferences():
    """获取用户偏好分析结果（基于历史对话）"""
    user_id = session.get("user_id")
    if not user_id:
        user_id = 0  # 兼容未登录

    try:
        prefs = analyze_user_preferences(user_id)
        return jsonify({"code": 200, "data": prefs})
    except Exception as e:
        print(f"[Route] 偏好分析失败: {e}")
        return jsonify({
            "code": 200,
            "data": {
                "preferred_styles": ["culture"],
                "preferred_tags": ["经典"],
                "chat_count": 0,
                "avg_duration": "3小时"
            }
        })


# ======================== 6. 个人对话历史 ========================
@user_bp.route("/chat-history", methods=["GET"])
@login_required
def get_chat_history():
    """获取对话历史——按会话分组，支持多轮对话展示
    规则：登录后只展示当前用户自己的对话记录（user_id 隔离）
    兼容：如果没有个人记录，回退展示系统公共记录(user_id=0)
    """
    user_id = g.current_user.id

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    from sqlalchemy import desc

    # 优先查询当前用户自己的记录
    pagination = ChatLog.query.filter(ChatLog.user_id == user_id)\
        .order_by(desc(ChatLog.question_time))\
        .paginate(page=page, per_page=per_page * 5, error_out=False)

    # 兼容处理：如果当前用户没有记录，回退到系统公共记录
    if pagination.items and len(pagination.items) == 0:
        pagination = ChatLog.query.filter(ChatLog.user_id == 0)\
            .order_by(desc(ChatLog.question_time))\
            .paginate(page=page, per_page=per_page * 5, error_out=False)

    # 按 session_id 分组
    sessions_map = {}
    ordered = []
    for log in pagination.items:
        sid = log.session_id or f"single_{log.id}"
        if sid not in sessions_map:
            sessions_map[sid] = {
                "session_id": sid,
                "title": log.question_text[:30],
                "time": log.question_time.strftime("%m-%d %H:%M"),
                "emotion": log.emotion_label,
                "message_count": 0,
                "route_data": None,
                "messages": []
            }
            ordered.append(sid)
        s = sessions_map[sid]
        s["message_count"] += 1
        s["messages"].append(log.to_dict())
        if log.route_data and not s["route_data"]:
            try:
                s["route_data"] = json.loads(log.route_data)
            except Exception:
                pass

    sessions = [sessions_map[sid] for sid in ordered]
    total_sessions = len(sessions_map)

    return jsonify({
        "code": 200,
        "data": {
            "sessions": sessions,
            "total": total_sessions,
            "page": page,
            "per_page": per_page
        }
    })


# ======================== 7. 获取WebSocket连接信息 ========================
@user_bp.route("/ws-info", methods=["GET"])
def get_ws_info():
    """获取WebSocket连接地址和参数"""
    ws_protocol = "wss" if request.is_secure else "ws"

    return jsonify({
        "code": 200,
        "data": {
            "ws_url": f"{ws_protocol}://{request.host}/ws/chat",
            "user_id": session.get("user_id", 0),
            "map_key": MAP_KEY
        }
    })


@user_bp.route("/chat-history", methods=["DELETE"])
@login_required
def clear_chat_history():
    """清除当前用户的对话历史（仅删除当前登录用户的记录）"""
    user_id = g.current_user.id

    try:
        # 只删除当前用户的对话记录（不删 user_id=0 的公共记录）
        count = ChatLog.query.filter(ChatLog.user_id == user_id).delete()
        db.session.commit()
        return jsonify({
            "code": 200,
            "message": f"已清除 {count} 条对话记录",
            "data": {"deleted_count": count}
        })
    except Exception as e:
        print(f"[Chat] 清除对话历史失败: {e}")
        return jsonify({"code": 500, "message": "清除失败，请稍后重试"})


# ======================== 用户长期记忆（memoryAgent，合规：用户可控） ========================
@user_bp.route("/memory", methods=["GET"])
@login_required
def get_user_memories():
    """查看当前用户的全部长期记忆（会话摘要/偏好画像），保障用户知情权"""
    user_id = g.current_user.id

    try:
        memories = get_memory_agent().get_user_memories(user_id)
        return jsonify({"code": 200, "data": memories})
    except Exception as e:
        print(f"[Memory] 查看记忆失败: {e}")
        return jsonify({"code": 500, "message": "查询失败，请稍后重试"})


@user_bp.route("/memory", methods=["DELETE"])
@login_required
def clear_user_memories():
    """一键清除当前用户的全部长期记忆，保障用户被遗忘权"""
    user_id = g.current_user.id

    try:
        count = get_memory_agent().clear_user_memories(user_id)
        return jsonify({
            "code": 200,
            "message": f"已清除 {count} 条记忆",
            "data": {"deleted_count": count}
        })
    except Exception as e:
        print(f"[Memory] 清除记忆失败: {e}")
        return jsonify({"code": 500, "message": "清除失败，请稍后重试"})
