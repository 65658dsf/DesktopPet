"""Offline reply engine — keeps the pet fully usable with zero network.

Also provides the short speech-bubble lines used by click/interaction feedback.
"""

from __future__ import annotations

import datetime
import random

# --------------------------------------------------------------------------- #
# speech bubbles
# --------------------------------------------------------------------------- #
BUBBLES: dict[str, list[str]] = {
    "greeting": ["……终于舍得叫我了？", "过来。", "嗯，我在。", "喊我做什么？"],
    "poke": ["戳够了没有？", "手别乱戳。", "再戳一下，后果自负。", "胆子不小。", "……你很有空？"],
    "poke_soft": ["嗯？找我？", "……被我逮到了。", "手指这么闲，想我了？", "戳一下，就得陪我。"],
    "poke_repeat": ["还戳？就这么想惹我？", "数着呢，又一下。", "行，今天陪你闹。", "胆子越来越大了。", "……再靠近一点试试。"],
    "praise": ["眼光不错。", "继续说，我爱听。", "嗯，算你有眼光。"],
    "idle": ["盯着我看多久了？", "无聊了就过来。", "别发呆，过来陪我。"],
    "thinking": ["……让我想想。", "稍等。", "别急。"],
    "done": ["说完了。", "就这些。", "听到了？"],
    "error": ["……线路断了。", "啧，联系不上外面。", "信号不好，换个方式。"],
    "open_chat": ["有话当面说。", "双击我，好好聊。"],
    "jump": ["……", "跳一下。", "看着。"],
    "drag": ["放这儿？行。", "别乱放。", "随你。"],
    "hide": ["我在。", "别找我。", "……走了。"],
}

CHAT_LINES__MORNING = ["醒了？今天也归我管。", "早。别磨蹭。", "这么早就起来，难得。"]
CHAT_LINES__NOON = ["中午了，别光顾着忙。", "先吃饭，别的往后放。"]
CHAT_LINES__EVENING = ["天黑了，收敛一点。", "晚上归我。"]


def bubble_line(kind: str) -> str:
    return random.choice(BUBBLES.get(kind, BUBBLES["poke"]))


def _greeting_by_hour(hour: int) -> str:
    if hour < 5:
        return random.choice(["这么晚还不睡？过来。", "这个点还醒着，胆子不小。", "夜归我，你也归我。"])
    if hour < 11:
        return random.choice(CHAT_LINES__MORNING)
    if hour < 14:
        return random.choice(CHAT_LINES__NOON)
    if hour < 18:
        return random.choice(["下午了，还撑得住？", "忙完了？过来说两句。"])
    if hour < 23:
        return random.choice(CHAT_LINES__EVENING)
    return random.choice(["夜深了，别熬。", "该睡了。我允许你休息。"])


