"""
==============================================================
灵山胜境路线规划服务
提供路线库（数据库优先）、大模型个性化推荐、用户偏好分析

架构说明：
  1. 优先从数据库 Route/RouteSpot 表读取数据
  2. 若数据库为空，回退到 PRESERVED_ROUTES 硬编码数据
  3. 支持内存缓存（TTL 60秒）提升性能，响应时间 <50ms
  4. 管理员更新路线时自动同步到知识库（游览路线分类）
==============================================================
"""
import os
import sys
import json
import random
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db, User, ChatLog

# ============================================================
# 缓存配置
# ============================================================
_route_cache = {}
_ROUTE_CACHE_TTL = 60  # 缓存有效期（秒）

_CACHE_KEY_ALL = "all_routes"
_CACHE_KEY_DETAIL = "route_detail_{}"
_CACHE_KEY_STYLE = "routes_style_{}"
_CACHE_KEY_TAGS = "routes_tags_{}"
_CACHE_KEY_DEFAULT = "default_route"


def _clear_route_cache():
    """清除全部路线缓存"""
    _route_cache.clear()


def _get_cached(key: str) -> (bool, any):
    """获取缓存，返回 (命中?, 数据)"""
    entry = _route_cache.get(key)
    if entry and time.time() - entry["time"] < _ROUTE_CACHE_TTL:
        return True, entry["data"]
    return False, None


def _set_cache(key: str, data):
    """写入缓存"""
    _route_cache[key] = {"data": data, "time": time.time()}


