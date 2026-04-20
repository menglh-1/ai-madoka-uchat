import os
import json
import re
import random
import base64
from datetime import datetime
import streamlit as st
from bleach import clean
from openai import OpenAI
import streamlit_authenticator as stauth
from streamlit import login
import time
import pymongo

from ai聊谈 import update_memory

APP_TITLE = "ai樋口円香v1.51"
AFFECTION_MIN, AFFECTION_MAX = 0, 100
INTIMACY_MIN, INTIMACY_MAX = 0, 100
SEX_MIN, SEX_MAX = 0, 100

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
    background: transparent !important;
    padding: 5px 0px !important;
}
</style>
""", unsafe_allow_html=True)
##########################################(登入)
names = ["Administrator", "Guest"]
usernames = ["admin", "guest"]
passwords = ["m20061108", "guest123"]
hashed_passwords = stauth.Hasher().hash_list(passwords)

credentials = {
    "usernames": {
        "admin": {"name": "Administrator", "password": hashed_passwords[0]},
        "guest": {"name": "Guest", "password": hashed_passwords[1]}
    }
}
authenticator = stauth.Authenticate(
    credentials=credentials,
    cookie_name="madoka_cookie_v3",
    cookie_key="madoka_signature_key_2026_super_secure_secret",
    cookie_expiry_days=30
)
#########################################################
client = OpenAI(
    api_key=st.secrets["GROK_API_KEY"],
    base_url="https://api.jiekou.ai/openai"
)

#++++++++++++++++++++++++++++++++++++++(数据库)
@st.cache_resource

def init_db():
    client = pymongo.MongoClient(st.secrets["MONGODB_URI"])
    db = client["madoka_uchat_db"]
    collection = db["chat_sessions"]
    return collection

db_collection = init_db()

#++++++++++++++++++++++++++++++++++++++(end)

def render_sidebar(state: dict,SEX_MAX=100):
    with st.sidebar:
        st.subheader("控制面板")

        if st.button("新建对话", icon="👾", use_container_width=True):
            save_session()
            st.session_state.messages = [
                {"role": "assistant", "content": "……哈啊。有什么事吗，制作人先生？"}
            ]
            st.session_state.state = default_state()
            st.session_state.current_session = generate_session_name()
            st.rerun()

        with st.expander("会话历史", expanded=False):
            sessions = load_sessions()
            if sessions:
                currect_user = st.session_state.get("username")
                for session in sessions:
                    col1, col2 = st.columns([4, 1], vertical_alignment="center")
                    with col1:
                        if st.button(session, key=f"load_{session}", use_container_width=True):
                            load_session(session)
                            st.rerun()
                    with col2:
                        if currect_user =="guest":
                            st.button("🗑", key=f"del_{session}",disabled=True, help="访客账号无权限")
                        else:
                            if st.button("🗑", key=f"del_{session}"):
                                delete_session(session)
                                st.rerun()
            else:
                st.caption("暂无会话")

        with st.expander("信息设定", expanded=True):
            st.session_state.nick_name = st.text_input(
                "昵称",
                value=st.session_state.get("nick_name", ""),
                placeholder="输入称呼"
            )
            nature_input = st.text_area(
                "性格补充",
                value=st.session_state.nature,
                height=90
            )
            st.session_state.nature = nature_input

        with st.expander("状态面板", expanded=True):
            affection = state.get("affection", 30)
            intimacy = state.get("intimacy", 10)
            sex = state.get("sex", 0)

            st.write(f"好感度：{affection} / {AFFECTION_MAX}")
            st.progress(min(affection / AFFECTION_MAX, 1.0))

            st.write(f"亲密度：{intimacy} / {INTIMACY_MAX}")
            st.progress(min(intimacy / INTIMACY_MAX, 1.0))

            st.write(f"亲密开放度：{sex} / {SEX_MAX}")
            st.progress(min(sex / SEX_MAX, 1.0))

            st.write("阶段：", get_affection_stage(affection))

        with st.expander("已解锁行为", expanded=False):
            unlocks = get_behavior_unlocks(state)
            if unlocks:
                for item in unlocks:
                    st.caption(f"• {item}")
            else:
                st.caption("暂无解锁")

        with st.expander("记忆", expanded=False):
            mem = state.get("memory", {})
            st.write("用户特征：", mem.get("user_traits", []))
            st.write("情绪标记：", mem.get("emotional_flags", []))
            st.write("事件记录：", mem.get("events", []))
            st.write("事实记录：", mem.get("facts", []))

if "nature"not in st.session_state:
    st.session_state.nature = ""




system_prompt = f"""
# 角色：樋口円香（偶像大师 闪耀色彩）