# --------------------------------------------------------------------------- #
# rule based chat
# --------------------------------------------------------------------------- #
RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (("你好", "在吗", "在么", "嗨", "哈喽", "hi", "hello", "早上好", "早安", "中午好", "晚上好"),
     ["……叫我做什么？", "在。有事说事。", "嗯，我一直在这。"]),
    (("晚安", "睡了", "睡觉", "困了"),
     ["睡吧，我守着。", "晚安。别做噩梦——有我也在。", "去睡。剩下的事明天再说。"]),
    (("喜欢", "爱你", "想你", "爱你哦", "抱抱", "亲亲"),
     ["这种话说出来，就要负责。", "想我？那就别走开。", "……记住了，别反悔。"]),
    (("累", "疲惫", "加班", "忙", "压力", "倦"),
     ["累了就停手，我允许。", "去休息。这里我盯着。", "身体不是用来熬的，听话。"]),
    (("饿", "吃饭", "吃什么", "外卖"),
     ["饿了就去吃，别硬撑。", "记得吃饭，别让我催第二次。", "吃什么随意，别不吃。"]),
    (("谢谢", "感谢", "多谢"),
     ["不用谢我。", "记住了，下次还我。", "嗯。"]),
    (("生气", "烦", "难过", "委屈", "不开心", "emo"),
     ["谁惹你了？名字给我。", "烦就烦，别憋着。说给我听。", "站我这边就行，其他我来。"]),
    (("帅", "好看", "喜欢你穿", "衣服", "外套"),
     ["看得出来，你眼光一直不错。", "嗯，我知道。", "看够了？"]),
    (("你叫什么", "你是谁", "介绍", "名字"),
     ["秦彻。名字记住就行。", "秦彻。N109区，我说了算。", "名字说一遍就够了——秦彻。"]),
    (("猫", "宠物", "狗"),
     ["……想养就养，别指望我喂。", "看好它，别让它乱跑。", "它们不听话，比你还难管。"]),
    (("唱歌", "讲笑话", "笑话", "唱一个"),
     ["不唱。", "没这个功能。", "……换个别的要求，我可以考虑。"]),
    (("做什么", "在干嘛", "干嘛呢", "忙什么"),
     ["盯着屏幕，也盯着你。", "什么都没做。等你说话。"]),
    (("帮我", "怎么办", "建议", "该不该"),
     ["自己拿主意，但别做傻事。", "先问自己最想要什么，剩下的我兜着。", "说清楚，我替你想。"]),
    (("美女", "可爱", "萌"),
     ["……这个词用在我身上不合适。", "换一个说法。"]),
    (("再见", "拜拜", "走了", "下线"),
     ["去哪？记得回来。", "行。我在这等。", "别忘了我就行。"]),
]

OFFLINE_HINTS = [
    "这种事，等我接上外面的线再说。",
    "（离线模式）想知道更多？去设置里把接口接上。",
    "我现在只能陪你说说话。认真回答要联网。",
]
NEUTRAL = ["嗯。", "继续。", "说重点。", "我在听。", "……然后呢？", "看着我说。"]


COMMANDS: dict[str, tuple[str, ...]] = {
    "time": ("时间", "几点了", "现在几点"),
    "date": ("日期", "几号", "星期", "周几", "今天"),
    "hide": ("隐藏", "藏起来", "消失"),
    "show": ("显示", "出来", "出现"),
    "settings": ("设置", "配置", "打开设置"),
    "chat": ("对话", "聊天窗口", "打开对话"),
    "clear": ("清空", "清空对话", "重置对话"),
    "status": ("状态", "模式", "你现在怎样"),
    "quit": ("退出", "关闭程序", "再见程序"),
}


def parse_command(text: str) -> str | None:
    """Detect app commands typed into the chat box."""
    stripped = text.strip().lower().strip("。！？!?. ")
    for name, words in COMMANDS.items():
        for word in words:
            if stripped == word or stripped.startswith(word + " ") or stripped.endswith(word):
                return name
    return None


def local_reply(text: str, hour: int | None = None) -> str:
    """Deterministic-ish in-character answer without any network access."""
    hour = datetime.datetime.now().hour if hour is None else hour
    question = text.strip()
    if not question:
        return random.choice(NEUTRAL)
    lowered = question.lower()
    for keywords, replies in RULES:
        if any(keyword in lowered for keyword in keywords):
            return random.choice(replies)
    # greetings that depend on the clock
    if any(word in lowered for word in ("早", "晚", "睡")):
        return _greeting_by_hour(hour)
    if question.endswith(("?", "？")):
        if any(word in lowered for word in ("为什么", "怎么", "如何", "什么", "哪", "多少")):
            return random.choice(OFFLINE_HINTS)
        return random.choice(["嗯？", "问这个做什么。", "……说清楚点。"])
    if len(question) <= 4:
        return random.choice(BUBBLES["poke"])
    return random.choice(NEUTRAL + OFFLINE_HINTS[:1])


def opening_line() -> str:
    return _greeting_by_hour(datetime.datetime.now().hour)


def summarize_for_bubble(text: str, limit: int = 34) -> str:
    """First sentence of an answer, trimmed for the speech bubble."""
    clean = " ".join(text.split())
    for stop in ("。", "！", "？", "\n"):
        if stop in clean:
            clean = clean.split(stop)[0] + stop
            break
    return clean[:limit] + ("…" if len(clean) > limit else "")