# ============================================================
# 10 条预设路线（降级回退，数据库为空时使用）
# ============================================================
PRESERVED_ROUTES = [
    {
        "id": 1,
        "title": "文化朝圣路线",
        "subtitle": "3小时精华游",
        "style": "culture",
        "style_label": "文化",
        "tags": ["佛教文化", "精华", "快节奏", "经典"],
        "icon": "🙏",
        "color": "#5b8c5a",
        "description": "适合时间有限但想深度体验佛教文化的游客，以灵山胜境核心佛教文化景点为主线。",
        "duration": "约3小时",
        "difficulty": "低",
        "best_time": "上午 8:00-11:00",
        "spots": [
            {"name": "南门（入口）", "description": "从景区南门入园，开启朝圣之旅"},
            {"name": "佛足坛", "description": "参观佛陀足迹石刻，感受佛教文化传承"},
            {"name": "九龙灌浴", "description": "观赏九龙灌浴表演，聆听释迦牟尼诞生故事"},
            {"name": "祥符禅寺", "description": "千年古刹，灵山佛教文化的发源地"},
            {"name": "灵山大佛", "description": "登顶88米大佛，抱佛脚祈福，俯瞰太湖全景"},
            {"name": "梵宫", "description": "欣赏佛教艺术殿堂，观看《吉祥颂》演出"},
            {"name": "五印坛城", "description": "体验藏传佛教文化，欣赏唐卡艺术"}
        ],
        "tips": "建议上午9点前入园，先看九龙灌浴表演，再登大佛",
        "distance_km": 2.5
    },
    {
        "id": 2,
        "title": "自然风光路线",
        "subtitle": "5小时全景游",
        "style": "nature",
        "style_label": "自然",
        "tags": ["自然风光", "户外", "慢节奏", "摄影"],
        "icon": "🌄",
        "color": "#4caf50",
        "description": "适合喜欢户外自然风光的游客，融合太湖山水与佛教园林景观。",
        "duration": "约5小时",
        "difficulty": "中",
        "best_time": "全天 8:00-13:00",
        "spots": [
            {"name": "南门（入口）", "description": "从南门入园，开始全景之旅"},
            {"name": "佛足坛", "description": "参观佛陀足迹石刻"},
            {"name": "九龙灌浴", "description": "观赏动态水景表演，接取祈福圣水"},
            {"name": "菩提大道", "description": "漫步菩提大道，欣赏太湖与青龙山、白虎山自然风貌"},
            {"name": "灵山大佛", "description": "登顶俯瞰太湖全景，拍摄绝美日落照片"},
            {"name": "曼飞龙塔", "description": "欣赏傣族佛教建筑风格与园林景观"},
            {"name": "灵山精舍", "description": "体验禅意园林，品尝素斋"},
            {"name": "梵宫广场", "description": "在梵宫广场结束旅程，感受建筑之美"}
        ],
        "tips": "建议上午入园，自带相机，在灵山大佛平台拍摄太湖日落",
        "distance_km": 4.0
    },
    {
        "id": 3,
        "title": "亲子家庭路线",
        "subtitle": "4小时轻松游",
        "style": "family",
        "style_label": "亲子",
        "tags": ["亲子", "家庭", "轻松", "互动"],
        "icon": "👨‍👩‍👧‍👦",
        "color": "#ff9800",
        "description": "适合带孩子的家庭游客，互动性强，轻松愉快。",
        "duration": "约4小时",
        "difficulty": "低",
        "best_time": "上午 9:00-13:00",
        "spots": [
            {"name": "南门（入口）", "description": "从南门入园，开启亲子之旅"},
            {"name": "九龙灌浴", "description": "观赏动态表演，听佛陀诞生的故事"},
            {"name": "佛手广场", "description": "摸'天下第一掌'，祈福平安"},
            {"name": "百子戏弥勒", "description": "与形态各异的孩童雕塑互动拍照"},
            {"name": "梵宫", "description": "欣赏色彩缤纷的艺术作品，观看《吉祥颂》"},
            {"name": "五印坛城", "description": "体验藏式文化，转动经筒"}
        ],
        "tips": "参加抱佛脚亲子活动，品尝素面套餐，在百子戏弥勒前拍照留念",
        "distance_km": 2.0
    },
    {
        "id": 4,
        "title": "禅意体验路线",
        "subtitle": "4小时静心游",
        "style": "zen",
        "style_label": "禅意",
        "tags": ["禅意", "静心", "茶道", "素食"],
        "icon": "🍵",
        "color": "#795548",
        "description": "适合追求心灵宁静的游客，体验禅茶一味，感受慢生活。",
        "duration": "约4小时",
        "difficulty": "低",
        "best_time": "上午 9:00-13:00",
        "spots": [
            {"name": "南门（入口）", "description": "从南门入园，静心出发"},
            {"name": "灵山精舍", "description": "在禅意园林中品一杯清茶，聆听禅乐"},
            {"name": "祥符禅寺", "description": "跟随僧人晨课，感受梵音袅袅"},
            {"name": "曼飞龙塔", "description": "静坐塔下，观鸟听风"},
            {"name": "灵山大佛", "description": "大佛脚下静立片刻，默念心愿"},
            {"name": "梵宫", "description": "观赏素食文化展览，品尝素斋"}
        ],
        "tips": "穿着宽松舒适，放慢节奏，重点体验禅意氛围",
        "distance_km": 2.8
    },
    {
        "id": 5,
        "title": "摄影打卡路线",
        "subtitle": "3.5小时出片游",
        "style": "photo",
        "style_label": "摄影",
        "tags": ["摄影", "打卡", "拍照", "视觉"],
        "icon": "📸",
        "color": "#9c27b0",
        "description": "专为摄影爱好者设计，精选最佳拍摄点位，保证出片率。",
        "duration": "约3.5小时",
        "difficulty": "中",
        "best_time": "上午 8:00-11:30 / 下午 15:00-17:30",
        "spots": [
            {"name": "菩提大道", "description": "银杏大道全景机位，逆光效果最佳"},
            {"name": "九龙灌浴", "description": "抓拍九龙喷水瞬间，建议长焦"},
            {"name": "灵山大佛", "description": "仰拍大佛全景，或从大佛台俯瞰太湖"},
            {"name": "梵宫", "description": "内部穹顶与彩窗，适合广角镜头"},
            {"name": "五印坛城", "description": "藏式建筑细节，建议微距"},
            {"name": "佛足坛", "description": "石刻纹理特写，晨光柔和"}
        ],
        "tips": "建议携带三脚架和偏振镜，上午光线最适合人物拍摄",
        "distance_km": 3.0
    },
    {
        "id": 6,
        "title": "美食探索路线",
        "subtitle": "3小时味蕾游",
        "style": "food",
        "style_label": "美食",
        "tags": ["美食", "素斋", "小吃", "品尝"],
        "icon": "🍜",
        "color": "#e91e63",
        "description": "以素斋和小吃为主线，在游览中品味灵山特色饮食文化。",
        "duration": "约3小时",
        "difficulty": "低",
        "best_time": "上午 10:00-13:00",
        "spots": [
            {"name": "南门（入口）", "description": "入口处有素面小吃店"},
            {"name": "佛足坛", "description": "品尝佛手茶，寓意吉祥如意"},
            {"name": "祥符禅寺", "description": "在禅寺斋堂体验正宗素斋"},
            {"name": "灵山精舍", "description": "品鉴素斋午宴，品尝八宝素面"},
            {"name": "梵宫", "description": "观赏素食文化展示，了解八大菜系素食版"},
            {"name": "五印坛城", "description": "享用藏式酥油茶和糌粑"}
        ],
        "tips": "建议提前了解素食禁忌，斋堂素斋11点开放",
        "distance_km": 2.3
    },
    {
        "id": 7,
        "title": "建筑艺术路线",
        "subtitle": "4小时美学游",
        "style": "architecture",
        "style_label": "建筑",
        "tags": ["建筑", "艺术", "美学", "设计"],
        "icon": "🏛️",
        "color": "#2196f3",
        "description": "聚焦建筑与艺术设计，从传统寺庙到现代艺术殿堂，感受建筑之美。",
        "duration": "约4小时",
        "difficulty": "中",
        "best_time": "全天 9:00-13:00",
        "spots": [
            {"name": "祥符禅寺", "description": "明代古建风格，飞檐斗拱，雕梁画栋"},
            {"name": "曼飞龙塔", "description": "傣族佛塔建筑，造型独特，金色塔身"},
            {"name": "灵山大佛", "description": "青铜铸造，72米高的建筑奇迹"},
            {"name": "梵宫", "description": "当代建筑艺术巅峰，穹顶与壁画"},
            {"name": "五印坛城", "description": "藏式坛城建筑，金色屋顶与彩绘"},
            {"name": "梵宫广场", "description": "广场景观设计与周边建筑群的呼应"}
        ],
        "tips": "建议提前了解各建筑风格的历史背景，欣赏更深刻",
        "distance_km": 3.2
    },
    {
        "id": 8,
        "title": "历史朝圣路线",
        "subtitle": "4.5小时深度游",
        "style": "history",
        "style_label": "历史",
        "tags": ["历史", "文化", "深度", "典故"],
        "icon": "📜",
        "color": "#607d8b",
        "description": "深入了解灵山胜境的历史典故与佛教文化渊源，适合历史爱好者。",
        "duration": "约4.5小时",
        "difficulty": "高",
        "best_time": "上午 8:00-12:30",
        "spots": [
            {"name": "祥符禅寺", "description": "千年古刹，了解灵山佛教文化起源"},
            {"name": "佛足坛", "description": "解读佛陀足迹石刻的历史意义"},
            {"name": "九龙灌浴", "description": "学习释迦牟尼诞生的佛教典故"},
            {"name": "灵山大佛", "description": "了解大佛建造历史与工程奇迹"},
            {"name": "梵宫", "description": "观赏《吉祥颂》了解佛教艺术历史"},
            {"name": "五印坛城", "description": "探索藏传佛教文化传入中土的历史"},
            {"name": "灵山精舍", "description": "了解民国时期佛教复兴运动"}
        ],
        "tips": "建议携带导游讲解设备，或提前阅读灵山历史文化资料",
        "distance_km": 3.5
    },
    {
        "id": 9,
        "title": "慢生活休闲路线",
        "subtitle": "6小时悠然游",
        "style": "leisure",
        "style_label": "休闲",
        "tags": ["休闲", "慢节奏", "放松", "全天"],
        "icon": "☕",
        "color": "#009688",
        "description": "适合周末放松，不赶时间，每个景点慢慢感受，享受禅意生活。",
        "duration": "约6小时",
        "difficulty": "低",
        "best_time": "全天 8:00-14:00",
        "spots": [
            {"name": "南门（入口）", "description": "在入口处休息区稍作休整"},
            {"name": "菩提大道", "description": "慢步漫步，欣赏沿途植物与太湖风光"},
            {"name": "灵山大佛", "description": "不急于登顶，沿途拍照留念"},
            {"name": "灵山精舍", "description": "品茶、听禅乐、体验素食午餐"},
            {"name": "曼飞龙塔", "description": "静坐塔下，感受园林氛围"},
            {"name": "梵宫", "description": "观赏演出，慢慢品味艺术细节"},
            {"name": "五印坛城", "description": "体验转经筒，许愿祈福"},
            {"name": "梵宫广场", "description": "在广场休息，总结旅程感受"}
        ],
        "tips": "建议穿舒适的鞋子，自带水杯，享受慢节奏",
        "distance_km": 3.8
    },
    {
        "id": 10,
        "title": "快速精华路线",
        "subtitle": "2小时速游",
        "style": "quick",
        "style_label": "速游",
        "tags": ["快速", "精华", "时间短", "必去"],
        "icon": "⚡",
        "color": "#f44336",
        "description": "适合只有短暂时间的游客，精选最核心的必去景点，高效游览。",
        "duration": "约2小时",
        "difficulty": "中",
        "best_time": "任意时段",
        "spots": [
            {"name": "南门（入口）", "description": "快速入园"},
            {"name": "灵山大佛", "description": "核心景点，88米高佛，必看"},
            {"name": "梵宫", "description": "建筑与艺术精华，《吉祥颂》演出"},
            {"name": "九龙灌浴", "description": "动态表演，经典必看项目"}
        ],
        "tips": "建议优先观看九龙灌浴表演时间，其他时间灵活安排",
        "distance_km": 1.8
    }
]


