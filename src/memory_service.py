# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 记忆服务
=================================================
核心思路：让大模型自己从对话里"提取"值得长期记住的信息。

流程：
    用户说"我叫小袁，喜欢打篮球"
        ↓
    额外调一次 LLM，给专门的提取 prompt
        ↓
    LLM 返回 JSON 数组：[{key, value, category, confidence}]
        ↓
    存入 memories 表
"""

import json
from src import db
from src.categories import CATEGORIES


# 记忆提取的 prompt 模板
EXTRACT_PROMPT = """请从下面这段对话中，提取值得长期记住的用户信息。

只输出 JSON 数组，不要输出任何其他内容，不要加代码块标记。

格式示例：
[
  {{"key": "名字", "value": "小袁", "category": "基本信息", "confidence": 0.9}},
  {{"key": "喜欢的食物", "value": "火锅", "category": "喜好", "confidence": 0.8}}
]

规则：
1. 只提取稳定、长期有效的信息（名字、年龄、职业、喜好、重要事件、情绪、目标、烦恼、习惯等）
2. 不要提取临时性的闲聊内容（比如"今天天气不错"）
3. 如果没有值得记住的信息，输出空数组 []
4. confidence 是 0 到 1 之间的置信度
5. category 只能从以下类别中选择：{categories}
   如果都不合适，归入"其他"

用户：{user_text}
助手：{assistant_text}
"""


# 把固定分类列表拼进 prompt（供 format 使用）
_CATEGORIES_STR = "、".join(CATEGORIES)


class MemoryService:
    def __init__(self, client):
        self.client = client

    def extract_memories(self, user_text, assistant_text):
        """
        调用 LLM 从对话中提取记忆。
        返回 [{key, value, category, confidence}] 列表
        """
        prompt = EXTRACT_PROMPT.format(
            user_text=user_text,
            assistant_text=assistant_text,
            categories=_CATEGORIES_STR,
        )
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,  # 提取任务要稳定，温度调低
        )
        raw = response.choices[0].message.content
        return self._parse_json(raw)

    def _parse_json(self, raw):
        """把 LLM 返回的文本解析成列表，容错处理"""
        raw = raw.strip()
        # LLM 偶尔会包一层 ```json ... ```，去掉
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            # 解析失败，返回空列表（宁可不存，也不能让程序崩）
            return []

    def save_memories(self, memories, user_id="default"):
        """把提取到的记忆写入数据库"""
        for m in memories:
            # 防御：确保字段齐全，缺失用默认值
            key = m.get("key", "").strip()
            value = m.get("value", "").strip()
            category = m.get("category", "其他")
            confidence = m.get("confidence", 0.5)
            # 归一化：如果 category 不在固定分类里，归入"其他"
            if category not in CATEGORIES:
                category = "其他"
            if key and value:  # key 和 value 都不能为空才存
                db.save_memory(user_id, key, value, category, confidence)
