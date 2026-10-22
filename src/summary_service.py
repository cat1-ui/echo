# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 摘要服务
=================================================
当对话过长时，用 LLM 把旧消息"压缩"成简短摘要，
后续请求只需发送"摘要 + 最近消息"，降低 token 成本。

采用「增量摘要」策略：
    每满 20 条新消息，只总结"上次摘要之后新产生的"那一批。
"""

from src import db

# 每隔多少条消息做一次摘要
SUMMARY_INTERVAL = 20

# 摘要 prompt 模板
SUMMARY_PROMPT = """请用 100 字以内总结下面这段对话，保留用户的关键信息和情绪变化。

只输出摘要文本，不要输出任何其他内容。

对话内容：
{history}
"""

# 生成会话标题的 prompt 模板
TITLE_PROMPT = """请根据用户这句话，生成一个简短的会话标题（不超过 8 个字）。

只输出标题本身，不要加引号、标点或其他内容。

用户的话：{user_text}
"""


class SummaryService:
    def __init__(self, client):
        self.client = client

    def generate_summary(self, messages):
        """把一段消息列表总结成 100 字摘要"""
        # 把消息拼成可读的对话文本
        lines = []
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role}：{msg['content']}")
        history_text = "\n".join(lines)

        prompt = SUMMARY_PROMPT.format(history=history_text)
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # 摘要要稳定，温度低一些
        )
        return response.choices[0].message.content.strip()


def generate_title(client, user_text):
    """根据用户第一句话，用 LLM 生成一个短标题"""
    prompt = TITLE_PROMPT.format(user_text=user_text)
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    title = response.choices[0].message.content.strip()
    # 兜底：如果生成失败或太长，截断
    return title[:12] if title else "新对话"


def maybe_summarize(conversation_id, summary_service):
    """
    检查是否需要做增量摘要，需要就执行。
    逻辑：
        当前消息总数 - 已摘要到的位置 >= 20 条时，触发摘要。
    """
    total = db.count_messages(conversation_id)

    # 取最新的摘要信息（含它覆盖到哪条消息）
    latest = db.get_latest_summary_info(conversation_id)
    last_pos = latest["last_message_id"] if latest else 0  # 没有摘要则从 0 开始

    # 还没满 20 条新消息，不做
    if total - last_pos < SUMMARY_INTERVAL:
        return

    # 找出"上次摘要之后新产生的"消息（id 在 last_pos 之后）
    # 但我们要总结到"最近的整批"，即只总结到当前消息数对应的位置
    # 简化：直接取 (last_pos, 当前最新) 之间的消息来总结
    new_messages = db.get_messages_range(conversation_id, last_pos, 999999999)

    if not new_messages:
        return

    # 生成摘要
    summary_text = summary_service.generate_summary(new_messages)

    # 记录这次摘要覆盖到的最后一条消息 id
    # 通过查最新的消息 id 得到
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(id) AS max_id FROM messages WHERE conversation_id=?",
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()
    max_id = row["max_id"]

    # 保存摘要（含位置）
    db.save_summary_with_pos(conversation_id, summary_text, max_id)