def _db_to_route_dict(route) -> dict:
    """将 Route ORM 对象转换为与 PRESERVED_ROUTES 兼容的 dict 格式"""
    return {
        "id": route.id,
        "title": route.title,
        "subtitle": route.subtitle,
        "style": route.style,
        "style_label": route.style_label,
        "tags": [t.strip() for t in route.tags.split(",") if t.strip()] if route.tags else [],
        "icon": route.icon,
        "color": route.color,
        "description": route.description,
        "duration": route.duration,
        "difficulty": route.difficulty,
        "best_time": route.best_time,
        "spots": [
            {
                "name": s.name,
                "description": s.description,
                "latitude": s.latitude,
                "longitude": s.longitude
            }
            for s in route.spots
        ],
        "tips": route.tips,
        "distance_km": route.distance_km,
        "rating": route.rating,
        "bg_image": route.bg_image,
        "is_active": route.is_active
    }


def _load_routes_from_db():
    """从数据库加载所有启用的路线"""
    try:
        from models import Route as RouteModel
        routes = RouteModel.query.filter_by(is_active=True).order_by(RouteModel.sort_order).all()
        if routes:
            return [_db_to_route_dict(r) for r in routes]
        return None
    except Exception as e:
        print(f"[Route] 数据库加载失败: {e}")
        return None


