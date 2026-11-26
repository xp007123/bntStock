"""导演：决定下一步谁说话、接谁的话、小四什么时候开场 / 拱火 / 收场。

一场戏是一个异步生成器：每次给出一步，运行器演完后把产生的消息送回来（没演成就送 None），导演再给下一步。
导演永远给得出下一步：需要“判断”的地方先用规则，用到模型的地方解析不了就退回规则。

第一版只有“圆桌”。以后的辩论赛、一对一、每日自动开场，都是新写一个同样形状的类，运行器不用改。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncGenerator

from . import prompts
from .llm import ChatModel
from .personas import Persona
from .state import Message, Room


@dataclass
class Speak:
    persona_id: str
    cue: str
    reply_to: int | None = None


@dataclass
class Host:
    action: str     # open 开场 / poke 拱火 / close 收场
    cue: str
    reply_to: int | None = None


Step = Speak | Host
Scene = AsyncGenerator[Step, Message | None]


class Roundtable:
    """圆桌：开场每人说一条 → 小四拱一处分歧 → 被点的人回应、对手回一句 → 小四收场，等用户。"""

    name = "roundtable"

    def __init__(self, cast: dict[str, Persona], model: ChatModel | None = None):
        self.cast = cast
        self.model = model

    def _n(self, pid: str) -> str:
        return self.cast[pid].name

    # ---------------------------------------------------------- 开场
    async def opening(self, room: Room) -> Scene:
        order = [p for p in room.members if p in self.cast]
        if not order:
            return
        yield Host("open", f"开场。用一句话说今天聊 {room.topic.get('name', '这只股票')}，带上简报里最扎眼的一个事实，然后点名让{self._n(order[0])}先说。")
        for i, pid in enumerate(order):
            if i == 0:
                cue = "小四点你先说。按你自己看股票的顺序，说你的第一反应。想看数据就先查。"
            else:
                prev = "、".join(self._n(p) for p in order[:i])
                cue = f"轮到你了。{prev}已经说过了。先接一句前面你最不同意的话（点名），再说你自己怎么看。想看数据就先查。"
            yield Speak(pid, cue)
        # 接上“拱火”那一段。异步生成器没有 yield from，演完的消息要手动转交进去
        inner = self._clash(room)
        try:
            step = await inner.asend(None)
            while True:
                step = await inner.asend((yield step))
        except StopAsyncIteration:
            return

    # ---------------------------------------------------------- 接着聊
    def more(self, room: Room) -> Scene:
        return self._clash(room)

    async def _clash(self, room: Room) -> Scene:
        pair = self._pick_pair(room)
        if not pair:
            return
        target, challenger = pair
        said = room.last_by(challenger)
        poke = yield Host("poke", f"拱火。{self._n(challenger)}和{self._n(target)}的说法对不上。把{self._n(challenger)}说过的一句扎心的话原样甩给{self._n(target)}，问他服不服。"
                                  + (f"（{self._n(challenger)}刚说过：{said.text}）" if said else ""))
        if poke:
            poke.meta["pair"] = [target, challenger]
        answer = yield Speak(target, f"小四在拱火，{self._n(challenger)}在质疑你。正面回应，别绕。可以反过来戳他的软肋。", reply_to=poke.seq if poke else None)
        back = yield Speak(challenger, f"{self._n(target)}刚回应了你。回一句，要短，要有新东西，别重复之前说过的。", reply_to=answer.seq if answer else None)
        yield Host("close", f"收场。用一两句话点破{self._n(target)}和{self._n(challenger)}到底在哪儿没谈拢，不评判谁对，然后把问题抛给{room.user_name}：问他站哪边，或者想听谁接着说。",
                   reply_to=back.seq if back else None)

    def _pick_pair(self, room: Room) -> tuple[str, str] | None:
        """挑一对还没吵过的对手：被点的人（target）和质疑他的人（challenger）。规则，不用模型。"""
        members = [p for p in room.members if p in self.cast]
        if len(members) < 2:
            return None
        used = {tuple(m.meta["pair"]) for m in room.messages if m.meta.get("pair")}
        pairs = [(a, b) for a in members for b in self.cast[a].rivals if b in members]
        pairs += [(a, b) for a in members for b in members if a != b]
        for a, b in pairs:
            if (a, b) not in used and (b, a) not in used:
                return a, b
        return pairs[len(used) % len(pairs)]

    # ---------------------------------------------------------- 用户说话
    async def on_user(self, room: Room, msg: Message) -> Scene:
        targets = await self._who_answers(room, msg)
        first = None
        for i, pid in enumerate(targets[:2]):
            cue = (f"{room.user_name}刚才在群里说话了" + ("，点名问你" if msg.meta.get("mentions") else "") + f"：“{msg.text}”。直接回他，叫他“你”。说人话，别讲大道理。")
            got = yield Speak(pid, cue, reply_to=msg.seq)
            first = first or got
        # 只有一个人接话时，让他的对手插一句：有来有回才好看
        if len(targets) == 1 and first:
            rival = next((r for r in self.cast[targets[0]].rivals if r in room.members), None)
            if rival:
                yield Speak(rival, f"{self._n(targets[0])}刚回答了{room.user_name}。你不同意他的说法，插一句，要短。", reply_to=first.seq)

    async def _who_answers(self, room: Room, msg: Message) -> list[str]:
        members = [p for p in room.members if p in self.cast]
        mentioned = [p for p in msg.meta.get("mentions", []) if p in members]
        if mentioned:
            return mentioned
        named = [p for p in members if self._n(p) in msg.text]
        if named:
            return named
        if self.model:
            reply = await self.model.chat(prompts.route_prompt(room, msg.text, self.cast), max_tokens=30, temperature=0)
            picked = sorted((reply.text.find(self._n(p)), p) for p in members if self._n(p) in reply.text)
            if picked:
                return [p for _, p in picked[:2]]
        # 退回规则：最后说话的那位嘉宾接
        last = next((m.persona_id for m in reversed(room.messages) if m.role == "guest" and m.persona_id in members), None)
        return [last or members[0]]


class Solo:
    """一对一深聊：只有一位角色，没有主持人。他开场、反问、一步步往下讲；用户说一句他回一句。"""

    name = "solo"

    def __init__(self, cast: dict[str, Persona], model: ChatModel | None = None):
        self.cast = cast

    def _who(self, room: Room) -> str | None:
        return next((p for p in room.members if p in self.cast), None)

    async def opening(self, room: Room) -> Scene:
        pid = self._who(room)
        if pid:
            yield Speak(pid, f"{room.user_name}想和你把{room.topic.get('name', '这只股票')}聊透。按你自己的方式开场：先查你下判断需要的数据，"
                             "说说你对这门生意的第一印象，然后问他一到两个你最想先弄清楚的问题。")

    async def on_user(self, room: Room, msg: Message) -> Scene:
        pid = self._who(room)
        if pid:
            yield Speak(pid, f"{room.user_name}刚说：“{msg.text}”。接着往下聊：回应他，需要数据就查，把你的分析往前推一步。", reply_to=msg.seq)

    async def more(self, room: Room) -> Scene:
        pid = self._who(room)
        if pid:
            yield Speak(pid, "他请你接着往下说。把你还没讲到的那一步讲完：比如价格够不够便宜、最坏会怎样、出现什么情况说明你看错了。别重复前面说过的。")
