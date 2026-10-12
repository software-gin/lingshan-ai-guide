"""
==============================================================
消费数据分析路由模块
提供消费数据分析相关的RESTful API接口
==============================================================
"""

import os
import sys
import json
import csv
import tempfile
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, session, current_app
from models import db, Admin
from services.consumption_service import (
    get_consumption_overview,
    get_monthly_trend,
    get_age_analysis,
    get_satisfaction_cost_analysis,
    get_gender_analysis,
    get_stay_cost_analysis,
    get_type_analysis,
    get_operational_insights,
    extract_lingsan_data,
)

# 创建消费分析蓝图
admin_bp_consumption = Blueprint("consumption", __name__, url_prefix="/api/admin/consumption")


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


# ======================== 1. 消费总览 ========================
@admin_bp_consumption.route("/overview", methods=["GET"])
@admin_required
def get_overview():
    """获取消费数据总览统计"""
    result = get_consumption_overview()
    return jsonify(result)


# ======================== 2. 月度消费趋势 ========================
@admin_bp_consumption.route("/monthly", methods=["GET"])
@admin_required
def get_monthly():
    """获取月度消费趋势"""
    result = get_monthly_trend()
    return jsonify(result)


# ======================== 3. 年龄段消费分析 ========================
@admin_bp_consumption.route("/age", methods=["GET"])
@admin_required
def get_age():
    """获取年龄段消费分析"""
    result = get_age_analysis()
    return jsonify(result)


# ======================== 4. 消费与满意度交叉分析 ========================
@admin_bp_consumption.route("/satisfaction-cost", methods=["GET"])
@admin_required
def get_satisfaction_cost():
    """获取消费与满意度交叉分析"""
    result = get_satisfaction_cost_analysis()
    return jsonify(result)


# ======================== 5. 性别消费对比 ========================
@admin_bp_consumption.route("/gender", methods=["GET"])
@admin_required
def get_gender():
    """获取性别消费对比"""
    result = get_gender_analysis()
    return jsonify(result)


# ======================== 6. 停留时长与消费关系 ========================
@admin_bp_consumption.route("/stay-cost", methods=["GET"])
@admin_required
def get_stay_cost():
    """获取停留时长与消费关系"""
    result = get_stay_cost_analysis()
    return jsonify(result)


# ======================== 7. 景区类型消费对比 ========================
@admin_bp_consumption.route("/type", methods=["GET"])
@admin_required
def get_type():
    """获取景区类型消费对比"""
    result = get_type_analysis()
    return jsonify(result)


# ======================== 8. 运营分析建议 ========================
@admin_bp_consumption.route("/insights", methods=["GET"])
@admin_required
def get_insights():
    """获取运营分析建议"""
    result = get_operational_insights()
    return jsonify(result)


# ======================== 9. CSV上传与筛选 ========================
@admin_bp_consumption.route("/upload", methods=["POST"])
@admin_required
def upload_csv():
    """上传CSV文件并提取灵山景区消费数据"""
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "未上传文件"})

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"code": 400, "message": "文件为空"})

    # 检查文件扩展名
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext != "csv":
        return jsonify({"code": 400, "message": "仅支持CSV格式文件"})

    # 保存上传文件到临时目录
    temp_dir = tempfile.gettempdir()
    temp_filepath = os.path.join(temp_dir, file.filename)
    file.save(temp_filepath)

    try:
        # 调用服务层提取灵山景区数据
        result = extract_lingsan_data(temp_filepath)
        return jsonify(result)
    except Exception as e:
        return jsonify({"code": 500, "message": f"文件处理失败：{str(e)}"})
    finally:
        # 清理临时文件
        try:
            if os.path.exists(temp_filepath):
                os.unlink(temp_filepath)
        except:
            pass