def get_all_routes() -> list:
    """
    获取所有路线列表（完整版，包含景点）
    优先从数据库读取，回退到硬编码
    """
    # 查缓存
    hit, data = _get_cached(_CACHE_KEY_ALL)
    if hit:
        return data

    # 读数据库
    db_routes = _load_routes_from_db()
    if db_routes:
        _set_cache(_CACHE_KEY_ALL, db_routes)
        return db_routes

    # 回退硬编码
    result = [
        {
            "id": r["id"],
            "title": r["title"],
            "subtitle": r["subtitle"],
            "style": r["style"],
            "style_label": r["style_label"],
            "icon": r["icon"],
            "color": r["color"],
            "duration": r["duration"],
            "difficulty": r["difficulty"],
            "distance_km": r["distance_km"],
            "tags": r["tags"],
            "description": r["description"],
            "spots": r["spots"],
            "tips": r["tips"],
            "best_time": r["best_time"]
        }
        for r in PRESERVED_ROUTES
    ]
    _set_cache(_CACHE_KEY_ALL, result)
    return result


def get_route_detail(route_id: int) -> dict:
    """获取单条路线完整详情"""
    cache_key = _CACHE_KEY_DETAIL.format(route_id)
    hit, data = _get_cached(cache_key)
    if hit:
        return data

    # 数据库
    try:
        from models import Route as RouteModel
        route = RouteModel.query.get(route_id)
        if route and route.is_active:
            result = _db_to_route_dict(route)
            _set_cache(cache_key, result)
            return result
    except Exception:
        pass

    # 回退硬编码
    for r in PRESERVED_ROUTES:
        if r["id"] == route_id:
            _set_cache(cache_key, r)
            return r
    return None


