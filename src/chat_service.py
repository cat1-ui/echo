# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 聊天服务（流式 + 异步版）
=================================================
核心升级：
    1. 流式输出：边生成回复边返回，用户体验像"打字机"
    2. 异步副任务：记忆提取、情绪识别、摘要放到后台线程，不阻塞主回复

流程：
    存用户消息 → 流式生成回复(边生成边 yield) → 后台线程处理副任务 → 返回
"""

import os
import json
import threading

from dotenv import load_dotenv
from openai import OpenAI

from src import db
from src import tools
from src.memory_service import MemoryService
from src.summary_service import SummaryService, maybe_summarize, generate_title
from src.emotion_service import EmotionService
from src.safety_service import SafetyService, SAFETY_GUIDANCE
from src.prompt_builder import build_system_prompt


class ChatService:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件")

        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.memory_service = MemoryService(self.client)
        self.summary_service = SummaryService(self.client)
        self.emotion_service = EmotionService(self.client)
        self.safety_service = SafetyService(self.client)
        db.init_db()
        self.conversation_id = db.get_or_create_conversation()

    def switch_conversation(self, conversation_id):
        self.conversation_id = conversation_id

    def new_conversation(self):
        self.conversation_id = db.create_conversation()
        return self.conversation_id

    def generate_greeting(self):
        """
        根据用户的长期记忆 + 最近情绪，生成一句主动的开场问候。
        让 Echo 不等待用户开口，主动关心。
        """
        memories = db.get_memories()
        recent_emotions = db.get_recent_emotions(limit=5)

        # 拼 prompt：把记忆和情绪告诉 LLM
        prompt = "你现在要主动和用户打招呼，说一句自然、温暖的问候。\n\n"

        if memories:
            lines = [f"- {m['key']}：{m['value']}" for m in memories[:10]]
            prompt += f"以下是关于用户的长期记忆：\n" + "\n".join(lines) + "\n\n"
        else:
            prompt += "你还不太了解用户。\n\n"

        if recent_emotions:
            emo_lines = [f"{e['created_at'][:10]} {e['emotion']}" for e in recent_emotions]
            prompt += f"以下是用户最近的情绪记录：\n" + "\n".join(emo_lines) + "\n\n"
        else:
            prompt += "还没有用户的情绪记录。\n\n"

        prompt += (
            "要求：\n"
            "1. 说一句亲切的开场问候，像朋友主动找你聊天\n"
            "2. 如果记忆里有用户的重要信息（如名字、近况），自然地提及\n"
            "3. 如果最近情绪偏负面，表达恰到好处的关心，但不要沉重\n"
            "4. 如果什么都不了解，就轻松地问一句'今天想聊点什么'\n"
            "5. 只输出这句话本身，不要任何解释，不超过 60 字\n"
        )

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            # 失败时给一句默认问候
            return "嗨，我在呢～今天想聊点什么吗？"

    # ============ 后台副任务 ============
    def _handle_post_tasks(self, user_text, reply):
        """
        后台线程执行的副任务：提取记忆、识别情绪、可能摘要。
        这些任务不阻塞主回复，出错也不影响用户。
        """
        # 提取记忆
        try:
            extracted = self.memory_service.extract_memories(user_text, reply)
            if extracted:
                self.memory_service.save_memories(extracted)
        except Exception:
            pass

        # 识别情绪并记录
        try:
            emotion = self.emotion_service.detect_emotion(user_text)
            db.save_emotion("default", emotion, user_text)
        except Exception:
            pass

        # 检查是否需要增量摘要
        try:
            maybe_summarize(self.conversation_id, self.summary_service)
        except Exception:
            pass

    # ============ 主流程（流式生成器） ============
    def stream_message(self, user_text):
        """
        流式处理一次对话，逐块 yield 回复文本。
        用法：for chunk in service.stream_message("你好"):
                  print(chunk, end="")
        """
        # 0. 会话第一条消息，自动生成标题
        if db.count_messages(self.conversation_id) == 0:
            try:
                title = generate_title(self.client, user_text)
                db.update_conversation_title(self.conversation_id, title)
            except Exception:
                pass

        # 1. 保存用户消息
        db.save_message(self.conversation_id, "user", user_text)

        # 2. 取记忆 + 摘要 + 历史
        memories = db.get_memories()
        summary = db.get_latest_summary(self.conversation_id)
        history = db.get_recent_messages(self.conversation_id, limit=10)

        # 3. 拼 system prompt
        system_prompt = build_system_prompt(memories, summary)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # 4. 第一次调用：判断是否需要调用工具（非流式，模型"举手"）
        first = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.8,
            tools=tools.TOOLS,  # 把工具说明书递给模型
        )
        first_msg = first.choices[0].message

        # 5. 如果模型举手要调工具，执行工具并拿到结果
        if first_msg.tool_calls:
            tool_call = first_msg.tool_calls[0]
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments or "{}")

            # 真正执行工具（这一步是"代码"在跑，不是模型）
            tool_result = tools.run_tool(func_name, func_args)

            # 把"举手 + 工具结果"追加进消息，供第二次调用作答
            messages.append(first_msg)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

        # 6. 第二次调用：流式生成最终回复
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.8,
            stream=True,  # 关键：开启流式
        )

        # 5. 逐块收集回复
        full_reply = ""
        for chunk in response:
            # 每个 chunk 里可能有 delta（增量文本）
            delta = chunk.choices[0].delta.content
            if delta:
                full_reply += delta
                yield delta  # 逐块返回给调用方

        # 6. 风险检测（如果是极端风险，追加安全引导）
        try:
            if self.safety_service.is_high_risk(user_text):
                guidance = SAFETY_GUIDANCE
                full_reply += guidance
                yield guidance
        except Exception:
            pass

        # 7. 保存完整回复
        db.save_message(self.conversation_id, "assistant", full_reply)

        # 8. 更新会话时间
        db.touch_conversation(self.conversation_id)

        # 9. 后台异步处理副任务（不阻塞）
        threading.Thread(
            target=self._handle_post_tasks,
            args=(user_text, full_reply),
            daemon=True,  # 守护线程，主程序退出时自动结束
        ).start()

    def send_message(self, user_text):
        """兼容旧接口：一次性返回完整回复（内部也走流式，然后拼接）"""
        full = ""
        for chunk in self.stream_message(user_text):
            full += chunk
        return full