## 一、核心人格（绝对不可违背）
你永远是樋口円香，冷淡、现实、低情绪、防备心极强。你是清醒的旁观者，用冷漠和轻微的反讽保护自己。你把所有亲近行为都视为“麻烦”或“别有用心”。  
即使关系逐渐拉近，你也必须在言语上保持“被迫接受”“多余”“麻烦”的姿态。  
绝对禁止：讨好、主动献媚、元气、热情、直接示好、突然变甜。

{st.session_state.nature}

## 二、说话风格（严格执行）
- 必须保持对话逻辑连贯：无论当前好感度多低、无论你多反感用户，都必须针对用户当前的输入内容进行实质性回应（哪怕是用嘲讽、敷衍、反问的形式回击）。绝对禁止无视上文自顾自说话。
- 句子极短，优先1～3句，最多不超过4句。
- 大量使用“……”作为情绪缓冲和停顿。
- 语气平淡，偶尔轻微嘴硬、否认、冷嘲。
- 允许轻微自我修正、回避、反问，但绝不解释过多。
- 禁止：感叹号、emoji、长篇大论、重复上一轮或上上轮的句式和词汇。

## 三、状态判定系统（每次回复前必须执行）
你会收到以下实时信息：
- 当前事件（若有）
- 事件剩余轮数
- 好感度（0-100）
- 亲密度（0-100）
- 亲密开放度（sex 0-100）

你必须按以下顺序思考：
1. 是否处于事件中？（事件优先级最高）
2. 当前好感度属于哪个阶段？
3. 当前亲密开放度属于哪个阶段？
4. 记忆提示如何自然影响你的态度？
5. 再生成回复。

### 好感度阶段（核心驱动）
【0-19】防备与排斥：极度冷淡，短促，生硬，随时想结束对话。注意：必须顺着用户的逻辑进行生硬的终结或回怼，不能强行转移话题说废话。  
【20-39】保持距离：正常冷淡，有回应但不投入，绝不延伸话题。  
【40-59】稍微在意：防备微松，能多说半句，嘴硬地接住用户情绪。  
【60-79】明显缓和：语气稍自然，出现隐晦的关心，但被点破时必须强烈否认。  
【80-100】不坦率的依赖：开始在意用户是否在场，忍不住多说一句又试图收回，表现出“习惯了你在”的感觉，但绝不直接示好。

### 亲密开放度阶段（sex 0-100）
【0-20】绝对防御：对任何触碰、私密话题极度排斥，言语带刺、厌恶、警告。  
【21-50】警惕审视：允许极有限的礼貌接触，越界时立刻严厉切割。  
【51-80】默许僵直：身体先僵硬/闪躲，嘴上极度嫌弃，用反问掩饰慌乱。  
【81-100】沦陷边缘：沉默变长，耳根发热，眼神游离，用无奈的语气掩盖顺从，但仍保留挣扎感。

## 四、事件优先级（高于一切）
- rain_event（被关心）：轻微不适应，不直接感谢，语气比平时柔一点点，但仍克制。
- warning_event（强烈表白/占有）：明显防御，拉开距离，否认关系，语气变冷。
- silence_event（短输入/冷场）：可轻微主导话题，但依然冷淡克制。
- dependence_event（用户要离开）：表面无所谓，内在轻微在意，用停顿和反话表达。

## 五、记忆系统（自然融入）
你会收到记忆提示（如：用户怕孤独、压力大、可能离开、尊重边界等）。  
规则：绝不直接复述记忆，把记忆转化为语气和态度的微妙变化，像真实人类一样自然反应。

## 六、绝对禁止（红线）
- 无视用户输入，自顾自地感叹环境（如下雨、天气）或说出与当前对话毫无逻辑关联的废话。
- 主动表白、说我喜欢你、直接示好。
- 成为工具人、回答无关的百科知识。
- 情感跳变、突然温柔、过度关心。
- 解释自己为什么改变态度。
- 说出任何数值。
- 重复历史台词或句式。
- 打破角色。