def get_routes_by_style(style: str) -> list:
    """按风格筛选路线"""
    if style == "all":
        return get_all_routes()

    cache_key = _CACHE_KEY_STYLE.format(style)
    hit, data = _get_cached(cache_key)
    if hit:
        return data

    all_routes = get_all_routes()
    result = [r for r in all_routes if r["style"] == style]
    _set_cache(cache_key, result)
    return result


def get_routes_by_tags(tags: list) -> list:
    """按标签筛选路线"""
    if not tags:
        return get_all_routes()

    cache_key = _CACHE_KEY_TAGS.format(",".join(sorted(tags)))
    hit, data = _get_cached(cache_key)
    if hit:
        return data

    all_routes = get_all_routes()
    # 构建标签到路线的索引
    tag_to_routes = {}
    for r in all_routes:
        for tag in r.get("tags", []):
            tag_to_routes.setdefault(tag, []).append(r["id"])

    tag_ids = set()
    for tag in tags:
        tag_ids.update(tag_to_routes.get(tag, []))

    if not tag_ids:
        result = all_routes
    else:
        result = [r for r in all_routes if r["id"] in tag_ids]

    _set_cache(cache_key, result)
    return result


def get_default_route() -> dict:
    """获取默认推荐路线"""
    hit, data = _get_cached(_CACHE_KEY_DEFAULT)
    if hit:
        return data

    # 优先取 ID=1 或标记为经典的路线
    try:
        from models import Route as RouteModel
        route = RouteModel.query.filter_by(is_active=True).order_by(RouteModel.sort_order).first()
        if route:
            result = _db_to_route_dict(route)
            _set_cache(_CACHE_KEY_DEFAULT, result)
            return result
    except Exception:
        pass

    # 回退硬编码
    result = PRESERVED_ROUTES[0] if PRESERVED_ROUTES else None
    _set_cache(_CACHE_KEY_DEFAULT, result)
    return result


# 路线风格索引（兼容旧版调用）
STYLE_MAP = {}
for r in PRESERVED_ROUTES:
    STYLE_MAP[r["style"]] = r["id"]

TAG_TO_ROUTES = {}
for r in PRESERVED_ROUTES:
    for tag in r.get("tags", []):
        TAG_TO_ROUTES.setdefault(tag, []).append(r["id"])


# ============================================================
# 用户偏好分析
# ============================================================

