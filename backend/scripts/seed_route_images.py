"""
==============================================================
灵山路线主题图片生成脚本
为10条预设路线生成符合主题风格的高清展示图片（PIL生成，零网络依赖）
首次运行后端时自动执行：从 PRESERVED_ROUTES 匹配生成图片并写入 route.bg_image
==============================================================
"""
import os
import sys
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 10条路线的主题配色与文字（从 PRESERVED_ROUTES 提取）
ROUTE_IMAGES = [
    {
        "id": 1,
        "title": "灵山大佛·文化朝圣",
        "subtitle": "88米大佛 · 佛教文化精华",
        "filename": "route_01_culture_buddha.png",
        # 金色 + 深绿，大佛主题
        "colors": [("#2a4a2a", 0.0), ("#3a6b3a", 0.3), ("#5b8c5a", 0.6), ("#8f6a30", 0.85), ("#c8a45c", 1.0)],
        "accent": "#f5c842",
    },
    {
        "id": 2,
        "title": "太湖风光·自然路线",
        "subtitle": "菩提大道 · 山水如画",
        "filename": "route_02_nature_lakeshore.png",
        "colors": [("#1a3a5a", 0.0), ("#2e7d32", 0.3), ("#4caf50", 0.6), ("#81c784", 0.85), ("#b8e6c8", 1.0)],
        "accent": "#81c784",
    },
    {
        "id": 3,
        "title": "亲子欢乐·家庭路线",
        "subtitle": "九龙灌浴 · 百子戏弥勒",
        "filename": "route_03_family_children.png",
        "colors": [("#5a2a0a", 0.0), ("#bf360c", 0.3), ("#e65100", 0.55), ("#ff9800", 0.8), ("#ffd180", 1.0)],
        "accent": "#ffcc80",
    },
    {
        "id": 4,
        "title": "禅茶一味·禅意路线",
        "subtitle": "灵山精舍 · 静心品茗",
        "filename": "route_04_zen_tea.png",
        "colors": [("#2a1a0a", 0.0), ("#3e2723", 0.3), ("#5d4037", 0.55), ("#8d6e55", 0.8), ("#c9b8a0", 1.0)],
        "accent": "#d7ccc8",
    },
    {
        "id": 5,
        "title": "梵宫穹顶·摄影路线",
        "subtitle": "绝美机位 · 出片圣地",
        "filename": "route_05_photo_pagoda.png",
        "colors": [("#1a0a2a", 0.0), ("#4a148c", 0.3), ("#7b1fa2", 0.55), ("#ab47bc", 0.8), ("#e1bee7", 1.0)],
        "accent": "#ce93d8",
    },
    {
        "id": 6,
        "title": "素斋雅集·美食路线",
        "subtitle": "祥符禅寺 · 八宝素面",
        "filename": "route_06_food_vegarian.png",
        "colors": [("#2a0a1a", 0.0), ("#880e4f", 0.3), ("#c2185b", 0.55), ("#e91e63", 0.8), ("#f8bbd0", 1.0)],
        "accent": "#f48fb1",
    },
    {
        "id": 7,
        "title": "曼飞龙塔·建筑艺术",
        "subtitle": "傣式佛塔 · 飞檐斗拱",
        "filename": "route_07_architecture_tower.png",
        "colors": [("#0a1a2a", 0.0), ("#0d47a1", 0.3), ("#1565c0", 0.55), ("#2196f3", 0.8), ("#bbdefb", 1.0)],
        "accent": "#90caf9",
    },
    {
        "id": 8,
        "title": "千年古刹·历史路线",
        "subtitle": "祥符禅寺 · 佛教渊源",
        "filename": "route_08_history_temple.png",
        "colors": [("#1a1a1a", 0.0), ("#263238", 0.3), ("#455a64", 0.55), ("#607d8b", 0.8), ("#b0bec5", 1.0)],
        "accent": "#90a4ae",
    },
    {
        "id": 9,
        "title": "慢享灵山·休闲路线",
        "subtitle": "品茶听禅 · 悠然全天",
        "filename": "route_09_leisure_garden.png",
        "colors": [("#0a2a2a", 0.0), ("#004d40", 0.3), ("#00796b", 0.55), ("#009688", 0.8), ("#80cbc4", 1.0)],
        "accent": "#a7d7d0",
    },
    {
        "id": 10,
        "title": "必去精华·速游路线",
        "subtitle": "大佛·梵宫·九龙灌浴",
        "filename": "route_10_quick_essence.png",
        "colors": [("#2a0a0a", 0.0), ("#b71c1c", 0.3), ("#d32f2f", 0.55), ("#f44336", 0.8), ("#ef9a9a", 1.0)],
        "accent": "#ffab91",
    },
]

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def draw_decorative_elements(draw, img_w, img_h, color: tuple, accent: tuple):
    """在渐变背景上绘制灵山主题装饰元素（半透明几何图案）"""
    import random
    random.seed(42)

    # 远处山峦剪影
    def draw_mountain(base_y, amplitude, color_override=None):
        c = color_override or (*color, 60)
        points = [((0, img_h))]
        x = 0
        while x < img_w:
            y = base_y - amplitude * (0.5 + 0.5 * abs(sin_approx(x / img_w * 6)))
            points.append((x, int(y)))
            x += max(1, img_w // 40)
        points.append((img_w, img_h))
        draw.polygon(points, fill=c)

    # 佛塔/建筑轮廓
    def draw_pagoda(x, y, size):
        c = (*accent, 70)
        # 塔身
        draw.polygon([
            (x, y - size),
            (x - size // 2, y),
            (x + size // 2, y)
        ], fill=c)
        # 塔顶
        draw.polygon([
            (x, y - size - size // 3),
            (x - size // 4, y - size),
            (x + size // 4, y - size)
        ], fill=c)

    def sin_approx(x):
        import math
        return math.sin(x)

    # 山峦三层
    draw_mountain(img_h * 0.7, img_h * 0.18)
    draw_mountain(img_h * 0.6, img_h * 0.12, color_override=(*color, 50))
    draw_mountain(img_h * 0.52, img_h * 0.08, color_override=(*color, 40))

    # 佛塔
    draw_pagoda(img_w * 0.35, img_h * 0.52, img_w * 0.08)
    draw_pagoda(img_w * 0.65, img_h * 0.55, img_w * 0.06)

    # 光晕（从顶部向下）
    import math
    for i in range(8):
        alpha = 20 - i * 2
        if alpha < 1:
            break
        r = img_w * (0.15 + i * 0.04)
        cx = img_w * 0.5
        cy = img_h * 0.15
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     outline=(*accent, alpha), width=2)

    # 底部水面反光线条
    for i in range(5):
        y_pos = img_h * (0.82 + i * 0.03)
        alpha = 30 - i * 5
        line_color = (*accent, alpha)
        offset = i * 20
        draw.line([(offset, y_pos), (img_w - offset, y_pos)],
                  fill=line_color, width=1)


def generate_route_image(info: dict, output_dir: str):
    """生成单张路线主题图片"""
    img_w, img_h = 800, 500
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    colors = info["colors"]
    accent_hex = info["accent"]
    accent = hex_to_rgb(accent_hex)

    # 1. 绘制垂直渐变背景
    for y in range(img_h):
        ratio = y / img_h
        # 在 colors 中找到颜色
        idx = 0
        for i in range(len(colors) - 1):
            if ratio <= colors[i+1][1]:
                idx = i
                break
        c1_hex, c1_t = colors[idx]
        c2_hex, c2_t = colors[idx + 1]
        t = (ratio - c1_t) / (c2_t - c1_t) if c2_t != c1_t else 0
        c1 = hex_to_rgb(c1_hex)
        c2 = hex_to_rgb(c2_hex)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        draw.line([(0, y), (img_w, y)], fill=(r, g, b, 255))

    # 2. 绘制装饰元素
    bg_color = hex_to_rgb(colors[0][0])
    draw_decorative_elements(draw, img_w, img_h, bg_color, accent)

    # 3. 文字（title + subtitle）
    title = info["title"]
    subtitle = info["subtitle"]

    # 尝试使用系统字体
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "C:\\Windows\\Fonts\\msyhbd.ttf",
        "C:\\Windows\\Fonts\\simhei.ttf",
    ]
    font_large = None
    font_small = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font_large = ImageFont.truetype(fp, 40)
                font_small = ImageFont.truetype(fp, 22)
                break
            except Exception:
                continue
    if font_large is None:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # 文字阴影
    def draw_text_shadow(text, font, x, y, fill):
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 120))

    # 标题
    draw_text_shadow(title, font_large, img_w // 2 - 140, img_h * 0.42, (255, 255, 255, 220))
    draw.text((img_w // 2 - 140, img_h * 0.42), title, font=font_large, fill=(255, 255, 255, 255))

    # 副标题
    draw_text_shadow(subtitle, font_small, img_w // 2 - 90, img_h * 0.55, accent + (180,))
    draw.text((img_w // 2 - 90, img_h * 0.55), subtitle, font=font_small, fill=accent + (255,))

    # 4. 底部灵山胜境水印
    draw.text((img_w // 2 - 55, img_h - 35), "Lingshan · 灵山胜境",
              font=font_small,
              fill=(255, 255, 255, 120))

    # 5. 转换为 RGB 保存为 PNG
    img_rgb = Image.new("RGB", (img_w, img_h), (255, 255, 255))
    img_rgb.paste(img, mask=img.split()[-1] if len(img.split()) == 4 else None)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, info["filename"])
    img_rgb.save(output_path, "PNG", quality=95)
    return output_path


def seed_route_images():
    """生成所有路线图片并更新数据库 bg_image 字段"""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    uploads_dir = os.path.join(backend_dir, "uploads", "route_images")

    if not HAS_PIL:
        print("[!] PIL/Pillow 未安装，跳过图片生成（pip install Pillow）")
        return 0

    generated = []
    for info in ROUTE_IMAGES:
        output_path = generate_route_image(info, uploads_dir)
        image_path = f"/uploads/route_images/{info['filename']}"
        generated.append((info["id"], image_path))
        print(f"[✓] 已生成: {info['filename']} → route#{info['id']}")

    # 更新数据库
    db_path = os.path.join(backend_dir, "lingshan.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            for route_id, image_path in generated:
                cursor.execute(
                    "UPDATE route SET bg_image = ? WHERE id = ?",
                    (image_path, route_id)
                )
            conn.commit()
            print(f"[✓] 已更新数据库：{len(generated)} 条路线的 bg_image 字段")
            conn.close()
        except Exception as e:
            print(f"[!] 更新数据库失败: {e}")
    else:
        print(f"[!] 数据库文件不存在: {db_path}，跳过数据库更新")

    return len(generated)


if __name__ == "__main__":
    print("=" * 50)
    print("灵山胜境路线主题图片生成器")
    print("=" * 50)
    count = seed_route_images()
    print(f"\n完成！共生成 {count} 张路线主题图片")
