"""
==============================================================
情绪分析服务模块
根据AI回复文本分析情绪标签，用于驱动数字人面部表情
==============================================================
"""

import re
from typing import Tuple


class EmotionService:
    """
    情绪分析服务
    根据AI回复文本内容，判断回复时的情绪标签
    支持：平静、微笑、热情
    """

    def __init__(self):
        # 热情关键词
        self.热情_keywords = [
            "推荐", "强烈", "太棒", "绝佳", "必去", "不容错过",
            "震撼", "惊叹", "美不胜收", "赏心悦目", "极致",
            "一定要", "非常值得", "最", "特别推荐", "超赞"
        ]
        # 微笑关键词
        self.微笑_keywords = [
            "适合", "不错", "可以", "舒适", "惬意", "悠然",
            "放松", "宁静", "平和", "温柔", "美好", "愉快",
            "轻松", "开心", "享受", "满意", "温馨", "惬意"
        ]

    def analyze(self, text: str) -> Tuple[str, float]:
        """
        分析文本情绪

        参数：
            text: AI回复文本

        返回：
            (情绪标签, 置信度)
            情绪标签："热情" / "微笑" / "平静"
        """
        if not text:
            return "平静", 0.0

        # 统计各类关键词出现次数
        text_lower = text
        excitement_count = sum(1 for kw in self.热情_keywords if kw in text_lower)
        smile_count = sum(1 for kw in self.微笑_keywords if kw in text_lower)

        # 检测感叹号（通常表示热情）
        exclamation_count = text.count("！") + text.count("!")

        # 加权计算
        excitement_score = excitement_count + exclamation_count * 0.5
        smile_score = smile_count * 0.6

        total = excitement_score + smile_score

        if excitement_score > smile_score and excitement_score >= 1:
            confidence = min(0.5 + excitement_score * 0.1, 1.0)
            return "热情", round(confidence, 2)
        elif smile_score > 0:
            confidence = min(0.4 + smile_score * 0.1, 1.0)
            return "微笑", round(confidence, 2)
        else:
            return "平静", 0.6

    def get_emotion_label(self, text: str) -> str:
        """获取情绪标签简写"""
        label, _ = self.analyze(text)
        return label


# ======================== 全局单例 ========================
_emotion_service = None


def get_emotion_service() -> EmotionService:
    """获取情绪服务单例"""
    global _emotion_service
    if _emotion_service is None:
        _emotion_service = EmotionService()
    return _emotion_service
