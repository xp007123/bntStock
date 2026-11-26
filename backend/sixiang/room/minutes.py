"""纪要：聊了一阵之后，小四把每位嘉宾的立场记成一张卡。也是分享图的原料。

谁负责什么（这是这张卡能不能信的关键）：
- 每位嘉宾的那句话：从他真说过的话里原样引用。模型只挑“哪一条”，不改写。
- 数据：只用嘉宾当时查到的原文。模型只挑“哪一条”。
- 立场（看多 / 看空 / 再等等）和“分歧在哪”那一句：模型来判断和措辞；那一句里不许出现数字，出现了就不要。
模型说不清、答非所问时，卡照样出：没有立场标签，引用每个人最后说的那句。
"""
from __future__ import annotations

import datetime as dt
import json
import re

from .llm import ChatModel
from .personas import Persona
from .state import Room

STANCES = ("看多", "看空", "再等等")
LINE = "我把大家的看法记了一下。"
EMPTY_LINE = "还没人开口，没什么可记的。"
LOOKBACK = 60          # 只看最近这么多条消息
MAX_DATA = 8


def _bubbles(room: Room, cast: dict[str, Persona]) -> list[tuple[str, int, str]]:
    """嘉宾说过的每一句（一行算一句）：(嘉宾 id, 消息序号, 原话)。"""
    out = []
    for m in room.messages[-LOOKBACK:]:
        if m.role == "guest" and m.persona_id in cast:
            out += [(m.persona_id, m.seq, line.strip()) for line in m.text.split("\n") if line.strip()]
    return out


def _data(room: Room) -> list[str]:
    seen: list[str] = []
    for m in room.messages[-LOOKBACK:]:
        for d in m.data:
            if d not in seen:
                seen.append(d)
    return seen[-MAX_DATA:]


def prompt(room: Room, cast: dict[str, Persona]) -> list[dict] | None:
    lines = _bubbles(room, cast)
    if not lines:
        return None
    names = "、".join(dict.fromkeys(cast[p].name for p, _, _ in lines))
    talk = "\n".join(f"[{i}] {cast[p].name}：{t}" for i, (p, _, t) in enumerate(lines, 1))
    data = "\n".join(f"({i}) {d}" for i, d in enumerate(_data(room), 1)) or "（没有）"
    ask = ('请输出：\n{"stances":[{"name":"嘉宾名","stance":"看多、看空、再等等 三选一","quote":这位嘉宾最能代表他看法的那条发言的编号}],'
           '"split":"一句话说他们最大的分歧在哪","data":最值得记下来的那条数据的编号，没有就写 0}\n'
           "要求：每位发过言的嘉宾都要有一条。stance 按他对这只股票的态度判断：明确看好是看多，明确不看好是看空，其余是再等等。"
           "split 不超过 40 个字，不出现任何数字，不评判谁对，不说该买该卖。")
    return [{"role": "system", "content": "你是群聊的记录员，只做记录，不加自己的观点。只输出一个 JSON 对象，不要任何别的字。"},
            {"role": "user", "content": f"股票：{room.topic.get('name', '')}\n嘉宾：{names}\n\n聊天记录（每条前面是编号）：\n{talk}\n\n查到过的数据：\n{data}\n\n{ask}"}]


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        v = json.loads(m.group(0)) if m else {}
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def build(room: Room, cast: dict[str, Persona], reply_text: str, anchor: dict | None = None) -> dict | None:
    """把模型的回答核对一遍，拼成卡。anchor 是出纪要时的行情（哪天、收盘价），回访时用它算之后的涨跌。"""
    lines = _bubbles(room, cast)
    if not lines:
        return None
    got = _parse(reply_text)
    by_name = {str(s.get("name", "")).strip(): s for s in got.get("stances") or [] if isinstance(s, dict)}
    stances = []
    for pid in dict.fromkeys(p for p, _, _ in lines):
        mine = [(seq, t) for p, seq, t in lines if p == pid]
        said = by_name.get(cast[pid].name, {})
        n = _int(said.get("quote"))
        seq, quote = (lines[n - 1][1], lines[n - 1][2]) if 1 <= n <= len(lines) and lines[n - 1][0] == pid else mine[-1]
        stances.append({"persona_id": pid, "name": cast[pid].name, "stance": said.get("stance") if said.get("stance") in STANCES else None,
                        "quote": quote, "seq": seq})
    split = str(got.get("split") or "").strip().strip("“”\"")
    data, n = _data(room), _int(got.get("data"))
    return {"type": "minutes", "code": room.topic.get("code"), "name": room.topic.get("name"), "stances": stances,
            "split": split if split and len(split) <= 60 and not re.search(r"\d", split) else None,
            "data": data[n - 1] if 1 <= n <= len(data) else (data[-1] if data else None), **(anchor or {})}


async def make(room: Room, cast: dict[str, Persona], model: ChatModel, anchor: dict | None = None) -> dict | None:
    messages = prompt(room, cast)
    if messages is None:
        return None
    reply = await model.chat(messages, max_tokens=1500, temperature=0)
    return build(room, cast, reply.text, anchor)


def anchor(market, code: str) -> dict:
    """出纪要这一刻的行情：最新一根日线的日期和收盘价（不复权，给人看的）。"""
    try:
        bar = market.daily(code, adjust="none", limit=1)["bars"][-1]
        return {"asof": bar["date"], "close": bar["close"]}
    except Exception:  # noqa: BLE001  取不到就不带，回访那一行不显示
        return {}


def since(market, card: dict) -> dict | None:
    """纪要之后到现在：过了几个交易日、涨跌多少（前复权，跨除权日也可比）。还没有新行情就返回 None。"""
    if not card.get("asof") or not card.get("code"):
        return None
    try:
        bars = market.daily(card["code"], start=dt.date.fromisoformat(card["asof"]), adjust="qfq")["bars"]
    except Exception:  # noqa: BLE001
        return None
    if len(bars) < 2 or bars[0]["date"] != card["asof"] or not bars[0]["close"]:
        return None
    return {"days": len(bars) - 1, "date": bars[-1]["date"], "ret": bars[-1]["close"] / bars[0]["close"] - 1}
