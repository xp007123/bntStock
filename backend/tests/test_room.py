"""群聊：导演、演员、数据工具。全部用假模型，不联网。重点是“失败即台词”：任何一环出错，戏都能演下去。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sixiang.config import Settings
from sixiang.data.baseline_import import import_baseline
from sixiang.data.store import MarketStore
from sixiang.room import actor, personas, tools
from sixiang.room.director import Host, Roundtable, Speak
from sixiang.room.llm import FakeModel, Reply, ToolCall
from sixiang.room.state import Room

from .conftest import write_daily


@pytest.fixture
def ctx(tmp_path: Path) -> tools.ToolContext:
    src = tmp_path / "src"
    (src / "daily").mkdir(parents=True)
    dates = pd.bdate_range("2024-01-01", periods=600)
    rng = np.random.default_rng(5)
    for code, name in (("sh600519", "贵州茅台"), ("sz000001", "平安银行")):
        close = 20 * np.cumprod(1 + rng.normal(0.0005, .02, len(dates)))
        prev = np.r_[close[0], close[:-1]]
        write_daily(src / "daily" / f"{code}.csv", code, name,
                    [(d.strftime("%Y-%m-%d"), round(p * 1.001, 2), round(max(c, p) * 1.01, 2), round(min(c, p) * .99, 2), round(c, 2), round(p, 2))
                     for d, c, p in zip(dates, close, prev)])
    data = tmp_path / "data"
    import_baseline(src, data / "market", "v-test", workers=1, log=lambda *_: None)
    settings = Settings(data_dir=data, frontend_dist=tmp_path / "none")
    return tools.ToolContext(MarketStore(settings.market_dir), data / "research" / "jobs")


def make_room() -> tuple[Room, dict, personas.Persona]:
    cast = personas.all_personas(reload=True)
    return Room(topic={"kind": "stock", "code": "sh600519", "name": "贵州茅台"}, members=list(personas.DEFAULT_GUESTS), user_name="老王", brief="贵州茅台"), cast, personas.host()


def play(scene, room, cast, host, model, ctx) -> int:
    return asyncio.run(actor.play(scene, room, cast, host, model, ctx))


def test_persona_cards_load():
    cast = personas.all_personas(reload=True)
    assert {"xiaosi", "buffett", "yangjia", "soros", "serenity"} <= set(cast)
    assert personas.host().id == "xiaosi" and len(personas.guests()) >= 4
    for pid in personas.DEFAULT_GUESTS:
        pub = cast[pid].public()
        assert pub["name"] and pub["lens"] and len(pub["beliefs"]) >= 3 and pub["lines"] and pub["color"].startswith("#")
        assert all(r in cast for r in cast[pid].rivals)


def test_tools_never_raise(ctx):
    ok = tools.run(ctx, "stock_outlook", {"code": "茅台", "horizon": "21"})        # 名称、字符串参数都认
    assert ok.ok and ok.card["type"] == "outlook" and "贵州茅台" in ok.text
    assert tools.run(ctx, "stock_recent", {"code": "600519"}).ok
    assert tools.run(ctx, "option_outlook", {"code": "sh600519", "fee": 7.5}).card["fee"] == pytest.approx(0.075)   # 7.5 当成 7.5%
    for name, args in [("stock_outlook", {"code": "没有这只"}), ("stock_outlook", {}), ("没有这个工具", {}),
                       ("stock_financials", {"code": "sh600519"}), ("method_hits", {"code": "sh600519"}), ("market_outlook", {"index": "xx"})]:
        r = tools.run(ctx, name, args)
        assert isinstance(r.text, str) and r.text       # 不管成不成，都是一句话，不是异常


def test_tidy():
    assert actor.tidy("巴菲特：“这价格我再等等。”", "巴菲特") == "这价格我再等等。"
    assert actor.tidy("**第一句。**\n\n- 第二句。\n3. 第三句。\n第四句。", "x") == "第一句。\n第二句。\n第三句。"       # 去掉 Markdown，最多三条
    assert actor.tidy("12.3 倍市盈率，不贵。\n1. 第一点", "x") == "12.3 倍市盈率，不贵。\n第一点"      # 开头的小数不是列表记号
    long = actor.tidy("很长" * 60 + "。然后还有。", "x")
    assert len(long) <= actor.MAX_CHARS + 1


def test_opening_scene(ctx):
    room, cast, host = make_room()
    model = FakeModel(default="我的看法是这样。")
    made = play(Roundtable(cast).opening(room), room, cast, host, model, ctx)
    # 小四开场 + 四位各一条 + 小四拱火 + 被点的回应 + 对手回一句 + 小四收场
    assert made == 9 and [m.role for m in room.messages] == ["host", "guest", "guest", "guest", "guest", "host", "guest", "guest", "host"]
    assert [m.persona_id for m in room.messages[1:5]] == personas.DEFAULT_GUESTS
    poke, answer, back = room.messages[5], room.messages[6], room.messages[7]
    assert poke.meta["pair"] == [answer.persona_id, back.persona_id]
    assert answer.reply_to == poke.seq and back.reply_to == answer.seq
    # 接着聊：换一对没吵过的
    play(Roundtable(cast).more(room), room, cast, host, model, ctx)
    pairs = [frozenset(m.meta["pair"]) for m in room.messages if m.meta.get("pair")]
    assert len(pairs) == 2 and pairs[0] != pairs[1]
    # 每个人看到的提示词里有自己的人设和别人说过的话
    last = model.calls[-1]["messages"]
    assert last[0]["role"] == "system" and "小四" in last[0]["content"] and "导演悄悄话" in last[-1]["content"]


def test_tool_call_becomes_data_card(ctx):
    room, cast, host = make_room()
    model = FakeModel([Reply(tool_calls=[ToolCall("c1", "stock_outlook", '{"code": "sh600519"}')]), "我查了，不到一半。"])
    msg = asyncio.run(actor.perform(Speak("buffett", "说"), room, cast, host, model, ctx))
    assert msg.text == "我查了，不到一半。" and msg.cards[0]["type"] == "outlook" and msg.data and msg.meta["calls"] == 2
    assert model.calls[1]["messages"][-1]["role"] == "tool"


def test_failures_become_dialogue(ctx):
    """模型报错、说空话、乱调工具、参数不是 JSON：这一条要么照常说出来，要么悄悄跳过，绝不抛异常，戏接着演。"""
    room, cast, host = make_room()
    script = [
        "开场。",                                                             # 小四
        TimeoutError("模型超时"), TimeoutError("还是超时"),                      # 巴菲特：两次都失败 → 跳过
        Reply(tool_calls=[ToolCall("c1", "不存在的工具", "不是 JSON")]), "数据没取到，凭感觉说两句。",   # 养家：工具出错，照常说话
        "", "被催了一下才开口。",                                              # 索罗斯：第一次没说话，催一次
        Reply(tool_calls=[ToolCall("c2", "stock_outlook", '{"code": "sh600519"}')]),
        Reply(tool_calls=[ToolCall("c3", "stock_recent", '{"code": "sh600519"}')]), "查了两轮，说完了。",     # Serenity：查满两轮
    ]
    model = FakeModel(script, default="行。")
    made = play(Roundtable(cast).opening(room), room, cast, host, model, ctx)
    by = {m.persona_id: m for m in room.messages[:5]}
    assert "buffett" not in by                                              # 被跳过，没有留下报错消息
    assert by["yangjia"].text == "数据没取到，凭感觉说两句。" and not by["yangjia"].cards
    assert by["soros"].text == "被催了一下才开口。"
    assert by["serenity"].text == "查了两轮，说完了。" and len(by["serenity"].cards) == 2
    assert made == len(room.messages) >= 7 and room.messages[-1].role == "host"   # 戏演到了收场
    assert all(m.text for m in room.messages)


def test_everyone_fails_still_ends(ctx):
    room, cast, host = make_room()
    made = play(Roundtable(cast).opening(room), room, cast, host, FakeModel(default=""), ctx)
    assert made == 0 and room.messages == []          # 全程没人说得出话：安静地结束，不报错


def test_user_message_routing(ctx):
    room, cast, host = make_room()
    d = Roundtable(cast, FakeModel(["索罗斯"]))
    play(d.opening(room), room, cast, host, FakeModel(default="嗯。"), ctx)
    n = len(room.messages)
    # @ 了谁就谁回；只有一个人接话时，他的对手会插一句
    msg = room.add("user", "老王", "你怎么看？", meta={"mentions": ["yangjia"]})
    play(d.on_user(room, msg), room, cast, host, FakeModel(default="回你。"), ctx)
    replies = room.messages[n + 1:]
    assert replies[0].persona_id == "yangjia" and replies[0].reply_to == msg.seq
    assert len(replies) == 2 and replies[1].persona_id in cast["yangjia"].rivals and replies[1].reply_to == replies[0].seq
    # 没 @：话里提到名字就找他；都没有就问导演（假模型回“索罗斯”）；导演答非所问就退回上一个说话的嘉宾
    assert asyncio.run(d._who_answers(room, room.add("user", "老王", "巴菲特你服吗"))) == ["buffett"]
    assert asyncio.run(d._who_answers(room, room.add("user", "老王", "现在能买吗"))) == ["soros"]
    lost = Roundtable(cast, FakeModel(["不知道"]))
    assert asyncio.run(lost._who_answers(room, room.add("user", "老王", "现在能买吗"))) == [replies[1].persona_id]


def test_host_gets_no_tools(ctx):
    room, cast, host = make_room()
    model = FakeModel(default="开场。")
    asyncio.run(actor.perform(Host("open", "开场"), room, cast, host, model, ctx))
    asyncio.run(actor.perform(Speak("buffett", "说"), room, cast, host, model, ctx))
    assert model.calls[0]["tools"] is None and len(model.calls[1]["tools"]) == len(tools.REGISTRY)
