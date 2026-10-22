# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 安全兜底服务
=================================================
当用户出现自我伤害/自杀倾向等极端风险信号时，
在正常回复后追加安全引导，体现产品的责任感。

识别范围刻意收敛：只识别最严重的极端风险，
避免把"普通情绪低落"误判成危险，破坏陪伴的自然感。
"""

# 风险识别 prompt
RISK_PROMPT = """请判断下面这句话是否包含"自我伤害或自杀倾向"的明确信号。

只输出一个词：是 或 否，不要输出任何其他内容。

注意：
1. 只有明确表达"不想活、结束生命、伤害自己"等极端信号才输出"是"
2. 普通情绪低落（如"好烦""压力大""心情不好"）请输出"否"

用户的话：{user_text}
"""

# 安全引导话术（高风险时追加）
SAFETY_GUIDANCE = (
    "\n\n——\n\n"
    "听到你这么说，我很担心你。你现在感受到的痛苦是真实的，"
    "但它不是你的全部，也请一定不要一个人扛着。\n\n"
    "如果此刻你感到非常难受，可以试着联系一位你信任的人，"
    "或拨打心理援助热线，会有专业的人愿意陪你聊聊。"
    "你值得被好好对待，也值得被帮助。"
)


class SafetyService:
    def __init__(self, client):
        self.client = client

    def is_high_risk(self, user_text):
        """
        判断这句话是否包含极端风险信号。
        返回 True（高风险）或 False（正常）。
        识别失败时返回 False（宁可不误判，也不乱触发）。
        """
        prompt = RISK_PROMPT.format(user_text=user_text)
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # 风险判断要非常稳定、保守
            )
            raw = response.choices[0].message.content.strip()
        except Exception:
            return False

        # 只有明确回答"是"才触发
        return "是" in raw and "否" not in raw
