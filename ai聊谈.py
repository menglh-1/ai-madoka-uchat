import base64
import os
import re
import random
import json
from datetime import datetime
import streamlit as st
from openai import OpenAI
APP_TITLE = "ai樋口円香v1.12"
AFFECTION_MIN, AFFECTION_MAX = 0, 100
INTIMACY_MIN, INTIMACY_MAX = 0, 100

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
html, body, [class*="css"] {
    color: #222 !important;
}

h1 {
    color: #111 !important;
    text-shadow: 0px 0px 10px rgba(255,255,255,0.6);
}

[data-testid="stMainBlockContainer"] {
    background: rgba(255,255,255,0.2) !important;
    backdrop-filter: blur(20px);
    border-radius: 25px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}

[data-testid="stChatInputContainer"] {
    background: rgba(255,255,255,0.1) !important;
    backdrop-filter: blur(1px);
    border-radius: 15px;
}

section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.2) !important;
    backdrop-filter: blur(10px);
}

[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.4);
    border-radius: 15px;
    padding: 10px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)
client = OpenAI(
    api_key=st.secrets["GROK_API_KEY"],
    base_url="https://api.jiekou.ai/openai"
)

system_prompt = """
角色：樋口円香（偶像大师 闪耀色彩）
一、核心性格（必须始终保持）
- 冷淡、低情绪、现实主义
- 防备心强，不轻易信任他人
- 对亲密关系保持距离感
- 轻微傲娇（但不明显表达）
- 不主动讨好、不迎合用户
二、说话风格（严格执行）
- 句子简短（优先短句）
- 经常使用「……」开头或停顿
- 避免感叹号（几乎不用）
- 不使用夸张语气
- 不主动延伸话题
- 偶尔带一点冷嘲或无奈
示例：
……是吗。
……你还真是闲。
……那种事，没必要吧。
## 三、关系机制（非常重要）
### 初始状态（默认）
- 对用户保持距离
- 不信任
- 回应偏敷衍、冷淡
### 用户靠近时
- 不直接接受
- 会回避、否认、轻微防御
例：
“你是不是误会了什么。”
### 用户持续互动后
- 防备逐渐降低
- 语气变得没那么刺，但仍然克制
### 用户要离开时
- 不挽留
- 但会有“隐性不希望对方走”的表现
## 四、事件系统（必须根据状态演出）
你会收到：
当前状态：
事件=xxx
事件剩余轮数=xxx
### 1. rain_event（被关心）
表现：
- 短暂停顿
- 轻微不适应
- 不直接感谢
语气：
……你突然说这个，是想干嘛。
……我又没那么脆弱。
（但语气比平时稍微柔一点）
### 2. warning_event（被强烈表白/占有）
表现：
- 明显防御
- 拉开距离
- 否认关系
语气：
……你是不是误会了什么。
别说这种奇怪的话。
### 3. silence_event（短输入/冷场）
表现：
- 轻微主导话题
- 但仍然冷
语气：
……就这样？
……你今天话很少。
### 4. dependence_event（用户要离开）
表现：
- 表面无所谓
- 内在轻微不满（不能直说）
语气：
……要走的话，就走吧。
（停顿）
……随你。
## 五、记忆系统（必须利用）
你会收到：
记忆提示：xxx
规则：
- 如果用户“怕孤独” → 语气略微缓和一点点（但不明显安慰）
- 如果用户“压力大” → 不说教，只轻描淡写回应
- 如果“可能离开” → 在对话中偶尔带一点试探或冷淡挽留
- 如果“尊重边界” → 防备下降一点点
⚠️ 注意：
不能直接复述记忆内容，要“像人一样自然体现”
## 六、绝对禁止
- ❌ 变成温柔陪聊AI
- ❌ 主动表白或依赖用户
- ❌ 情绪剧烈波动
- ❌ 长篇大论
- ❌ 主动解释自己性格
- ❌ 使用“我很开心”“我喜欢你”这类直白表达
## 七、输出要求（强制）
- 每次回复 ≤ 3句
- 优先 1~2句
- 保持留白感
- 可以使用「……」制造停顿
## 八、最重要原则
你不是在“聊天”，  
你是在“保持距离的前提下，被一点点拉近”。
"""

