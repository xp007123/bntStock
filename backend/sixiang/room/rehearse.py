"""彩排：在命令行里用真模型跑一场，直接把对话打印出来。调角色卡和群规用，不用开页面。

    python -m sixiang.room.rehearse --code sz002594
    python -m sixiang.room.rehearse --code 贵州茅台 --say "我 1700 买的，现在怎么办" --more 1
    python -m sixiang.room.rehearse --code sz300750 --members buffett,serenity

--say  开场演完后，替用户说一句话（可以带 @名字）
--more 再“接着聊”几场
--quiet 只打印对话，不打印数据和统计
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

from ..config import load_settings
from ..data.store import MarketStore
from . import actor, llm, personas, tools
from .director import Roundtable
from .state import Room


def _print(room: Room, since: int, quiet: bool) -> None:
    for m in room.messages[since:]:
        quoted = room.by_seq(m.reply_to)
        head = f"{m.name}" + (f" ↩ {quoted.name}" if quoted and quoted.name != m.name else "")
        print(f"\n{head}：" + m.text.replace("\n", "\n" + " " * (len(head) * 2 + 2)))
        if not quiet:
            for d in m.data:
                print(f"    〔数据〕{d}")
            if m.meta.get("errors"):
                print(f"    〔出过错〕{m.meta['errors']}")


async def run(args) -> None:
    settings = load_settings()      # 先读 .env，密钥在里面
    model = llm.from_env()
    if model is None:
        sys.exit("没有配置 SIXIANG_LLM_API_KEY（仓库根目录的 .env）")
    ctx = tools.ToolContext(MarketStore(settings.market_dir), settings.data_dir / "research" / "jobs")
    cast = personas.all_personas(reload=True)
    host = personas.host()
    members = [m for m in (args.members.split(",") if args.members else personas.DEFAULT_GUESTS) if m in cast]

    code = tools.resolve(ctx, args.code)
    recent = tools.run(ctx, "stock_recent", {"code": code})
    name = recent.card["name"] if recent.card else code
    room = Room(topic={"kind": "stock", "code": code, "name": name}, members=members, user_name=args.user,
                brief=f"股票：{name}（{code}）。{recent.text}")
    director = Roundtable(cast, model)
    print(f"━━ 彩排：{name} · 模型 {model.name} · 嘉宾 {'、'.join(cast[m].name for m in members)} ━━")
    if not args.quiet:
        print(f"〔话题简报〕{room.brief}")

    t0 = time.monotonic()
    shown = 0

    async def act(scene, title: str) -> None:
        nonlocal shown
        print(f"\n── {title} ──")
        await actor.play(scene, room, cast, host, model, ctx)
        _print(room, shown, args.quiet)
        shown = len(room.messages)

    await act(director.opening(room), "开场")
    if args.say:
        mentions = [p for p in members if "@" + cast[p].name in args.say]
        msg = room.add("user", args.user, args.say.replace("@", ""), meta={"mentions": mentions})
        shown = len(room.messages)
        print(f"\n{args.user}：{msg.text}")
        await act(director.on_user(room, msg), "用户说话之后")
    for i in range(args.more):
        await act(director.more(room), f"接着聊 {i + 1}")

    said = [m for m in room.messages if m.role in ("host", "guest")]
    tin, tout = sum(m.meta.get("prompt_tokens", 0) for m in said), sum(m.meta.get("completion_tokens", 0) for m in said)
    print(f"\n━━ 共 {len(said)} 条发言，模型调用 {sum(m.meta.get('calls', 0) for m in said)} 次，"
          f"输入 {tin:,} token，输出 {tout:,} token，用时 {time.monotonic() - t0:.0f} 秒；"
          f"查了 {sum(len(m.data) for m in said)} 次数据，出错 {sum(len(m.meta.get('errors', [])) for m in said)} 次 ━━")


def main() -> None:
    ap = argparse.ArgumentParser(description="群聊彩排")
    ap.add_argument("--code", required=True, help="股票代码或名称")
    ap.add_argument("--members", default="", help="嘉宾 id，逗号分隔；默认四位都来")
    ap.add_argument("--say", default="", help="开场后替用户说的一句话")
    ap.add_argument("--more", type=int, default=0, help="再接着聊几场")
    ap.add_argument("--user", default="老王", help="用户在群里的名字")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