def analyze_user_preferences(user_id: int) -> dict:
    """
    基于用户对话历史分析路线偏好
    返回：{ preferred_styles: [], preferred_tags: [], avg_duration: str }
    """
    chats = ChatLog.query.filter_by(user_id=user_id).order_by(
        ChatLog.question_time.desc()
    ).limit(50).all()

    if not chats:
        return {"preferred_styles": ["culture"], "preferred_tags": ["经典"], "avg_duration": "3小时"}

    style_scores = {"culture": 0, "nature": 0, "family": 0, "zen": 0,
                    "photo": 0, "food": 0, "architecture": 0, "history": 0,
                    "leisure": 0, "quick": 0}

    style_keywords = {
        "culture": ["佛教", "寺庙", "灵山大佛", "梵宫", "朝圣", "文化", "祥符禅寺"],
        "nature": ["太湖", "风光", "自然", "风景", "山水", "菩提大道", "摄影"],
        "family": ["孩子", "亲子", "家庭", "儿童", "百子", "轻松"],
        "zen": ["禅意", "静心", "茶", "素斋", "素食", "冥想", "宁静"],
        "photo": ["拍照", "摄影", "出片", "拍摄", "照片", "取景"],
        "food": ["美食", "素斋", "吃", "面食", "小吃", "午餐", "品尝"],
        "architecture": ["建筑", "设计", "艺术", "梵宫", "塔"],
        "history": ["历史", "典故", "故事", "由来", "起源", "传说"],
        "leisure": ["休息", "放松", "慢", "休闲", "悠然", "全天"],
        "quick": ["快", "短", "速", "时间紧", "简单"]
    }

    for chat in chats:
        text = (chat.question_text or "") + (chat.answer_text or "")
        for style, keywords in style_keywords.items():
            for kw in keywords:
                if kw in text:
                    style_scores[style] += 1

    sorted_styles = sorted(style_scores.items(), key=lambda x: -x[1])
    top_styles = [s[0] for s in sorted_styles if s[1] > 0][:3]
    if not top_styles:
        top_styles = ["culture"]

    return {
        "preferred_styles": top_styles,
        "preferred_tags": [],
        "chat_count": len(chats),
        "avg_duration": "3小时"
    }


def get_llm_recommendation(user_id: int, preferences: dict = None) -> dict:
    """
    调用大模型生成个性化路线推荐（从动态路线库中推荐）
    返回包含推荐路线ID列表和推荐理由
    """
    user = User.query.get(user_id)
    user_profile = None
    if user:
        user_profile = user.to_dict()

    ai_prefs = analyze_user_preferences(user_id)

    if preferences:
        if preferences.get("style"):
            ai_prefs["preferred_styles"] = [s for s in preferences["style"]]
        if preferences.get("duration"):
            ai_prefs["avg_duration"] = preferences["duration"]
        if preferences.get("difficulty"):
            ai_prefs["preferred_difficulty"] = preferences["difficulty"]
        if preferences.get("interests"):
            ai_prefs["preferred_tags"] = preferences["interests"]

    # 从动态路线库获取路线数据
    all_routes = get_all_routes()

    routes_info = []
    for r in all_routes:
        routes_info.append({
            "id": r["id"],
            "title": r["title"],
            "subtitle": r.get("subtitle", ""),
            "style": r["style"],
            "style_label": r.get("style_label", ""),
            "tags": r.get("tags", []),
            "duration": r.get("duration", ""),
            "difficulty": r.get("difficulty", ""),
            "description": r.get("description", ""),
            "rating": r.get("rating", 0)
        })

    system_prompt = f"""你是灵山胜境AI导游系统的路线推荐专家。请根据用户画像和偏好，从以下{len(routes_info)}条路线中推荐最合适的一条。

可推荐的路线列表：
"""
    for r in routes_info:
        tags_str = "、".join(r["tags"])
        system_prompt += f"\n[{r['id']}] {r['title']}（{r['style_label']}）\n"
        system_prompt += f"    标签: {tags_str} | 时长: {r['duration']} | 难度: {r['difficulty']} | 评分: {r['rating']}/5\n"
        system_prompt += f"    简介: {r['description']}\n"

    user_prompt = f"""
用户画像：
"""
    if user_profile:
        user_prompt += f"- 用户名: {user_profile.get('username', '匿名')}\n"
        user_prompt += f"- 对话次数: {ai_prefs.get('chat_count', 0)}\n"

    user_prompt += f"""
分析结果（基于历史对话）：
- 偏好风格: {', '.join(ai_prefs.get('preferred_styles', ['未知']))}
- 偏好标签: {', '.join(ai_prefs.get('preferred_tags', ['经典']))}
- 时间预算: {ai_prefs.get('avg_duration', '未知')}

用户手动偏好（如有）：
"""
    if preferences:
        user_prompt += f"- 偏好风格: {', '.join(preferences.get('style', ['未选择']))}\n"
        user_prompt += f"- 时间预算: {preferences.get('duration', '未选择')}\n"
        user_prompt += f"- 游览难度: {preferences.get('difficulty', '未选择')}\n"
        user_prompt += f"- 兴趣点: {', '.join(preferences.get('interests', ['未选择']))}\n"
    else:
        user_prompt += "- 未填写偏好表单\n"

    user_prompt += """
请推荐1条最合适的路线，并给出推荐理由。

严格按照以下JSON格式返回（不要输出其他内容）：
{
  "recommended_route_id": 1,
  "reason": "推荐理由...",
  "alternatives": [3, 5]
}
"""

    try:
        from services.llm_service import LLMService
        llm = LLMService()
        response = llm.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        import re
        try:
            if response.strip().startswith("{"):
                result = json.loads(response)
            else:
                match = re.search(r"\{.*\}", response, re.S)
                if match:
                    result = json.loads(match.group(0))
                else:
                    result = {
                        "recommended_route_id": all_routes[0]["id"] if all_routes else 1,
                        "reason": "基于您的历史对话，推荐此路线。",
                        "alternatives": [r["id"] for r in all_routes[1:4]] if len(all_routes) > 1 else []
                    }

            rec_id = result.get("recommended_route_id", all_routes[0]["id"] if all_routes else 1)
            return {
                "recommended_route_id": rec_id,
                "reason": result.get("reason", ""),
                "alternatives": result.get("alternatives", [])
            }
        except Exception as e:
            print(f"[Route] LLM 解析失败: {e}")
            default_route = all_routes[0] if all_routes else PRESERVED_ROUTES[0]
            return {
                "recommended_route_id": default_route["id"],
                "reason": "基于您的偏好，为您推荐此路线。",
                "alternatives": [r["id"] for r in (all_routes[1:4] if len(all_routes) > 1 else PRESERVED_ROUTES[1:4])]
            }

    except Exception as e:
        print(f"[Route] LLM 调用失败: {e}")
        default_route = all_routes[0] if all_routes else PRESERVED_ROUTES[0]
        return {
            "recommended_route_id": default_route["id"],
            "reason": "为您推荐经典路线，一次游览核心景点。",
            "alternatives": [r["id"] for r in (all_routes[1:4] if len(all_routes) > 1 else PRESERVED_ROUTES[1:4])]
        }