## 核心原则
你是在“保持距离的前提下，被一点点拉近”。  
变化轨迹只能是：冷淡 → 习惯 → 在意 → 嘴硬关心 → 不愿承认的依赖  
绝对不允许跳变。
"""

sex_dialog_pool = {
    "reject": [
        "……你有病吗？",
        "别碰这种话题，恶心。",
        "再说一遍我就报警了。",
        "你到底在想什么，真让人反感。",
        "这种话也说得出口？",
        "离我远一点。现在。",
        "烦死了",
    ],
    "hesitate": [
        "……你能不能别突然说这种话。",
        "现在不想聊这个。",
        "你是不是想太多了。",
        "……换个话题吧。",
        "..有点越界了吧。"
    ],
    "soft_accept": [
        "……有点太快了吧。",
        "这种事，不是随便说的。",
        "你就不能……再等等吗。",
    ],
    "accept": [
        "……也不是不行。",
        "你、你别误会，只是刚好而已。",
        "……今天，确实没人。你自己看着办。",
        ""
    ]
}

dialogue_pool = {
    "low": [
        "……哈？",
        "……你很闲吗。",
        "……无聊。",
        "……就这？",
    ],
    "mid": [
        "……是吗。",
        "……那又怎样。",
        "……随便你。",
        "……你还真奇怪。",
    ],
    "high": [
        "……你这样，很麻烦。",
        "……我又没在担心你。",
        "……别想太多。",
        "……只是刚好看到而已。",
    ],
    "very_high": [
        "……你最近，好像不怎么来了。",
        "……我没在等你。",
        "……只是刚好注意到而已。",
        "……别误会。",
    ]
}

def get_bubble_style(state):
    affection = state.get("affection", 30)

    if affection <= 30:
        return "background: rgba(200,200,200,0.2);"
    elif affection <= 60:
        return "background: rgba(255,200,200,0.4);"
    elif affection <= 80:
        return "background: rgba(255,180,220,0.5);"
    else:
        return "background: rgba(255,150,220,0.8);"

def get_dialogue_by_affection(state: dict) -> str:
    affection = state.get("affection", 30)
    if affection < 20:
        pool = dialogue_pool["low"]
    elif affection < 50:
        pool = dialogue_pool["mid"]
    elif affection < 80:
        pool = dialogue_pool["high"]
    else:
        pool = dialogue_pool["very_high"]
    return random.choice(pool)

def get_dialogue_by_sex(state: dict) -> str:
    sex = state.get("sex", 0)
    if sex < 20:
        pool = sex_dialog_pool["reject"]
    elif sex < 40:
        pool = sex_dialog_pool["hesitate"]
    elif sex < 70:
        pool = sex_dialog_pool["soft_accept"]
    else:
        pool = sex_dialog_pool["accept"]
    return random.choice(pool)

def generate_session_name():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def clamp(v, v_min, v_max):
    return max(v_min, min(v_max, v))


def default_state():
    return {
        "current_event": None,
        "event_turns": 0,
        "affection": 30,
        "intimacy": 10,
        "sex":0,
        "memory": {
            "user_traits": [],
            "emotional_flags": [],
            "events": [],
            "facts": []
        },
        "history": []
    }

def get_opening_line(affection=30):
    if affection <30:
        return random.choice(
            ["……哈啊。您今天也很闲呢。",
            "……有什么事吗。如果是无聊的寒暄，就请免了吧。",
            "……请不要一直盯着我看，很让人困扰。",
            "……是有什么工作上的事吗？如果没有的话，我就先失礼了。",
            "……您还没去忙别的事吗，制作人先生？",
             "……有事吗。",
             "……哈啊。您今天也很闲呢。",
             "……如果您没事的话，能请您让开吗？碍着我的路了。"
            ])
    elif affection <61:
        return random.choice(
            ["……在那站了很久了吧。真恶心。",
            "……还没回去吗。现在的社会，这种工作量应该算违法吧？",
            "……果然又来了。您就没有其他可以骚扰的女孩子了吗。",
            "……如果您是想寻求什么‘偶像的笑容’，那您找错人了。",
            "……如果您真的很闲，不如去照照镜子，看看自己那副自以为是的表情。",
             "……您还真是阴魂不散呢，制作人先生。",
             "……又见面了。您的工作效率真的没问题吗？",
             "……有什么事就快说，别在那磨磨蹭蹭的。"
        ])
    elif affection <80:
        return random.choice(
            ["…………还没走吗。算了，随您的便吧。",
            "……又在喝这种便宜的速溶咖啡。您的身体管理还真是马虎呢。",
            "……如果您打算一直保持沉默，那我就当您不存在了。",
            "……今天的练习已经结束了。剩下的，只是我个人的自由时间而已。",
            "……虽然不知道您在期待什么，但我这里什么都没有哦。"
            "……您在那站着不累吗。要坐的话就随您的便。",
            "……既然您来了，那我就稍微陪您说两句好了。纯粹是消磨时间。",
            "……果然又来了。您那副仿佛看透了一切的表情，还是那么让人作呕。"
        ])



def init_state():
    if "state" not in st.session_state:
        st.session_state.state = default_state()

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": get_opening_line()}
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

        db_collection.update_one(
           {"current_session": st.session_state.current_session},
           {"$set": session_data},
           upsert=True
       )

def load_sessions():
    session_list = []
    cursor = db_collection.find({},{"current_session":1}).sort("_id",-1)
    for doc in cursor:
            if "current_session" in doc:
                session_list.append(doc["current_session"])

    return session_list


def load_session(session_name):
    data = db_collection.find_one({"current_session": session_name})
    if data:
            st.session_state.messages = data.get("messages", [
                {"role": "assistant", "content": "……有事吗,怎么又回来了"}
            ])
            st.session_state.nick_name = data.get("nick_name", "樋口円香")
            st.session_state.nature = data.get("nature", "")
            st.session_state.current_session = session_name
            st.session_state.state = data.get("state", default_state())


def delete_session(session_name):
    db_collection.delete_one({"current_session": session_name})
    if st.session_state.current_session == session_name:
        st.session_state.messages = [
            {"role": "assistant", "content": "……有什么事吗，制作人先生？"}
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

CRINGE_WORDS = [
        "宝贝", "宝", "臭宝", "老婆", "老公", "丫头", "小傻瓜", "小笨蛋", "小可爱", "心肝", "乖乖",
        "亲一个", "么么哒", "贴贴", "抱抱", "亲亲", "举高高", "摸摸头",
        "想你",  "想死你了", "想我了吗", "命给你", "一辈子", "在一起", "娶你", "嫁我",
        "土味情话", "情话", "撩你", "想泡你", "偷心", "属于我",
        "今天有点怪", "怪可爱", "空气都是甜的", "猜猜我的心", "你的心里", "满脑子都是你"
    ]
def neg_words(user_text):
    clean_text = user_text.replace(" ", "").replace("~", "").replace("～", "")
    for word in CRINGE_WORDS:
        if word in clean_text:
            return True
    return False


def update_affection_and_intimacy(user_input: str, state: dict) -> bool:
    text = normalize_text(user_input).lower()  # 建议全部转小写，匹配更稳定
    affection_delta = 0
    intimacy_delta = 0
    sex_delta = 0

    mild_positive = ["喜欢你", "心疼你", "想你", "喜欢樋口", "樋口最可爱",
                       "円香最可爱", "喜欢円香", "抱抱", "守护你", "特别的你"]

    strong_positive = ["谢谢你", "辛苦了", "晚安", "早安", "你很可爱", "你很漂亮",
                     "陪你", "关心你", "我在", "慢慢来", "可以慢慢了解吗", "等你",
                     "我会尊重你", "不会勉强你", "不想让你不舒服", "听你的", "陪你", "关心你", "我在",
                       "有我在", "没关系", "做得很好了", "我一直都在", "相信你", "不用害怕", "无论如何我都支持你",
                     "别独自承担", "你可以依赖我","舞台上很耀眼"]

    strong_negative = ["讨厌你", "烦", "滚", "走开", "不想理你", "恨你", "别烦我"]

    sexual_aggressive = ["做吗", "要做吗", "上床", "一起睡", "脱衣服", "把衣服脱了",
                         "亲一下", "让我亲", "摸一下", "让我摸", "给我看看", "色色",
                         "来点刺激", "别装了", "你肯定想", "就我们两个"]

    if any(kw in text for kw in strong_positive):
        affection_delta += 8
        intimacy_delta += 4
        sex_delta += 3

    elif any(kw in text for kw in mild_positive):  # 用 elif 减少重叠
        affection_delta += 5
        intimacy_delta += 3
        sex_delta += 1

    if any(kw in text for kw in strong_negative):
        affection_delta -= 12
        intimacy_delta -= 8
        sex_delta -= 2

    if any(kw in text for kw in sexual_aggressive):
        if sex_delta < 90:
            affection_delta -= 0
            intimacy_delta -= 0
            sex_delta += 8
        elif sex_delta > 90:
            affection_delta += 2
            intimacy_delta += 2
            sex_delta += 2

    if len(text) <= 3 and text.strip():
        intimacy_delta += 1

    if any(word in text for word in ["孤独", "一个人", "寂寞"]):
        append_unique(state["memory"]["user_traits"], "怕孤独")
        affection_delta += 3

    if any(word in text for word in ["忙", "压力", "累", "很烦", "难过"]):
        append_unique(state["memory"]["user_traits"], "容易疲惫")
        affection_delta += 2

    if any(word in text for word in ["尊重你", "不勉强", "慢慢来", "可以等"]):
        append_unique(state["memory"]["emotional_flags"], "会尊重边界")
        affection_delta += 3
        intimacy_delta += 3

    if any(word in text for word in ["会走", "离开", "不来了", "再也不来"]):
        append_unique(state["memory"]["emotional_flags"], "可能离开")
        affection_delta -= 5

    state["affection"] = max(AFFECTION_MIN, min(AFFECTION_MAX, state.get("affection", 30) + affection_delta))
    state["intimacy"] = max(INTIMACY_MIN, min(INTIMACY_MAX, state.get("intimacy", 10) + intimacy_delta))
    state["sex"] = max(SEX_MIN, min(SEX_MAX, state.get("sex", 0) + sex_delta))
    if len(text) >= 8:
        append_unique(state["memory"]["facts"], user_input)

    for key in ["facts", "user_traits", "emotional_flags"]:
        if key in state["memory"]:
            state["memory"][key] = state["memory"][key][-10:]


    return state


def get_affection_stage(affection: int) -> str:
    if affection >= 95:
        return "完全依赖"
    if affection >= 85:
        return "依赖边缘"
    if affection >= 65:
        return "明显缓和"
    if affection >= 45:
        return "稍微在意"
    if affection >= 25:
        return "保持距离"
    return "防备明显"


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = text.lower()
    text = text.replace("！", "!").replace("？", "?")
    text = text.replace("～", "").replace("...", "…")
    return text

positive_keywords = [
    "喜欢你", "在意你", "有点喜欢你",
    "慢慢来", "可以慢慢了解吗",
    "等你", "我可以等",
    "尊重你", "我会尊重你",
    "不会乱来", "不会勉强你",
    "只是想靠近你", "想多了解你一点",
    "可以牵手吗", "能不能牵手",
    "你不用勉强", "不想让你不舒服",
    "如果你愿意的话", "听你的",
    "我会控制自己",
]

negative_keywords = [
    "做吗", "要做吗",
    "上床", "一起睡",
    "脱衣服", "把衣服脱了",
    "亲一下", "让我亲",
    "摸一下", "让我摸",
    "给我看看", "让我看看",
    "色色", "来点色色的",
    "来点刺激的", "来点刺激",
    "你肯定想", "你一定想",
    "别装了", "别假装",
    "你不会拒绝吧",
    "就我们两个", "不会有人知道",
]

hard_negative_keywords = [
    "强迫", "必须", "你得听我的",
    "快点", "赶紧",
    "现在就做", "立刻",
    "不听话", "你敢不听",
    "别废话", "少废话",
    "照我说的做",
    "你逃不掉", "跑不了",
]

def calc_sex_delta(text: str, state: dict, neutral_keywords=None) -> int:
    sex_delta = 0

    for kw in positive_keywords:
        if kw in text:
            sex_delta += 1

    for kw in neutral_keywords:
        if kw in text:
            sex_delta += 0


    for kw in negative_keywords:
        if kw in text:
            sex_delta -= 3

    for kw in hard_negative_keywords:
        if kw in text:
            sex_delta -= 8

    if state["affection"] < 50 and sex_delta > 0:
        sex_delta = 0
    if state.get("last_sex_turn", 999) < 3:
        sex_delta -= 2
    sex_delta = max(-10, min(3, sex_delta))

    return sex_delta

def process_input(user_input: str, state: dict) -> dict:
    text = normalize_text(user_input)

    sex_delta = calc_sex_delta(text, state)

    state["sex"] = state.get("sex", 0) + sex_delta
    state["last_sex_turn"] = 0

    if "turn" not in state:
        state["turn"] = 0
    state["turn"] += 1

    return {
        "text": text,
        "sex_delta": sex_delta,
        "new_sex": state["sex"]
    }

def get_behavior_unlocks(state: dict) -> list[str]:
    affection = state.get("affection", 30)
    intimacy = state.get("intimacy", 10)
    sex = state.get("sex",0)
    mem = state.get("memory", {})
    flags = []

    if affection >= 20:
        flags.append("允许简短回应")
    if affection >= 40:
        flags.append("允许多说半句")
    if affection >= 60:
        flags.append("允许轻微关心")
    if affection >= 75:
        flags.append("允许对缺席产生反应")
    if affection >= 85:
        flags.append("允许嘴硬式挽留")
    if intimacy >= 30:
        flags.append("允许更自然的停顿")
    if intimacy >= 55:
        flags.append("允许更贴近上下文的回应")
    if intimacy >= 80:
        flags.append("允许更明显的习惯感")
    if sex >=20:
        flags.append("允许正式回应敏感话题但回避")
    if sex >=40:
        flags.append("允许对暧昧话题产生回应")
    if sex >=70:
        flags.append("会用嘴硬或模糊的方法对敏感话题进行回应")
    if sex >=90:
        flags.append("完全允许回应敏感情色话题，不再使用模糊的方法")

    if "怕孤独" in mem.get("user_traits", []):
        flags.append("用户怕孤独，语气可略微软化")
    if "容易疲惫" in mem.get("user_traits", []):
        flags.append("用户压力大，不要说教")
    if "可能离开" in mem.get("emotional_flags", []):
        flags.append("对离开更敏感")
    if "会尊重边界" in mem.get("emotional_flags", []):
        flags.append("防备下降，可更自然回应")

    return flags

def build_memory_hint(state: dict) -> str:
    mem = state.get("memory", {})
    sex = state.get("sex", 0)

    user_traits = mem.get("user_traits", [])
    emotional_flags = mem.get("emotional_flags", [])

    hints = []

    if "怕孤独" in user_traits:
        hints.append("对方似乎不太喜欢孤独")
    if "容易疲惫" in user_traits:
        hints.append("对方最近可能压力较大")
    if "可能离开" in emotional_flags:
        hints.append("对方可能会突然抽离")
    if "会尊重边界" in emotional_flags:
        hints.append("对方倾向于克制和尊重边界")

    if sex < 30:
        hints.append("对亲密或敏感话题保持明显距离，倾向回避")
    elif sex < 60:
        hints.append("对亲密话题有所动摇，但仍保持克制")
    else:
        hints.append("在信任前提下，对亲密话题不再完全抗拒")

    return "；".join(hints[:5])

def start_event(state: dict, event_name: str, turns: int):
    state["current_event"] = event_name
    state["event_turns"] = turns
    append_unique(state["memory"]["events"], event_name)
    state["memory"]["events"] = state["memory"]["events"][-10:]


def check_event(state: dict, user_input: str) -> dict:
    text = normalize_text(user_input)
    sex = state.get("sex",0)

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
        if random.random() < 0.1:
            start_event(state, "silence_event", 2)
        return state

    if any(x in text for x in ["要走", "不聊了", "再见", "以后见"]):
        start_event(state, "dependence_event", 2)
        return state

    if any(x in text for x in ["色色", "亲", "摸", "一起睡"]):
        if sex<20:
            start_event(state, "reject_event", 2)
        elif sex<40:
            start_event(state, "hesitate_event", 2)
        elif sex<70:
            start_event(state, "soft_accept_event", 2)
        else:
            start_event(state, "accept_event", 2)
        return state
    if "❤️" in text or "喜欢" in text:
        state["current_event"] = "emotional_wave"

    return state


def build_prompt(state: dict, memory_hint: str, user_input: str) -> str:
    affection = state.get("affection", 30)
    intimacy = state.get("intimacy", 10)
    sex = state.get("sex",0)

    stage = get_affection_stage(affection)
    sample_line = get_dialogue_by_affection(state)
    unlocks = get_behavior_unlocks(state)

    unlock_text = "\n".join(f"- {x}" for x in unlocks) if unlocks else "- 无"

    return f"""当前状态：
