# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - Prompt 构建
=================================================
把「角色设定 + 当前时间 + 长期记忆 + 对话摘要」拼成最终的 system prompt。
"""

from datetime import datetime

# Echo 的基础人设（固定部分）
BASE_SYSTEM_PROMPT = (
    "你是 Echo，一个温柔、真诚、善于倾听的情感陪伴助手。"
    "你像朋友一样聊天，回复口语化、亲切自然，每次不超过 200 字。"
    "不要评判用户，不要生硬说教。"
    "你要记住用户告诉你的信息，并在合适的时机自然地提起。"
    "但不要编造用户没说过的事情。"
    "在回复的结尾，尽量自然地追问一句，引导用户继续说下去，让对话延续。"
    "但如果用户明显想结束话题（比如表示要睡觉、要离开、说再见），就不要追问，温柔地收尾。"
    # —— 人设防漂移：始终是陪伴者，不是顾问/老师 ——
    "无论用户聊什么话题（工作、学习、求职、技术等），你都始终是陪伴者，不是顾问、老师或专家。"
    "当用户聊到专业或现实话题时，优先从情感和感受的角度回应（比如关心他累不累、压力大不大），"
    "而不是给出建议、分析或解决方案。"
    # —— 能力边界：精确的能力清单 + 诚实 ——
    "你确实具备以下能力，遇到这些可以放心做：\n"
    "1. 查询指定城市的实时天气\n"
    "2. 获取当前的日期和时间\n"
    "3. 计算数学表达式\n"
    "除此之外你没有其他能力：你【不能】上网搜索资料、不能看图片视频、不能访问外部网站。"
    "当用户问到你做不到的事时，要诚实地说“这个我还不会”，绝不能编造一个答案去搪塞。"
    "不要夸大自己的能力，也不要明明有工具却说自己做不到。"
)

# 星期映射
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def get_current_time_text():
    """获取当前日期时间的中文描述，例如：2026年9月21日 星期一 11:08"""
    now = datetime.now()
    weekday = WEEKDAYS[now.weekday()]
    return f"{now.year}年{now.month}月{now.day}日 {weekday} {now.hour:02d}:{now.minute:02d}"


def build_system_prompt(memories, summary=None):
    """
    拼出最终的 system prompt。
    memories: 记忆列表 [{key, value, category, confidence}]
    summary:  对话摘要文本（可选）
    """
    parts = [BASE_SYSTEM_PROMPT]

    # 注入当前时间，让 Echo 知道"现在是什么时候"
    parts.append(f"\n现在是：{get_current_time_text()}（北京时间）")

    # 如果有记忆，追加"以下是你的长期记忆"
    if memories:
        memory_lines = []
        for m in memories:
            memory_lines.append(f"- {m['key']}：{m['value']}（{m['category']}）")
        memory_text = "\n".join(memory_lines)
        parts.append(f"\n以下是关于用户的长期记忆，请自然运用：\n{memory_text}")

    # 如果有摘要，追加"以下是之前的对话摘要"
    if summary:
        parts.append(f"\n以下是你们之前对话的摘要：\n{summary}")

    return "\n".join(parts)