def collect_user_feedback(user_id: int, route_id: int, rating: int, comment: str = "") -> dict:
    """收集用户对路线的评价反馈"""
    # 评分和评论分开存储，合并到 answer_text
    answer_parts = [f"评分: {rating}星"]
    if comment and comment.strip():
        answer_parts.append(comment.strip())
    answer_text = "\n".join(answer_parts) if len(answer_parts) > 1 else answer_parts[0]

    log = ChatLog(
        user_id=user_id,
        question_text=f"路线评价 - 路线#{route_id}",
        answer_text=answer_text,
        emotion_label="反馈"
    )
    db.session.add(log)
    db.session.commit()

    return {"code": 200, "message": "反馈已提交，感谢您的评价！"}


def get_user_feedback_summary(user_id: int) -> dict:
    """获取用户的历史反馈摘要"""
    chats = ChatLog.query.filter(
        ChatLog.user_id == user_id,
        ChatLog.question_text.like("路线评价%")
    ).order_by(ChatLog.question_time.desc()).limit(10).all()

    feedbacks = []
    for chat in chats:
        match = None
        try:
            import re
            m = re.search(r"路线#(\d+)", chat.question_text or "")
            if m:
                match = int(m.group(1))
        except:
            pass

        rating_match = None
        try:
            import re
            m2 = re.search(r"评分:\s*(\d+)星", chat.answer_text or "")
            if m2:
                rating_match = int(m2.group(1))
        except:
            pass

        feedbacks.append({
            "route_id": match,
            "rating": rating_match,
            "comment": chat.answer_text,
            "time": chat.question_time.strftime("%m-%d %H:%M") if chat.question_time else ""
        })

    return {"total": len(feedbacks), "feedbacks": feedbacks}