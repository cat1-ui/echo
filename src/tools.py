# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 工具层（Function Calling）
=================================================
让 Echo 从"只会说话"变成"会做事"。

核心认知（面试必讲）：
    大模型本身不会"做事"，它只会生成文字（JSON 也是文字）。
    我们在这里：
      1. 定义"工具函数"——真正干活的 Python 代码（手）
      2. 定义"工具说明书"——把工具介绍给模型（说明书）
    模型读说明书后，遇到该用工具的事，会"举手"返回 JSON，
    再由 chat_service 去执行对应的工具函数，把结果喂回模型。

当前工具：
    calculate   —— 安全地计算一个数学表达式（白名单，拒绝任意代码）
    get_time    —— 获取当前日期和时间
    get_weather —— 查询任意城市的实时天气（和风天气 API，联网）
"""

import re
import os
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# ============ 工具函数（真正干活的"手"）============

# 白名单：一个合法算式，只允许出现这些字符
_SAFE_PATTERN = re.compile(r"^[\d\s+\-*/().]+$")


def calculate(expr: str) -> str:
    """
    安全地计算一个数学表达式，返回结果字符串。

    安全措施（白名单）：
        先用正则检查 expr 是否【只包含】数字、空格、小数点
        和 + - * / ( ) 这些字符。只要混入任何其他字符
        （字母、下划线、引号等），就说明不是纯算式，直接拒绝，
        避免 eval 执行任意代码（代码注入）。
    """
    expr = (expr or "").strip()
    if not expr:
        return "表达式为空"

    # 白名单校验：不合法就直接拒绝，绝不交给 eval
    if not _SAFE_PATTERN.match(expr):
        return "表达式包含非法字符，已拒绝执行"

    try:
        result = eval(expr)
        # 限制结果长度，避免超大数刷屏
        return str(result)
    except Exception:
        return "表达式无法计算"


def get_time() -> str:
    """
    获取当前日期和时间，返回中文格式的字符串。
    纯本地工具，零依赖、零成本，模型不知道时间时靠它兜底。
    """
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    return f"{now.year}年{now.month}月{now.day}日 {weekday} {now.hour:02d}:{now.minute:02d}"


# ============ 天气工具（联网，和风天气 API）============

QWEATHER_KEY = os.getenv("QWEATHER_KEY", "")
# 和风天气专属 API Host（控制台「设置」里可查），不同账号域名不同
# 从 .env 读取，避免把个人账号专属域名硬编码进代码（会随代码公开）
QWEATHER_HOST = os.getenv("QWEATHER_HOST", "")
GEO_URL = f"https://{QWEATHER_HOST}/geo/v2/city/lookup"
WEATHER_URL = f"https://{QWEATHER_HOST}/v7/weather/now"


def get_weather(city: str) -> str:
    """
    查询一个城市的实时天气，返回一句可读的描述。

    内部链路（两步串起来）：
        1. GeoAPI 城市搜索：把中文/英文城市名 → Location ID
        2. 天气预报 API：用 Location ID 查实时天气
    支持全国乃至全球城市（GeoAPI 是全球库）。
    """
    if not QWEATHER_KEY:
        return "未配置和风天气 API Key，无法查询天气"

    # 第一步：城市名 → Location ID
    try:
        resp = requests.get(
            GEO_URL,
            params={"location": city, "key": QWEATHER_KEY, "number": 1},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != "200" or not data.get("location"):
            return f"没有找到城市「{city}」"
        loc = data["location"][0]
        location_id = loc["id"]
        loc_name = f"{loc.get('adm1', '')} {loc.get('name', '')}".strip()
    except Exception:
        return "城市查询失败，请稍后再试"

    # 第二步：Location ID → 实时天气
    try:
        resp = requests.get(
            WEATHER_URL,
            params={"location": location_id, "key": QWEATHER_KEY},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != "200":
            return f"「{loc_name}」天气查询失败"
        now = data["now"]
        return (
            f"{loc_name}当前天气：{now['text']}，"
            f"气温 {now['temp']}℃，体感 {now['feelsLike']}℃，"
            f"湿度 {now['humidity']}%，{now['windDir']}{now['windScale']}级"
        )
    except Exception:
        return "天气查询失败，请稍后再试"


# ============ 工具说明书（把工具"介绍"给模型）============

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
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取当前的日期和时间。当用户询问现在几点了、今天几号、今天星期几时使用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气。当用户询问某地天气、气温、下不下雨时使用。支持全国及全球主要城市。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，可以是中文或英文，例如 '广州'、'东京'、'New York'",
                    }
                },
                "required": ["city"],
            },
        },
    },
]


# ============ 执行工具（根据模型"举手"的函数名，调用对应函数）============

def run_tool(func_name: str, func_args: dict) -> str:
    """
    根据模型要调用的函数名，执行对应的工具函数，返回结果字符串。
    这是"你的代码真正干活"的地方。
    """
    if func_name == "calculate":
        return calculate(func_args.get("expr", ""))
    if func_name == "get_time":
        return get_time()
    if func_name == "get_weather":
        return get_weather(func_args.get("city", ""))
    # 未知工具名，兜底
    return f"未知工具：{func_name}"