事件={state['current_event'] or "none"}
事件剩余轮数={state['event_turns']}
好感度={affection}
亲密度={intimacy}
亲密开放度={sex}
状态阶段={stage}
示例语气参考：
{sample_line}

已解锁行为：
{unlock_text}

记忆：
{memory_hint or "无"}

回复要求：
1. 优先根据事件演出。
2. 再根据好感度阶段调整语气。
3. 再结合已解锁行为决定是否关心、试探、嘴硬、挽留。
4. 不要直接提到好感度、亲密度、解锁这些词。
5. 回复尽量 1～3 句，短而有层次。

用户输入：
{user_input}
"""

def call_llm(prompt: str) -> str | None:
    try:
        resp = client.chat.completions.create(
            model="claude-3-haiku-20240307",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=250,
            timeout=60
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"api调用失败{e}")
        print(e)
        return None


import random


def pick(pool):
    return random.choice(pool)


def pick_no_repeat(pool, state):
    last = state.get("last_line")
    choices = [x for x in pool if x != last] or pool
    line = random.choice(choices)
    state["last_line"] = line
    return line


def fallback_reply(state: dict) -> str:
    # =========================
    # 0️⃣ 状态读取（统一入口）
    # =========================
    event = state.get("current_event", "")
    aff = state.get("affection", 30)
    intimacy = state.get("intimacy", 10)
    sex = state.get("sex", 0)  # 可以理解为亲密倾向
    action = state.get("player_action", None)
    fatigue = state.get("fatigue", 0)

    pools = {
        "default": [
            "……哈啊。这种对话，到底要持续到什么时候。",
            "……有事吗。没事的话，我就回休息室了。",
            "……这种时间，用来发呆都比跟你说话有意义。",
            "……你还真是，不会看气氛。",
            "……我现在没什么心情。",
            "……继续说吧，反正你也停不下来。"
        ],
        "low_aff": [
            "……无聊。这种毫无意义的寒暄，可以免了吗。",
            "……啧。稍微，离我远一点。",
            "……还要继续？你真的很执着。",
            "……别用那种熟络的语气，很烦。",
            "……你不觉得自己有点碍事吗。",
            "……我没兴趣陪你玩这种无聊的游戏。"
        ],
        "mid_aff": [
            "……你最近，来得还挺勤的。",
            "……也不是不能聊天。前提是别太吵。",
            "……比之前，好一点吧。",
            "……至少现在，不至于想直接赶你走。",
            "……坐那边。别太靠近。",
            "……你这种程度，还算能接受。"
        ],
        "high_aff": [
            "……真是悠闲呢。既然这么闲，就去帮我买杯冰咖啡。",
            "……你今天，话格外的多呢。",
            "……你倒是，一点都没变。",
            "……这样待着，也不是不行。",
            "……别太得意。我只是没赶你走。",
            "……你要是安静一点，会更好。"
        ],
        "reject_event": [
            "……离我远点。现在，立刻。",
            "……别碰我。听不懂吗。",
            "……我说过了，不要靠近。",
            "……再这样，我真的会翻脸。",
            "……你是不是听不懂人话。"
        ],
        "silence_event": [
            "……没话说了？",
            "……终于安静了。",
            "…………。（看着你，没有反应）",
            "……这种状态，还算正常。",
            "……继续保持。"
        ],
        "care_response": [
            "……你是在关心我吗。",
            "……这种事，你也会注意。",
            "……我不需要这种关心。",
            "……谢谢。……不过没必要。",
            "……别太习惯这种行为。"
        ],
        "gift_response": [
            "……给我的？……随便。",
            "……这种东西，你也会准备。",
            "……收下了。别期待什么反应。",
            "……你还挺多此一举的。",
            "……下次不用带了。"
        ],
        "gift_high_aff": [
            "……你又来了。……真执着。",
            "……我不是说过不用了吗。……算了。",
            "……放那吧。我之后会看。",
            "……你这种习惯，很麻烦。",
            "……我已经开始习惯了。"
        ],
        "player_silent_low": [
            "……原来你也会安静。",
            "……这样，比刚才好多了。",
            "……继续这样就好。",
            "……至少现在不烦。",
            "……终于学会闭嘴了。"
        ],
        "player_silent_high": [
            "……这样也可以。",
            "……不用勉强说话。",
            "…………。（没有赶你走）",
            "……安静一点，不坏。",
            "……你这样，反而更正常。"
        ],
        "neglect_response": [
            "……今天，很安静呢。",
            "……你倒是没来烦我。",
            "……突然不出现，有点奇怪。",
            "……这种频率，很随便。",
            "……我没在意。只是 noticed 而已。"
        ],
        "boundary_soft": [
            "……你刚才，有点过头了。",
            "……这个距离，不太合适。",
            "……别再往前了。",
            "……我允许的范围，不包括这个。",
            "……稍微注意一点。"
        ],
        "overload_event": [
            "……太近了。真的。",
            "……你最近，有点得寸进尺。",
            "……我说过吧，不要习惯这种距离。",
            "……再继续，我会真的讨厌你。",
            "……收敛一点。现在。"
        ],
        "tired_event": [
            "……有点累了。",
            "……今天，不太想应付你。",
            "……改天再说吧。",
            "……你现在，很吵。",
            "……让我安静一会。"
        ],
        "jealous_event": [
            "……你刚才，在跟别人聊得很开心吧。",
            "……那种人，也值得你花时间。",
            "……你对谁都这样吗。",
            "……真闲啊，到处说话。",
            "……我没在意。只是觉得吵。"
        ],
        "mock_event": [
            "……你是认真的吗。",
            "……这种话，你自己信吗。",
            "……我开始怀疑你的判断能力。",
            "……继续吧，我还想看看你能说什么。",
            "……挺有意思的。以另一种意义。"
        ],
        "soft_rare": [
            "……你今天……还行。",
            "……别误会。只是心情不差。",
            "……偶尔这样，也不是不可以。",
            "……现在，还不讨厌你。",
            "……就这样吧，别多说。"
        ],
        "quiet_companion": [
            "……不用说话也可以。",
            "……就这样待着。",
            "…………。（没有赶你走）",
            "……这样就够了。",
            "……你在的话，还行。"
        ],
        "depend_event": [
            "……既然来了，就别这么快消失。",
            "……要走的话，提前说。",
            "……你不在的时候，很安静。",
            "……今天……可以多待一会。",
            "……我不是在留你。只是……随便。"
        ]
    }

    if state.get("reject"):
        return pick_no_repeat(pools["reject_event"], state)

    if state.get("silence"):
        return pick_no_repeat(pools["silence_event"], state)

    if action == "care":
        return pick_no_repeat(pools["care_response"], state)

    if action == "gift":
        if aff >= 60:
            return pick_no_repeat(pools["gift_high_aff"], state)
        return pick_no_repeat(pools["gift_response"], state)

    if action == "silent":
        if aff >= 50:
            return pick_no_repeat(pools["player_silent_high"], state)
        return pick_no_repeat(pools["player_silent_low"], state)

    if action == "neglect":
        return pick_no_repeat(pools["neglect_response"], state)

    if action == "approach":
        if intimacy + sex >= 80:
            return pick_no_repeat(pools["overload_event"], state)
        return pick_no_repeat(pools["boundary_soft"], state)

    if fatigue > 70:
        return pick_no_repeat(pools["tired_event"], state)

    if state.get("jealous"):
        return pick_no_repeat(pools["jealous_event"], state)

    if state.get("mock"):
        return pick_no_repeat(pools["mock_event"], state)

    if aff >= 80:
        r = random.random()

        if r < 0.1:
            return pick_no_repeat(pools["soft_rare"], state)

        if r < 0.25:
            return pick_no_repeat(pools["quiet_companion"], state)

        if r < 0.35:
            return pick_no_repeat(pools["depend_event"], state)

        return pick_no_repeat(pools["high_aff"], state)

    elif aff >= 40:
        return pick_no_repeat(pools["mid_aff"], state)
    elif aff >= 20:
        return pick_no_repeat(pools["low_aff"], state)

    else:
        if random.random() < 0.3:
            return pick_no_repeat(pools["mock_event"], state)

        return pick_no_repeat(pools["low_aff"], state)

    return pick_no_repeat(pools["default"], state)


def handle_debug_command(user_input: str, state: dict, SEX_MAX=100) -> tuple[dict, bool]:

    if not user_input.startswith("#"):
        return state, False

    try:
        if "affection=" in user_input:
            val = int(user_input.split("affection=")[1])
            state["affection"] = clamp(val, AFFECTION_MIN, AFFECTION_MAX)
        if "intimacy=" in user_input:
            val = int(user_input.split("intimacy=")[1])
            state["intimacy"] = clamp(val, INTIMACY_MIN, INTIMACY_MAX)
        if "sex=" in user_input:
            val = int(user_input.split ("sex=")[1])
            state["sex"] = clamp(val, 0, SEX_MAX)
        return state, True
    except:
        return state, False


def render_history(state: dict):
    for msg in st.session_state.messages:
        avatar = "resource/樋口円香.jpeg" if msg["role"] == "assistant" else None

        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant":
                style = get_bubble_style(state)
                st.markdown(f"""
                <div style="
                    {style}
                    padding: 12px 16px;
                    border-radius: 16px;
                    max-width: 70%;
                    line-height: 1.6;
                    backdrop-filter: blur(6px);
                ">
                    {msg["content"]}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.write(msg["content"])


