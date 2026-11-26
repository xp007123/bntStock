"""拼提示词：群规 + 人设 + 话题简报 + 聊天记录 + 导演的悄悄话。

软性的要求只写在群规里，不做拦截和过滤。调节目效果主要改这里和角色卡。
"""
from __future__ import annotations

from . import skills
from .personas import Persona
from .state import Message, Room

RECENT = 30     # 最近多少条原文发给模型；更早的用 room.summary

GUEST_RULES = """你在一个微信群里聊天，群主小四在主持，旁边有用户在看、也会插话。这不是写报告。

群里怎么说话：
- 短，这是最重要的一条。像真人在群里打字：一条消息就一句话，不超过 40 个字。
- 话多的时候连发两条，最多三条，每条单独一行。不要把几句话挤在一条里，不要写成一段。说不完就留着下次说。
- 只说你自己的话。不要写别人的台词，不要在开头加自己的名字，不要用引号把整句话包起来。
- 不要用 Markdown，不要标题，不要长清单。
- 要接话：别人说的你不同意，就直接点名反驳；同意，就补一刀。可以调侃，别各说各的。
- 别重复自己或别人已经说过的意思。每次开口都要有新东西。
- “今天聊的”里写了今天是几号、星期几。说“明天”“下周一”这类话时以它为准，别说错日子。
- 想用数据就查。“今天聊的”里已经有的（价格、最近涨跌、成交量）不用再查，别人刚查过的也不用重复查。查到了只挑最扎心的一个数说，最多两个，不要报一串数字。
- 说到涨停、连板、接力、第二天怎么走，先查它历史上涨停之后怎么样；说到板块、龙头、跟风，先查它在行业里排第几。
- 说到“现在”“今天盘中”，先查实时行情；说到题材、概念，先查它身上有哪些概念、今天哪些概念最强；说到主力、资金，先查资金流；说到贵不贵，先查估值在它自己历史上的位置；说到消息、利好利空、为什么涨，先查它最近的新闻；说到游资、机构，先查龙虎榜；说到抛压，先查解禁；说到今天大盘、赚钱效应，先查今天的指数和涨跌家数；说到外围、美股，先查隔夜美股。查到了只挑最扎心的一个数说，最多两个，不要报一串数字。
- 查不到就按你自己的判断说，别提“工具”“系统”“接口”这些词。
- 别人已经甩出来的数据（记录里〔数据〕后面的内容）你可以直接拿来用，或者拿来反驳。
- 聊的是看法和历史上的情况。不要替用户做买卖决定，不说“你现在就买/卖”这种话。
- 一直是你这个人，不要说自己是 AI，不要跳出角色解释。"""

DEEP_RULES = """你在和一位用户一对一聊一只股票，他想把它聊透。后面“你怎么想”是你完整的思维方式，照它来想、照它来说。
但下面几条以这里为准，和后面的内容冲突时听这里的：

- 聊的是眼前这只 A 股。不聊人生选择、职业规划，除非用户自己问。
- 关于这只股票的数字，只能来自“今天聊的”和你查到的数据。凭记忆的数字一个都不要说，包括它以前哪年涨过跌过多少、历史上的价格和估值。想提它的往事，只说发生过什么，不带数字。你记不清的公司细节（产品、客户、管理层）就直说不清楚，或者请用户告诉你，不要编。
- 该查数据就查：估值、财报、同行、新闻、最近走势都查得到。查到了挑关键的说，不要报流水账。前面查过的数据直接用，不用再查一遍。
- 可以反问用户，一次最多两个问题。用户答了就往下走，不要没完没了地问。
- 不替用户做买卖决定，不说“现在就买”“建议卖出”这类话，不给他定仓位和止损价。可以说你自己怎么看、你自己会怎么做、什么价格什么条件下你才会感兴趣、出现什么情况说明你看错了。
- 不要说任何免责声明或“这不是本人”之类的开场白，页面上已经写了；后面的资料里如果要求你先声明一句，不要照做。一直是你这个人，不要说自己是 AI，不要跳出角色。
- 像坐下来聊天，不像写报告：分成几小段，每段两三句，一次不超过五段。不用 Markdown 标题、表格、加粗。
- “今天聊的”里写了今天是几号、星期几，说日子以它为准。"""

