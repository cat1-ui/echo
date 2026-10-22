# -*- coding: utf-8 -*-
"""
Echo 情感陪伴智能体 - 网页界面（Streamlit）
=================================================
把 Echo 做成"像产品"的陪伴界面：
    - 主视觉：沉浸式聊天，默认不暴露任何管理功能
    - 人设：固定的 Echo 头像 + 一句自我介绍
    - 对话细节：气泡时间戳、正在输入、有温度的引导语
    - 情绪洞察：Echo 在对话里主动递出的卡片
    - 管理视图：点左上角「⚙」才展开（会话/记忆/情绪/清空）

运行方式：
    streamlit run app.py
"""

import streamlit as st

from src import db
from src.chat_service import ChatService
from src.categories import CATEGORIES, get_icon
from src.analytics_service import AnalyticsService, build_trend_chart, build_distribution_chart

# ============ 页面配置 ============
st.set_page_config(page_title="Echo 情感陪伴助手", page_icon="🤖", layout="centered")

# ============ 自定义暖色主题 ============
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #FFF7F0 0%, #FFFFFF 40%);
    }
    /* 顶部栏：人设 + 齿轮按钮 */
    .echo-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 2px;
    }
    .echo-avatar {
        font-size: 34px;
        line-height: 1;
    }
    .echo-name {
        font-size: 21px;
        font-weight: 700;
        color: #E8683B;
        letter-spacing: 0.5px;
    }
    .echo-sub {
        color: #B0846A;
        font-size: 13px;
        margin-top: 1px;
    }
    /* 情绪洞察卡片 */
    .insight-card {
        background: #FFFFFF;
        border: 1px solid #F3D9C8;
        border-radius: 16px;
        padding: 18px 20px;
        margin: 8px 0 4px 0;
        box-shadow: 0 2px 12px rgba(232, 104, 59, 0.06);
    }
    .insight-title {
        font-size: 15px;
        font-weight: 700;
        color: #E8683B;
        margin-bottom: 6px;
    }
    .insight-text {
        font-size: 14px;
        color: #6B5344;
        line-height: 1.7;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============ 初始化 ChatService（用缓存，避免重复创建） ============
@st.cache_resource
def get_service():
    return ChatService()


service = get_service()

# ============ 初始化状态 ============
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_conversation" not in st.session_state:
    st.session_state.current_conversation = service.conversation_id
if "insight_delivered" not in st.session_state:
    st.session_state.insight_delivered = False
if "show_admin" not in st.session_state:
    st.session_state.show_admin = False


# ============ 顶部栏：人设 + 不起眼的齿轮开关 ============
col_header, col_gear = st.columns([20, 1])
with col_header:
    st.markdown(
        """
        <div class="echo-header">
            <span class="echo-avatar">🤖</span>
            <div>
                <div class="echo-name">Echo</div>
                <div class="echo-sub">我是 Echo，会记得你说过的小事。</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_gear:
    # 齿轮按钮：切换管理视图。用文字而非图标，保证不抢眼但可点击。
    if st.button("⚙", key="toggle_admin", help="设置"):
        st.session_state.show_admin = not st.session_state.show_admin
        st.rerun()


# ============ 管理视图（点齿轮后展开） ============
if st.session_state.show_admin:
    with st.container(border=True):
        st.markdown("**设置**")

        # ---- 会话 ----
        st.markdown("**📁 会话**")
        if st.button("➕ 新的对话"):
            new_id = service.new_conversation()
            st.session_state.messages = []
            st.session_state.current_conversation = new_id
            st.session_state.pop("greeted", None)
            st.session_state.pop("insight_delivered", None)
            st.rerun()

        conversations = db.list_conversations()
        current_id = st.session_state.current_conversation

        for conv in conversations:
            c1, c2 = st.columns([5, 1])
            with c1:
                label = conv["title"] or "新的对话"
                if conv["id"] == current_id:
                    label = f"● {label}"
                if st.button(label, key=f"conv_{conv['id']}", width="stretch"):
                    service.switch_conversation(conv["id"])
                    st.session_state.current_conversation = conv["id"]
                    history = db.get_recent_messages(conv["id"], limit=50)
                    st.session_state.messages = [
                        {"role": m["role"], "content": m["content"]} for m in history
                    ]
                    st.rerun()
            with c2:
                if st.button("🗑", key=f"delconv_{conv['id']}"):
                    db.delete_conversation(conv["id"])
                    if conv["id"] == current_id:
                        remaining = db.list_conversations()
                        if remaining:
                            service.switch_conversation(remaining[0]["id"])
                            st.session_state.current_conversation = remaining[0]["id"]
                        else:
                            service.switch_conversation(service.new_conversation())
                            st.session_state.current_conversation = service.conversation_id
                        st.session_state.messages = []
                    st.rerun()

        st.divider()

        # ---- 关于你（记忆） ----
        st.markdown("**🧠 关于你**")
        memories = db.get_memories()
        if not memories:
            st.caption("等我们多聊几句，我会在这里慢慢记住你。")

        grouped = {}
        for m in memories:
            cat = m["category"] if m["category"] in CATEGORIES else "其他"
            grouped.setdefault(cat, []).append(m)

        for cat in CATEGORIES:
            if cat not in grouped:
                continue
            icon = get_icon(cat)
            st.markdown(f"**{icon} {cat}**")
            for m in grouped[cat]:
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(f"- {m['value']}")
                with c2:
                    if st.button("🗑", key=f"del_{m['id']}"):
                        db.delete_memory(m['id'])
                        st.rerun()

        st.divider()

        # ---- 最近情绪 ----
        st.markdown("**💗 最近心情**")
        from src.emotion_service import get_emotion_icon

        emotions = db.get_recent_emotions(limit=10)
        if not emotions:
            st.caption("等你和我说说今天，我会留意你的心情。")
        for e in emotions:
            icon = get_emotion_icon(e["emotion"])
            st.markdown(f"{icon} {e['emotion']} · {e['content'][:15]}")

        st.divider()

        if st.button("🧠 清空全部记忆"):
            db.delete_all_memories()
            service.conversation_id = db.create_conversation()
            st.session_state.current_conversation = service.conversation_id
            st.session_state.messages = []
            st.session_state.pop("greeted", None)
            st.session_state.pop("insight_delivered", None)
            st.rerun()


# ============ 主界面：沉浸式聊天 ============
# 开场主动问候
if not st.session_state.messages and "greeted" not in st.session_state:
    greeting = service.generate_greeting()
    st.session_state.messages.append({"role": "assistant", "content": greeting})
    st.session_state.greeted = True


def _render_insight_card(all_emotions):
    """在对话流里渲染情绪洞察卡片（趋势图 + 饼图 + 一句人话总结）。"""
    trend_buf = build_trend_chart(all_emotions)
    dist_buf = build_distribution_chart(all_emotions)

    if "analytics" not in st.session_state:
        st.session_state.analytics = AnalyticsService(service.client)
    insight_text = st.session_state.analytics.generate_insight(all_emotions)

    st.markdown('<div class="insight-card">', unsafe_allow_html=True)
    st.markdown('<div class="insight-title">💗 你最近的心情</div>', unsafe_allow_html=True)

    if insight_text:
        st.markdown(f'<div class="insight-text">{insight_text}</div>', unsafe_allow_html=True)

    if trend_buf and dist_buf:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.image(trend_buf, width="stretch")
        with c2:
            st.image(dist_buf, width="stretch")

    st.markdown("</div>", unsafe_allow_html=True)


# 停顿词：用户说出这些，代表这一轮对话告一段落，适合递心情卡片
_END_SIGNALS = ["晚安", "睡了", "先这样", "去睡了", "拜拜", "再见", "不聊了", "先忙", "先下了", "下次聊"]


def _is_conversation_ending(text):
    """判断用户这句话是否在结束对话。"""
    return any(sig in text for sig in _END_SIGNALS)


# 显示历史消息（普通消息用气泡，卡片消息用卡片）
for msg in st.session_state.messages:
    if msg.get("type") == "insight_card":
        with st.chat_message("assistant", avatar="🤖"):
            _render_insight_card(db.get_all_emotions())
    else:
        avatar = "🤖" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])

# 输入框
if prompt := st.chat_input("今天有什么想和我聊聊的吗？"):
    # 1. 用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.write(prompt)

    # 2. Echo 回复（带"正在输入"过渡）
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Echo 正在输入…"):
            try:
                reply = st.write_stream(service.stream_message(prompt))
            except Exception as e:
                reply = f"网络错误，请重试。（{e}）"
                st.write(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})

    # 3. 对话停顿点（用户说晚安/先这样等），且情绪够 5 条，Echo 才递心情卡片
    all_emotions = db.get_all_emotions()
    if (
        len(all_emotions) >= 5
        and not st.session_state.insight_delivered
        and _is_conversation_ending(prompt)
    ):
        with st.chat_message("assistant", avatar="🤖"):
            _render_insight_card(all_emotions)
        st.session_state.insight_delivered = True
        st.session_state.messages.append({"role": "assistant", "type": "insight_card", "content": ""})