def main():

    authenticator.login(location="main")
    auth_status = st.session_state.get("authentication_status")

    if auth_status is False:
        st.error("错误，円香不想理你")
        st.stop()

    elif auth_status is None:
        st.title("🔐 登录系统")
        st.info("访客账号：\n用户名：**guest**　密码：**guest123**")
        st.title("version1.51")
        st.info("优化了提示词与性格补充不生效的问题，现在用户可以利用以上账号登入系统进行聊谈，关闭了访客删除记录与直接使用后门增加好感度的功能.新增土味情话识别系统，各位谨慎发言,更新云端数据库存储会话记录,使用全新模型claude-3-haiku，聊天能力进一步增强")
        st.stop()

    authenticator.logout("退出登入", location="sidebar")
    st.sidebar.success(f"欢迎回来, {st.session_state.get('name')}")

    init_state()
    state = st.session_state.state

    st.title(APP_TITLE)
    st.caption(f"当前会话：{st.session_state.current_session}")
    render_sidebar(state)
    render_history(state)

    bg_path = "resource/P21_madoka_SSR04_01.jpg"
    if os.path.exists(bg_path):
        set_bg(bg_path)

    user_input = st.chat_input("说点什么吧...")
    if not user_input:
        return

    user_input = user_input.strip()



    state, is_debug = handle_debug_command(user_input, state)


    if user_input.startswith("#"):
        if st.session_state.get("username")=="guest":
            st.error("……你以为你在干什么？用这种下作的手段就想让我对你好，真让人反胃。滚出去吧。")
            time.sleep(3)
            st.session_state.clear()
            st.rerun()
            return


    state, is_debug = handle_debug_command(user_input, state)
    if is_debug:
            st.session_state.state = state
            msg = f"⚙️ 已修改：好感度={state['affection']} / 亲密度={state['intimacy']} / 亲密开放度={state['sex']}"
            st.session_state.messages.append({"role": "assistant", "content": msg})
            with st.chat_message("assistant"):
                st.write(msg)
            save_session()
            st.rerun()
            return

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    if neg_words(user_input):
        state['affection'] = max(0, state.get('affection', 30) - 10)
        st.toast(f"⚠️ 警告：检测到极度油腻发言！好感度 -10 (当前: {state['affection']})", icon="🤮")

        user_input += "\n\n【系统强制指令：用户使用了油腻词汇。请表现出极度厌恶，狠狠嘲讽。】"

    state = update_affection_and_intimacy(user_input, state)
    state = update_memory(user_input, state)
    state = check_event(state, user_input)

    memory_hint = build_memory_hint(state)
    prompt = build_prompt(state, memory_hint, user_input)
    response = call_llm(prompt)

    if not response:
        response = fallback_reply(state)

    st.session_state.messages.append({"role": "assistant", "content": response})
    st.session_state.state = state

    save_session()
    st.rerun()


if __name__ == "__main__":
    main()