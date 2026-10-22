# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 数据库层（SQLite）
=================================================
用 Python 内置的 sqlite3 管理四张表：
    conversations  会话表
    messages       消息表
    memories       记忆表（长期记忆）
    summaries      摘要表

SQLite 不需要装服务器，就是一个 .db 文件，比 MySQL 简单很多。
"""

import sqlite3
import os
from datetime import datetime

# 数据库文件路径：data/chat.db
DB_PATH = os.path.join("data", "chat.db")


def get_conn():
    """获取数据库连接（自动创建 data 目录和数据库文件）"""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 让查询结果可以用列名访问
    return conn


def init_db():
    """建表（如果表不存在）"""
    conn = get_conn()
    cursor = conn.cursor()

    # 会话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            title TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # 消息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)

    # 记忆表（长期记忆）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            key TEXT,
            value TEXT,
            category TEXT,
            confidence REAL,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # 摘要表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            summary TEXT,
            created_at TEXT
        )
    """)

    # 兼容旧表：如果 summaries 表没有 last_message_id 列，则补上
    try:
        cursor.execute("ALTER TABLE summaries ADD COLUMN last_message_id INTEGER")
    except sqlite3.OperationalError:
        pass  # 列已存在，忽略

    # 情绪表（情绪记录）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            emotion TEXT,
            content TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def create_conversation(user_id="default"):
    """强制新建一个会话（不管有没有旧会话）"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, "新的对话", now, now),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_or_create_conversation(user_id="default"):
    """获取当前会话 id，没有就新建一个"""
    conn = get_conn()
    cursor = conn.cursor()

    # 找最新的一个会话
    cursor.execute(
        "SELECT id FROM conversations WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    row = cursor.fetchone()
    if row:
        return row["id"]

    # 没有就新建
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, "新的对话", now, now),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def list_conversations(user_id="default"):
    """列出该用户所有会话，按更新时间倒序返回"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, created_at, updated_at FROM conversations "
        "WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation(conversation_id):
    """获取单个会话信息，不存在返回 None"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title FROM conversations WHERE id=?", (conversation_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_conversation_title(conversation_id, title):
    """更新会话标题"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
        (title, now, conversation_id),
    )
    conn.commit()
    conn.close()


def touch_conversation(conversation_id):
    """更新会话的 updated_at（有消息时调用，让列表排序最新在前）"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE conversations SET updated_at=? WHERE id=?",
        (now, conversation_id),
    )
    conn.commit()
    conn.close()


def delete_conversation(conversation_id):
    """删除会话及其所有消息、摘要（记忆是全局的，不删）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    cursor.execute("DELETE FROM summaries WHERE conversation_id=?", (conversation_id,))
    cursor.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    conn.commit()
    conn.close()


def save_message(conversation_id, role, content):
    """保存一条消息（role: user 或 assistant）"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conversation_id, role, content, now),
    )
    conn.commit()
    conn.close()


def count_messages(conversation_id):
    """统计某会话的消息总数"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS c FROM messages WHERE conversation_id=?",
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["c"]


def get_messages_range(conversation_id, start_id, end_id):
    """
    取某会话中 id 在 (start_id, end_id] 区间的消息，正序返回。
    用于增量摘要：只取"上次摘要之后新产生的"消息。
    """
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM messages "
        "WHERE conversation_id=? AND id>? AND id<=? ORDER BY id",
        (conversation_id, start_id, end_id),
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def get_recent_messages(conversation_id, limit=10):
    """取最近 N 条消息，按时间正序返回（最旧的在前）"""
    conn = get_conn()
    cursor = conn.cursor()
    # 先倒序取 limit 条，再反过来，保证顺序是"旧→新"
    cursor.execute(
        "SELECT role, content FROM messages "
        "WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    # rows 是 [新, ..., 旧]，反转为 [旧, ..., 新]
    rows = list(rows)[::-1]
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ============ 记忆表相关操作 ============

def save_memory(user_id, key, value, category, confidence):
    """保存一条记忆；如果同 key 已存在，则更新（覆盖）"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 查是否已有相同的 key
    cursor.execute(
        "SELECT id FROM memories WHERE user_id=? AND key=?",
        (user_id, key),
    )
    row = cursor.fetchone()

    if row:
        # 已存在，更新 value
        cursor.execute(
            "UPDATE memories SET value=?, category=?, confidence=?, updated_at=? WHERE id=?",
            (value, category, confidence, now, row["id"]),
        )
    else:
        # 不存在，新增
        cursor.execute(
            "INSERT INTO memories (user_id, key, value, category, confidence, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, key, value, category, confidence, now, now),
        )

    conn.commit()
    conn.close()


def get_memories(user_id="default"):
    """读取该用户所有记忆，返回列表"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, key, value, category, confidence FROM memories WHERE user_id=? ORDER BY id",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_memory(memory_id):
    """删除一条记忆"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    conn.commit()
    conn.close()


def delete_all_memories(user_id="default"):
    """删除该用户的所有记忆（Echo 彻底失忆）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memories WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


# ============ 情绪表相关操作 ============

def save_emotion(user_id, emotion, content):
    """保存一条情绪记录"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO emotions (user_id, emotion, content, created_at) VALUES (?, ?, ?, ?)",
        (user_id, emotion, content, now),
    )
    conn.commit()
    conn.close()


def get_recent_emotions(user_id="default", limit=10):
    """获取最近 N 条情绪记录，最新的在前"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT emotion, content, created_at FROM emotions "
        "WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_emotions(user_id="default"):
    """获取该用户所有情绪记录，按时间正序（最旧在前）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT emotion, content, created_at FROM emotions "
        "WHERE user_id=? ORDER BY id ASC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 摘要表相关操作 ============

def save_summary(conversation_id, summary):
    """保存一条对话摘要"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO summaries (conversation_id, summary, created_at) VALUES (?, ?, ?)",
        (conversation_id, summary, now),
    )
    conn.commit()
    conn.close()


def save_summary_with_pos(conversation_id, summary, last_message_id):
    """保存一条摘要，并记录它覆盖到哪条消息（last_message_id）"""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO summaries (conversation_id, summary, created_at, last_message_id) "
        "VALUES (?, ?, ?, ?)",
        (conversation_id, summary, now, last_message_id),
    )
    conn.commit()
    conn.close()


def get_latest_summary(conversation_id):
    """获取该会话最新一条摘要，没有则返回 None"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT summary FROM summaries WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["summary"] if row else None


def get_latest_summary_info(conversation_id):
    """获取该会话最新一条摘要的完整信息（含 last_message_id），没有则返回 None"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT summary, last_message_id FROM summaries "
        "WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {"summary": row["summary"], "last_message_id": row["last_message_id"]}
