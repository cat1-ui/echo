# -*- coding: utf-8 -*-
"""
Function Calling 演示：让大模型学会"算数时调工具，而不是瞎编"
================================================================
这是 Echo 从"聊天机器人"迈向"agent"的第一步。

核心机制（面试必讲）：
    大模型本身不会"做事"，它只会生成文字（JSON 也是文字）。
    当你给它一份"工具说明书"后，遇到该用工具的事（比如算数），
    它不会直接编答案，而是"举手"——返回一段 JSON，说：
        "我想调用 calculate 这个函数，参数是 '12345*67890'"。
    然后【你的代码】去真正执行 calculate，把结果喂回给模型，
    模型再基于真实结果，组织成一句自然的话回答你。

一句话总结：模型是"大脑"（判断+说话），工具函数是"手"（你的代码）。
"""

import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)


# ============ 零件 1：工具函数（真正干活的"手"）============
def calculate(expr: str) -> str:
    """计算一个数学表达式，返回结果字符串。"""
    result = eval(expr)  # eval 把字符串当成 Python 表达式来计算
    return str(result)


# ============ 零件 2：工具说明书（把函数"介绍"给模型）============
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算一个数学表达式。当用户问需要算数的内容（如加减乘除）时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expr": {
                        "type": "string",
                        "description": "要计算的数学表达式，例如 '12345*67890'",
                    }
                },
                "required": ["expr"],
            },
        },
    }
]


# ============ 零件 3 & 4：一次完整的对话 ============
def chat(user_text):
    """一次对话。如果模型判断要用工具，就走"两次调用"流程。"""

    # 第一次调用：模型判断 + 举手
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": user_text}],
        tools=TOOLS,  # 关键：把说明书递给模型
    )
    msg = response.choices[0].message

    # 模型举手了吗？（tool_calls 不为空 = 它想调工具）
    if msg.tool_calls:
        tool_call = msg.tool_calls[0]
        func_name = tool_call.function.name           # 想调哪个函数
        func_args = json.loads(tool_call.function.arguments)  # 传什么参数

        # 真正执行工具（这一步是"你的代码"在跑，不是模型）
        result = ""
        if func_name == "calculate":
            result = calculate(func_args["expr"])
            print(f"    [工具被调用] calculate({func_args['expr']}) = {result}")

        # 第二次调用：把结果喂回去，让模型作答
        response2 = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": user_text},
                msg,  # 模型的"举手"
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                },  # 工具结果
            ],
        )
        return response2.choices[0].message.content
    else:
        # 没举手 = 不需要工具，直接返回模型的回答
        return msg.content


if __name__ == "__main__":
    print("问：帮我算 12345 乘以 67890")
    print("Echo：", chat("帮我算 12345 乘以 67890"))
    print("-" * 50)
    print("问：你好呀，今天心情怎么样")
    print("Echo：", chat("你好呀，今天心情怎么样"))