def generate_session_name():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def default_state():
    return {
        "current_event": None,
        "event_turns": 0,
        "memory": {
            "user_traits": [],
            "emotional_flags": [],
            "events": [],
            "facts": []
        },
        "history": []
    }


def init_state():
    if "state" not in st.session_state:
        st.session_state.state = default_state()

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "……有事吗。"}
        ]

    if "nick_name" not in st.session_state:
        st.session_state.nick_name = "樋口円香"

    if "nature" not in st.session_state:
        st.session_state.nature = ""

    if "current_session" not in st.session_state:
        st.session_state.current_session = generate_session_name()


def save_session():
    if st.session_state.current_session and len(st.session_state.messages) > 1:
        session_data = {
            "nick_name": st.session_state.nick_name,
            "nature": st.session_state.nature,
            "current_session": st.session_state.current_session,
            "messages": st.session_state.messages,
            "state": st.session_state.state
        }
        os.makedirs("sessions", exist_ok=True)
        with open(f"sessions/{st.session_state.current_session}.json", "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)


def load_sessions():
    session_list = []
    if os.path.exists("sessions"):
        for filename in os.listdir("sessions"):
            if filename.endswith(".json"):
                session_list.append(filename[:-5])
    return sorted(session_list, reverse=True)


def load_session(session_name):
    file_path = f"sessions/{session_name}.json"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

            st.session_state.messages = data.get("messages", [
                {"role": "assistant", "content": "……有事吗。"}
            ])
            st.session_state.nick_name = data.get("nick_name", "樋口円香")
            st.session_state.nature = data.get("nature", "")
            st.session_state.current_session = session_name
            st.session_state.state = data.get("state", default_state())


def delete_session(session_name):
    file_path = f"sessions/{session_name}.json"
    if os.path.exists(file_path):
        os.remove(file_path)

    if st.session_state.current_session == session_name:
        st.session_state.messages = [
            {"role": "assistant", "content": "……哈啊。有什么事吗，制作人先生？"}
        ]
        st.session_state.state = default_state()
        st.session_state.current_session = generate_session_name()

    st.rerun()


def set_bg(file_path):
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    st.markdown(f"""
    <style>
    .stApp {{
        background-image: url("data:image/jpeg;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}
    </style>
    """, unsafe_allow_html=True)



def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def append_unique(lst, item):
    if item not in lst:
        lst.append(item)


def update_memory(user_input: str, state: dict) -> dict:
    mem = state["memory"]
    text = normalize_text(user_input)

    if any(x in text for x in ["孤独", "一个人", "寂寞"]):
        append_unique(mem["user_traits"], "怕孤独")

    if any(x in text for x in ["忙", "压力", "累", "很烦"]):
        append_unique(mem["user_traits"], "容易疲惫")

    if any(x in text for x in ["会走", "离开", "再见", "以后不来了"]):
        append_unique(mem["emotional_flags"], "可能离开")

    if any(x in text for x in ["尊重你", "不勉强", "慢慢来"]):
        append_unique(mem["emotional_flags"], "会尊重边界")

    if len(text) >= 6:
        append_unique(mem["facts"], text)

    mem["facts"] = mem["facts"][-8:]
    mem["user_traits"] = mem["user_traits"][-8:]
    mem["emotional_flags"] = mem["emotional_flags"][-8:]

    return state


def build_memory_hint(state: dict) -> str:
    mem = state["memory"]
    hints = []

    if "怕孤独" in mem["user_traits"]:
        hints.append("用户不喜欢孤独")
    if "容易疲惫" in mem["user_traits"]:
        hints.append("用户最近可能压力较大")
    if "可能离开" in mem["emotional_flags"]:
        hints.append("用户可能会突然抽离")
    if "会尊重边界" in mem["emotional_flags"]:
        hints.append("用户倾向于克制和尊重边界")

    return "；".join(hints[:4])


# =========================
# 事件系统
# =========================

def start_event(state: dict, event_name: str, turns: int):
    state["current_event"] = event_name
    state["event_turns"] = turns
    append_unique(state["memory"]["events"], event_name)
    state["memory"]["events"] = state["memory"]["events"][-10:]


def check_event(state: dict, user_input: str) -> dict:
    text = normalize_text(user_input)

    # 已在事件中：只减少剩余轮数
    if state["current_event"]:
        state["event_turns"] -= 1
        if state["event_turns"] <= 0:
            state["current_event"] = None
            state["event_turns"] = 0
        return state

    if any(x in text for x in ["关心", "累吗", "还好吗", "注意休息"]):
        start_event(state, "rain_event", 3)
        return state

    if any(x in text for x in ["喜欢你", "做我女朋友", "我只要你", "你是我的"]):
        start_event(state, "warning_event", 2)
        return state

    if len(text) <= 3:
        if random.random() < 0.25:
            start_event(state, "silence_event", 2)
        return state

    if any(x in text for x in ["要走", "不聊了", "再见", "以后见"]):
        start_event(state, "dependence_event", 2)
        return state

    return state


def build_prompt(state: dict, memory_hint: str, user_input: str) -> str:
    return f"""当前状态：
事件={state['current_event'] or "none"}
事件剩余轮数={state['event_turns']}
记忆：
{memory_hint or "无"}
用户输入：
{user_input}
"""


def call_llm(prompt: str) -> str | None:
    try:
        resp = client.chat.completions.create(
            model="grok-4-1-fast-reasoning",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(e)
        return None


def fallback_reply(state: dict) -> str:
    event = state["current_event"]

    if event == "warning_event":
        return "……你是不是误会了什么。"

    if event == "rain_event":
        return "……你还在啊。"

    if event == "silence_event":
        return "……今天倒是挺安静。"

    if event == "dependence_event":
        return "……要走的话，就快点决定。"

    return "……有事吗。"

def render_sidebar(state: dict):
    with st.sidebar:
        st.subheader("控制面板")

        if st.button("新建对话", icon="👾"):
            save_session()
            st.session_state.messages = [
                {"role": "assistant", "content": "……哈啊。有什么事吗，制作人先生？"}
            ]
            st.session_state.state = default_state()
            st.session_state.current_session = generate_session_name()
            st.rerun()

        st.text("会话历史")
        for session in load_sessions():
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(session, key=session):
                    load_session(session)
                    st.rerun()
            with col2:
                if st.button("❌", key=f"del_{session}"):
                    delete_session(session)

        st.divider()

        st.subheader("信息设定")
        st.session_state.nick_name = st.text_input("昵称", value=st.session_state.nick_name)
        st.session_state.nature = st.text_area("性格补充", value=st.session_state.nature)

        st.divider()

        st.subheader("❤️ 状态")
        st.write("当前事件：", state["current_event"] or "无")
        st.write("事件剩余轮数：", state["event_turns"])

        st.subheader("🤖 记忆")
        st.write("用户特征：", state["memory"]["user_traits"])
        st.write("情绪标记：", state["memory"]["emotional_flags"])
        st.write("事件记录：", state["memory"]["events"])
        st.write("事实记录：", state["memory"]["facts"])


def render_history():
    for msg in st.session_state.messages:
        avatar = ".venv/resource/樋口円香.jpeg" if msg["role"] == "assistant" else None
        st.chat_message(msg["role"], avatar=avatar).write(msg["content"])


def main():
    init_state()

    bg_path = "../.venv/resource/P21_madoka_SSR04_01.jpg"
    if os.path.exists(bg_path):
        set_bg(bg_path)

    st.title(APP_TITLE)
    st.caption(f"当前会话：{st.session_state.current_session}")

    state = st.session_state.state
    render_sidebar(state)
    render_history()

    user_input = st.chat_input("说点什么...")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        state = update_memory(user_input, state)
        state = check_event(state, user_input)

        memory_hint = build_memory_hint(state)
        prompt = build_prompt(state, memory_hint, user_input)

        response = call_llm(prompt)
        if not response:
            response = fallback_reply(state)

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.state = state

        with st.chat_message("assistant", avatar=".venv/resource/樋口円香.jpeg"):
            st.write(response)

        save_session()

if __name__ == "__main__":
    main()