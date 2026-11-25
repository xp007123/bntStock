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


# ---------------------------------------------------------------- 接口、运行器、角色管理

import time

from fastapi.testclient import TestClient

from sixiang.api.app import create_app
from sixiang.room.registry import PersonaError, PersonaRegistry

from .conftest import login_as_admin


@pytest.fixture
def client(tmp_path: Path, ctx):
    """ctx 已经在 tmp_path/data 下建好了行情；这里起一个应用，模型换成假的。"""
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none"))
    app.state.rooms.model = FakeModel(default="我的看法是这样。")
    with TestClient(app) as c:          # with：让后台任务所在的事件循环一直活着
        login_as_admin(c)
        yield c


def wait_idle(client: TestClient, rid: int) -> dict:
    for _ in range(200):
        room = client.get(f"/api/rooms/{rid}").json()
        if not room["playing"]:
            return room
        time.sleep(.05)
    raise AssertionError("这场戏一直没演完")


def test_room_api_flow(client: TestClient):
    listing = client.get("/api/personas").json()
    assert listing["available"] and listing["host"]["id"] == "xiaosi" and listing["default"] == personas.DEFAULT_GUESTS
    assert client.post("/api/rooms", json={"code": "没有这只"}).status_code == 422
    rid = client.post("/api/rooms", json={"code": "茅台"}).json()["id"]
    room = wait_idle(client, rid)
    assert room["title"] == "贵州茅台" and room["status"] == "idle" and "brief" not in room["topic"]
    msgs = room["messages"]
    assert len(msgs) == 9 and [m["seq"] for m in msgs] == list(range(1, 10)) and msgs[0]["action"] == "open"
    assert "prompt_tokens" not in str(msgs)                                   # 内部信息不给前端

    # 用户 @ 人说话：他先回，他的对手再插一句
    assert client.post(f"/api/rooms/{rid}/say", json={"text": "@索罗斯 现在怎么想"}).json() == {"ok": True}
    msgs = wait_idle(client, rid)["messages"]
    assert msgs[9]["role"] == "user" and msgs[9]["text"] == "索罗斯 现在怎么想"
    assert msgs[10]["persona_id"] == "soros" and msgs[10]["reply_to"] == 10 and len(msgs) == 12

    # 接着聊；拉人踢人
    client.post(f"/api/rooms/{rid}/continue")
    assert len(wait_idle(client, rid)["messages"]) == 16
    got = client.post(f"/api/rooms/{rid}/members", json={"remove": "serenity"}).json()["members"]
    assert "serenity" not in got
    room = wait_idle(client, rid)
    assert room["members"] == got and room["messages"][-1]["role"] == "system" and "请出" in room["messages"][-1]["text"]
    # 断线续传：只要某条之后的
    after = client.get(f"/api/rooms/{rid}").json()["messages"][-3]["seq"]
    assert [m["seq"] for m in client.app.state.rooms.store.messages(rid, after)] == [after + 1, after + 2]

    assert client.get("/api/rooms").json()["items"][0]["id"] == rid
    # 别人看不到、说不了话
    client.app.state.auth.register("路人丁", "13711115555", "abcdef", "abcdef", status="active")
    other = TestClient(client.app)
    other.post("/api/auth/login", json={"account": "路人丁", "password": "abcdef"})
    assert other.get(f"/api/rooms/{rid}").status_code == 404 and other.post(f"/api/rooms/{rid}/say", json={"text": "嗨"}).status_code == 404
    assert other.get("/api/admin/personas").status_code == 403


