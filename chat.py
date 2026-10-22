# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 阶段3：长期记忆
=================================================
在阶段2基础上，加入长期记忆：
    每次对话后，用 LLM 提取用户稳定信息存入 memories 表；
    下次对话时，把记忆拼进 system prompt。

运行方式：
    1. pip install openai python-dotenv
    2. .env 填好 DEEPSEEK_API_KEY
    3. python chat.py
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

from src import db
from src.memory_service import MemoryService
from src.prompt_builder import build_system_prompt

# ============ 1. 初始化 ============
load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    print("错误：未找到 DEEPSEEK_API_KEY，请检查 .env 文件")
    exit(1)

client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
db.init_db()
memory_service = MemoryService(client)


def chat_with_memory(conversation_id, user_text):
    """完整对话流程：存消息 → 取记忆+历史 → 拼 prompt → 调 API → 存回复 → 提取记忆"""
    # 1. 保存用户消息
    db.save_message(conversation_id, "user", user_text)

    # 2. 取长期记忆 + 最近历史
    memories = db.get_memories()
    history = db.get_recent_messages(conversation_id, limit=10)

    # 3. 拼 system prompt（含记忆）
    system_prompt = build_system_prompt(memories)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # 4. 调 API 生成回复
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.8,
    )
    reply = response.choices[0].message.content

    # 5. 保存助手回复
    db.save_message(conversation_id, "assistant", reply)

    # 6. 同步提取记忆（用 LLM 从本轮对话提取稳定信息）
    try:
        extracted = memory_service.extract_memories(user_text, reply)
        if extracted:
            memory_service.save_memories(extracted)
            print(f"      [已记住 {len(extracted)} 条信息]")
    except Exception as e:
        # 提取失败不影响主回复
        print(f"      [记忆提取失败：{e}]")

    return reply


def main():
    print("===== Echo 情感陪伴助手 =====")
    print("输入 quit 退出，输入 /memories 查看记忆\n")

    conversation_id = db.get_or_create_conversation()

    while True:
        user_text = input("你：").strip()
        if not user_text:
            continue
        if user_text.lower() == "quit":
            print("Echo：再见，我随时在这里。")
            break
        if user_text == "/memories":
            mems = db.get_memories()
            if not mems:
                print("      [暂无记忆]")
            for m in mems:
                print(f"      - {m['key']}：{m['value']}（{m['category']}）")
            continue

        try:
            reply = chat_with_memory(conversation_id, user_text)
            print(f"Echo：{reply}\n")
        except Exception as e:
            print(f"网络错误，请重试。（{e}）\n")


if __name__ == "__main__":
    main()
