"""演员：把导演给的一步演出来，产生一条消息。

一条发言 = 一次模型调用（想查数据时最多再多两轮）。发言是纯文本，不要求任何格式。
失败即台词：模型出错、说了空话，这一条就不产生（返回 None），导演接着往下走；工具出错，角色照常说话。
"""
from __future__ import annotations

import asyncio
import re
from typing import Awaitable, Callable

from . import prompts, tools
from .director import Host, Speak, Step
from .llm import ChatModel, Reply
from .personas import Persona
from .state import Message, Room

MAX_TOOL_ROUNDS = 2     # 一条发言里最多查两轮数据：为了节奏和成本
MAX_BUBBLES = 3         # 一次最多连发三条
MAX_CHARS = 70          # 每条太长就截到句子结尾
MAX_TOKENS = 1500       # 输出上限给宽：模型说话前的思考也算在里面，给小了会想完没字可说

Emit = Callable[[str, dict], Awaitable[None] | None]


async def _send(emit: Emit | None, kind: str, payload: dict) -> None:
    if emit:
        r = emit(kind, payload)
        if asyncio.iscoroutine(r):
            await r


def tidy(text: str, name: str) -> str:
    """模型偶尔会带上名字前缀、整句引号、Markdown，或者说太长：收拾一下，不算错。"""
    t = (text or "").strip()
    t = re.sub(rf"^[【\[]?{re.escape(name)}[】\]]?\s*[：:]\s*", "", t)
    t = re.sub(r"^（[^）]{0,12}）", "", t).strip()            # “（回巴菲特）”这类照抄的标记
    t = re.sub(r"[*_`#>]+", "", t)
    if len(t) >= 2 and t[0] in "“\"「" and t[-1] in "”\"」":
        t = t[1:-1].strip()
    # 一行就是一条消息（真人在群里也是连发几条短的）。行太长就截到句子结尾，行太多只留前几条。
    bubbles = []
    for line in re.split(r"\s*\n+\s*", t):
        line = re.sub(r"^(?:[-•·]\s*|\d{1,2}[.、)）](?!\d)\s*)", "", line).strip()      # 去掉列表记号；“12.3 倍”这种小数不动
        if not line:
            continue
        if len(line) > MAX_CHARS:
            cut = max(line.rfind(ch, 0, MAX_CHARS) for ch in "。！？!?…；;")
            line = line[:cut + 1] if cut > 20 else line[:MAX_CHARS] + "…"
        bubbles.append(line)
    return "\n".join(bubbles[:MAX_BUBBLES])


async def perform(step: Step, room: Room, cast: dict[str, Persona], host: Persona, model: ChatModel,
                  ctx: tools.ToolContext, emit: Emit | None = None) -> Message | None:
    me = host if isinstance(step, Host) else cast.get(step.persona_id)
    if me is None:
        return None
    is_host = me.role == "host"
    await _send(emit, "typing", {"persona": me.id, "name": me.name})
    messages = prompts.build(me, room, step.cue, cast, host.name)
    offered = None if is_host else tools.schemas()
    cards: list[dict] = []
    data: list[str] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    seconds, calls, errors = 0.0, 0, []
    reply = Reply()

    async def on_text(piece: str) -> None:
        await _send(emit, "delta", {"persona": me.id, "text": piece})

    for round_ in range(MAX_TOOL_ROUNDS + 1):
        last = round_ == MAX_TOOL_ROUNDS
        reply = await model.chat(messages, None if last else offered, temperature=me.temperature,
                                 max_tokens=MAX_TOKENS, on_text=on_text)
        calls += 1
        seconds += reply.seconds
        for k in usage:
            usage[k] += int(reply.usage.get(k, 0) or 0)
        if reply.error:
            errors.append(reply.error)
        if not reply.tool_calls or last:
            break
        messages.append(reply.as_message())
        for call in reply.tool_calls:
            result = await asyncio.to_thread(tools.run, ctx, call.name, call.args())
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result.text})
            if result.ok:
                data.append(result.text)
                if result.card:
                    cards.append(result.card)

    text = tidy(reply.text, me.name)
    if not text and not reply.tool_calls:
        # 想了半天没说话：不带数据工具再催一次
        messages.append({"role": "user", "content": "（导演悄悄话）直接说话，就一两句。"})
        reply = await model.chat(messages, None, temperature=me.temperature, max_tokens=MAX_TOKENS, on_text=on_text)
        calls += 1
        seconds += reply.seconds
        if reply.error:
            errors.append(reply.error)
        text = tidy(reply.text, me.name)
    if not text:
        await _send(emit, "skipped", {"persona": me.id, "errors": errors})
        return None
    msg = room.add("host" if is_host else "guest", me.name, text, persona_id=me.id, reply_to=step.reply_to, cards=cards, data=data,
                   meta={"model": model.name, "seconds": round(seconds, 2), "calls": calls, "persona_version": me.version, **usage,
                         **({"errors": errors} if errors else {}), **({"action": step.action} if isinstance(step, Host) else {})})
    await _send(emit, "message", {"seq": msg.seq})
    return msg


async def play(scene, room: Room, cast: dict[str, Persona], host: Persona, model: ChatModel, ctx: tools.ToolContext,
               emit: Emit | None = None, should_stop: Callable[[], bool] | None = None) -> int:
    """把一场戏演完。返回产生了几条消息。should_stop 为真时（比如用户插话了）在两条消息之间停下。"""
    made = 0
    try:
        step = await scene.asend(None)
        while True:
            if should_stop and should_stop():
                await scene.aclose()
                break
            msg = await perform(step, room, cast, host, model, ctx, emit)
            made += 1 if msg else 0
            step = await scene.asend(msg)
    except StopAsyncIteration:
        pass
    return made
