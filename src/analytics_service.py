# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 情绪洞察服务
=================================================
把记录的情绪数据"用起来"：
    1. 可视化：按天聚合，画情绪趋势折线图 + 分布饼图
    2. 洞察：用 LLM 总结最近的情绪规律，生成人性化关怀

复用项目一学到的 matplotlib 能力。
"""

import io
from collections import Counter
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # 不弹窗，输出到内存
import matplotlib.pyplot as plt

from src import db
from src.emotion_service import get_emotion_score

# 中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


def _emotions_by_day(emotions):
    """
    把情绪记录按天聚合成 {日期: 平均情绪分}。
    日期格式取 created_at 的前 10 位（YYYY-MM-DD）。
    """
    daily = {}
    for e in emotions:
        day = e["created_at"][:10]
        score = get_emotion_score(e["emotion"])
        daily.setdefault(day, []).append(score)
    # 求每天的平均分
    return {day: sum(scores) / len(scores) for day, scores in daily.items()}


def build_trend_chart(emotions):
    """
    画情绪趋势折线图，返回 PNG 图片的字节流。
    横轴=日期，纵轴=平均情绪分。
    """
    daily = _emotions_by_day(emotions)
    if not daily:
        return None

    # 按日期排序
    days = sorted(daily.keys())
    scores = [daily[d] for d in days]

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(days, scores, marker="o", color="#E8683B", linewidth=2)
    ax.axhline(0, color="#cccccc", linestyle="--", linewidth=1)  # 0 基线
    ax.set_title("情绪趋势")
    ax.set_xlabel("日期")
    ax.set_ylabel("情绪分（正=积极，负=消极）")
    ax.set_ylim(-2.5, 2.5)
    plt.xticks(rotation=30)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def build_distribution_chart(emotions):
    """
    画情绪分布饼图，返回 PNG 字节流。
    四种情绪各占多少比例。
    """
    if not emotions:
        return None

    counter = Counter(e["emotion"] for e in emotions)
    labels = list(counter.keys())
    sizes = list(counter.values())

    fig, ax = plt.subplots(figsize=(4, 4))
    colors = {"开心": "#F4B183", "平静": "#A5C8E1", "难过": "#8EA9C1", "焦虑": "#E8A87C"}
    color_list = [colors.get(l, "#cccccc") for l in labels]
    ax.pie(sizes, labels=labels, autopct="%.0f%%", startangle=90, colors=color_list)
    ax.set_title("情绪分布")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


# 情绪洞察 prompt
INSIGHT_PROMPT = """以下是用户最近一段时间的情绪记录（格式：日期 情绪）：

{emotion_list}

请用 2-3 句话，温柔地总结用户的情绪状态，并给出恰到好处的关心。
注意：
1. 语气要像朋友，自然、不评判、不说教
2. 如果负面情绪偏多，表达关心，但不要夸大、不要危言耸听
3. 不要编造记录里没有的信息
"""


class AnalyticsService:
    def __init__(self, client):
        self.client = client

    def generate_insight(self, emotions):
        """
        用 LLM 根据情绪记录生成一段洞察/关怀文本。
        情绪记录太少时返回 None。
        """
        if len(emotions) < 3:
            return None

        # 把情绪记录拼成文本
        lines = [f"{e['created_at'][:10]} {e['emotion']}" for e in emotions]
        prompt = INSIGHT_PROMPT.format(emotion_list="\n".join(lines))

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None