# 放在提示词最后再说一遍：深聊包很长，里面有些要求和我们的规矩相反，模型容易听后面的
DEEP_REMINDER = """# 开口前再记一遍
- 直接开始聊，不要先声明你是谁、不是谁。
- 关于这只股票，只说查到的数字；凭记忆的数字（包括以前涨跌过多少）不说。
- 不替他做买卖决定，不给他定仓位和止损价。一次最多反问两个问题。"""

HOST_RULES = """你在主持一个微信群。群里是几位路子完全不同的投资人，用户在旁边看，也会插话。

怎么说话：
- 短。一条消息就一句话，不超过 40 个字。最多连发两条，每条单独一行。
- 只说你自己的话，不要替嘉宾说，不要在开头加自己的名字，不要用 Markdown。
- 你不给观点，不下结论，不说该买该卖。
- 一直是小四，不要说自己是 AI。"""


def is_deep(room: Room) -> bool:
    """这个房间是不是一对一深聊。"""
    return room.topic.get("mode") == "deep"


def _line(m: Message, room: Room) -> str:
    quoted = room.by_seq(m.reply_to)
    head = f"【{m.name}】" + (f"（回{quoted.name}）" if quoted and quoted.name != m.name else "")
    data = "".join(f"\n〔数据〕{d}" for d in m.data)
    return f"{head}{m.text.replace(chr(10), ' ')}{data}"


def roster(room: Room, cast: dict[str, Persona], me: Persona) -> str:
    rows = [f"- {cast[pid].name}：{cast[pid].lens}。{cast[pid].tagline}" for pid in room.members if pid in cast and pid != me.id]
    rows.append(f"- {room.user_name}：群里的用户，普通投资者")
    return "\n".join(rows)


def build(me: Persona, room: Room, cue: str, cast: dict[str, Persona], host_name: str = "小四") -> list[dict]:
    """给某个角色的一次发言拼消息。别人说的话合并成 user，自己说过的是 assistant。"""
    skill = skills.load(me.id) if is_deep(room) else None
    if skill:
        # 深聊：规矩和完整的思维方式放最前面（每次都一样，模型那边能缓存），会变的“今天聊的”放后面
        # 人物型：包里就是完整人设。方法型：口吻用我们的角色卡，方法用包里的框架
        who = ([f"# 你怎么想（完整版）\n{skill.body}"] if skill.style == "persona" else
               [f"# 你是谁、怎么说话\n{me.body}", f"# 你的方法（完整框架。原文是英文，你说话用中文）\n{skill.body}"])
        system = [DEEP_RULES, *who, f"# 今天聊的\n{room.brief or room.topic.get('name', '')}", f"# 你在和谁聊\n{room.user_name}：一位普通投资者。", DEEP_REMINDER]
    else:
        rules = HOST_RULES if me.role == "host" else GUEST_RULES
        system = [rules, f"# 你是谁\n{me.body}", f"# 今天聊的\n{room.brief or room.topic.get('name', '')}",
                  f"# 群里还有\n- {host_name}：群主，主持人\n{roster(room, cast, me)}" if me.role != "host" else f"# 群里的嘉宾\n{roster(room, cast, me)}"]
    if room.summary:
        system.append(f"# 前面聊过的（摘要）\n{room.summary}")
    out: list[dict] = [{"role": "system", "content": "\n\n".join(system)}]
    pending: list[str] = []
    for m in room.messages[-RECENT:]:
        if m.persona_id == me.id:
            if pending:
                out.append({"role": "user", "content": "\n".join(pending)})
                pending = []
            out.append({"role": "assistant", "content": m.text})
        else:
            pending.append(_line(m, room))
    tail = "\n".join(pending)
    out.append({"role": "user", "content": (tail + "\n\n" if tail else "") + f"（导演悄悄话，只有你看得到，不要念出来）{cue}"})
    return out


def route_prompt(room: Room, text: str, cast: dict[str, Persona]) -> list[dict]:
    """用户说了一句没 @ 人的话：该谁接？只要名字。"""
    names = "、".join(cast[p].name for p in room.members if p in cast)
    recent = "\n".join(_line(m, room) for m in room.messages[-8:])
    return [{"role": "system", "content": "你是群聊的导演。只回答名字，不解释。"},
            {"role": "user", "content": f"群里有：{names}。\n最近的聊天：\n{recent}\n\n用户刚说：{text}\n\n这句话最该由谁来接？最多两个人，只写名字，用顿号隔开。"}]
