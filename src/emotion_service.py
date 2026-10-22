# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 情绪识别服务
=================================================
用 LLM 识别用户话语中的情绪，归入固定四类。
思路与记忆提取、摘要一致：让大模型理解语义。
"""

from src import db

# 固定四类情绪
EMOTIONS = ["开心", "平静", "难过", "焦虑"]

# 情绪对应图标
EMOTION_ICONS = {
    "开心": "😊",
    "平静": "😌",
    "难过": "😢",
    "焦虑": "😰",
}

# 情绪对应的数值（用于画趋势图）
EMOTION_SCORES = {
    "开心": 2,
    "平静": 0,
    "难过": -2,
    "焦虑": -1,
}


def get_emotion_icon(emotion):
    return EMOTION_ICONS.get(emotion, "😐")


def get_emotion_score(emotion):
    return EMOTION_SCORES.get(emotion, 0)


# 情绪识别 prompt
EMOTION_PROMPT = """请判断下面这句话所表达的情绪。

只输出以下四种情绪之一，不要输出任何其他内容：开心、平静、难过、焦虑

用户的话：{user_text}
"""


class EmotionService:
    def __init__(self, client):
        self.client = client

    def detect_emotion(self, user_text):
        """
        识别一句话的情绪，返回四种之一。
        识别失败时返回 "平静"（兜底，不阻塞对话）。
        """
        prompt = EMOTION_PROMPT.format(user_text=user_text)
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # 识别要稳定
            )
            raw = response.choices[0].message.content.strip()
        except Exception:
            return "平静"

        # 归一化：只接受四种情绪，其他归"平静"
        for e in EMOTIONS:
            if e in raw:
                return e
        return "平静"