def test_daily_limit_is_a_line_not_an_error(client: TestClient):
    client.app.state.rooms.daily_limit = 0
    rid = client.post("/api/rooms", json={"code": "sh600519"}).json()["id"]
    msgs = wait_idle(client, rid)["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "host" and msgs[0]["action"] == "limit"


def test_model_down_room_stays_quiet(client: TestClient):
    client.app.state.rooms.model = FakeModel(default="")       # 模型一句话都说不出来
    rid = client.post("/api/rooms", json={"code": "sh600519"}).json()["id"]
    room = wait_idle(client, rid)
    # 没有报错：小四说一句固定的话，告诉用户过会儿再试
    assert [(m["role"], m["action"]) for m in room["messages"]] == [("host", "quiet")] and room["status"] == "idle"
    client.app.state.rooms.model = None
    assert client.get("/api/personas").json()["available"] is False
    assert client.post("/api/rooms", json={"code": "sh600519"}).status_code == 422


def test_persona_admin(client: TestClient):
    items = client.get("/api/admin/personas").json()
    assert {p["id"] for p in items["items"]} >= {"xiaosi", "buffett"} and items["tools"] and "id: new_persona" in items["template"]
    d = client.get("/api/admin/personas/buffett").json()
    assert d["builtin"] and not d["custom"] and d["versions"] == [] and d["content"].startswith("---")

    # 改人设：存成新的一版，立刻生效
    edited = d["content"].replace("好公司也要好价格", "价格是你付的，价值是你得的")
    saved = client.post("/api/admin/personas/buffett/versions", json={"content": edited, "note": "换了口头禅"}).json()
    assert saved["custom"] and saved["version"] == d["version"] + 1 and saved["tagline"] == "价格是你付的，价值是你得的"
    assert saved["versions"][0]["note"] == "换了口头禅"
    assert next(p for p in client.get("/api/personas").json()["items"] if p["id"] == "buffett")["tagline"] == "价格是你付的，价值是你得的"
    # 回到出厂设置，再切回刚才那一版
    assert client.post("/api/admin/personas/buffett/use", json={"version": None}).json()["tagline"] == "好公司也要好价格"
    assert client.post("/api/admin/personas/buffett/use", json={"version": saved["version"]}).json()["custom"]
    assert "价格是你付的" in client.get(f"/api/admin/personas/buffett/versions/{saved['version']}").json()["content"]
    assert "好公司也要好价格" in client.get("/api/admin/personas/buffett/versions/0").json()["content"]

    # 写坏的卡片存不进去；id 不能改
    assert client.post("/api/admin/personas/buffett/versions", json={"content": "没有头部的一段话，但是够长够长够长够长够长"}).status_code == 422
    assert client.post("/api/admin/personas/buffett/versions", json={"content": edited.replace("id: buffett", "id: someone")}).status_code == 422

    # 停用：不再出现在角色列表和默认成员里；主持人不能停用
    client.post("/api/admin/personas/serenity/settings", json={"enabled": False})
    pub = client.get("/api/personas").json()
    assert "serenity" not in [p["id"] for p in pub["items"]] and "serenity" not in pub["default"]
    assert client.post("/api/admin/personas/xiaosi/settings", json={"enabled": False}).status_code == 422
    rid = client.post("/api/rooms", json={"code": "sh600519"}).json()["id"]
    assert "serenity" not in wait_idle(client, rid)["members"]

    # 新建一个角色，设为默认进群、排第一个
    new = items["template"].replace("id: new_persona", "id: munger").replace("name: 新角色", "name: 芒格") + "\n这个人说话很直，喜欢反过来想问题，对蠢事毫不客气。\n"
    made = client.post("/api/admin/personas", json={"content": new}).json()
    assert made["id"] == "munger" and not made["builtin"] and made["version"] == 1
    assert client.post("/api/admin/personas", json={"content": new}).status_code == 422       # 重名
    client.post("/api/admin/personas/munger/settings", json={"in_default": True, "sort": 0})
    assert client.get("/api/personas").json()["default"][0] == "munger"
    assert client.post("/api/admin/personas/munger/use", json={"version": None}).status_code == 422    # 不是内置的，没有出厂设置

    # 试说一句：用草稿，不保存
    tried = client.post("/api/admin/personas/try", json={"content": new, "code": "茅台"}).json()
    assert tried["ok"] and tried["text"] == "我的看法是这样。" and tried["stock"] == "贵州茅台"
