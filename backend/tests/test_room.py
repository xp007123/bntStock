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
    assert {"xiaosi", "buffett", "yangjia", "soros", "serenity", "munger", "taleb"} <= set(cast)
    assert all(p.bio for p in cast.values() if p.role == "guest")           # 每位嘉宾都有概要简介
    assert personas.host().id == "xiaosi" and len(personas.guests()) >= 4
    for pid in personas.DEFAULT_GUESTS:
        pub = cast[pid].public()
        assert pub["name"] and pub["lens"] and len(pub["beliefs"]) >= 3 and pub["lines"] and pub["color"].startswith("#")
        assert pub["hold"] and pub["ask"] and pub["never"] and pub["rivals"]          # 角色页人物卡上的短介绍
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
    new = items["template"].replace("id: new_persona", "id: fisher").replace("name: 新角色", "name: 费雪") + "\n这个人说话很直，喜欢反过来想问题，对蠢事毫不客气。\n"
    made = client.post("/api/admin/personas", json={"content": new}).json()
    assert made["id"] == "fisher" and not made["builtin"] and made["version"] == 1
    assert client.post("/api/admin/personas", json={"content": new}).status_code == 422       # 重名
    client.post("/api/admin/personas/fisher/settings", json={"in_default": True, "sort": 0})
    assert client.get("/api/personas").json()["default"][0] == "fisher"
    assert client.post("/api/admin/personas/fisher/use", json={"version": None}).status_code == 422    # 不是内置的，没有出厂设置

    # 试说一句：用草稿，不保存
    tried = client.post("/api/admin/personas/try", json={"content": new, "code": "茅台"}).json()
    assert tried["ok"] and tried["text"] == "我的看法是这样。" and tried["stock"] == "贵州茅台"


def test_minutes_quotes_real_lines(ctx):
    """纪要：每个人的那句话是他真说过的原话，数据是查到的原文；模型只挑哪一条、判断立场。"""
    from sixiang.room import minutes
    room, cast, _ = make_room()
    a, b = room.members[0], room.members[1]
    room.add("guest", cast[a].name, "这生意我看得懂。\n价格不便宜。", persona_id=a, data=["贵州茅台最近 20 天涨了 3.2%。"])
    room.add("user", "老王", "那到底怎么看")
    room.add("guest", cast[b].name, "情绪已经到头了。", persona_id=b)
    reply = ('好的：{"stances":[{"name":"%s","stance":"看多","quote":1},{"name":"%s","stance":"乱写","quote":1}],'
             '"split":"一个看生意，一个看情绪。","data":1}' % (cast[a].name, cast[b].name))
    card = minutes.build(room, cast, reply, {"asof": "2026-04-17", "close": 20.0})
    assert [(s["persona_id"], s["stance"], s["quote"], s["seq"]) for s in card["stances"]] == [
        (a, "看多", "这生意我看得懂。", 1), (b, None, "情绪已经到头了。", 3)]       # 立场不在三选一里就不标；引用别人的话不算数
    assert card["split"] == "一个看生意，一个看情绪。" and card["data"] == "贵州茅台最近 20 天涨了 3.2%。" and card["asof"] == "2026-04-17"
    # 模型答非所问、分歧那句带了数字：卡照样出，那些地方留空
    card = minutes.build(room, cast, '{"split":"一个说涨 30%，一个不信"}')
    assert [s["quote"] for s in card["stances"]] == ["价格不便宜。", "情绪已经到头了。"] and card["split"] is None
    assert minutes.build(room, cast, "模型罢工了")["stances"][0]["stance"] is None
    empty, cast2, _ = make_room()
    assert minutes.build(empty, cast2, "{}") is None and minutes.prompt(empty, cast2) is None
    assert "[1] " in minutes.prompt(room, cast)[1]["content"] and "(1) 贵州茅台最近" in minutes.prompt(room, cast)[1]["content"]

    # 回访：纪要那天到最新一根日线
    bars = ctx.store.daily("sh600519", adjust="none")["bars"]
    then = {"code": "sh600519", "asof": bars[-4]["date"], "close": bars[-4]["close"]}
    got = minutes.since(ctx.store, then)
    assert got["days"] == 3 and got["date"] == bars[-1]["date"] and got["ret"] == pytest.approx(bars[-1]["close"] / bars[-4]["close"] - 1, abs=1e-3)
    assert minutes.since(ctx.store, {"code": "sh600519", "asof": bars[-1]["date"]}) is None and minutes.since(ctx.store, {}) is None
    assert minutes.anchor(ctx.store, "sh600519") == {"asof": bars[-1]["date"], "close": bars[-1]["close"]}


def test_minutes_api(client: TestClient):
    rid = client.post("/api/rooms", json={"code": "sh600519"}).json()["id"]
    before = len(wait_idle(client, rid)["messages"])
    assert client.post(f"/api/rooms/{rid}/minutes").json() == {"ok": True}
    msgs = wait_idle(client, rid)["messages"]
    last = msgs[-1]
    assert len(msgs) == before + 1 and last["role"] == "host" and last["action"] == "minutes"
    card = last["cards"][0]
    assert card["type"] == "minutes" and card["name"] == "贵州茅台" and len(card["stances"]) == len(personas.DEFAULT_GUESTS)
    assert all(s["quote"] for s in card["stances"]) and card["asof"] and card["since"] is None      # 假模型不出 JSON：卡照样有


def test_limit_up_and_sector_tools(ctx):
    """两个新工具：涨停之后怎么样、在行业里排第几。数字和日线对得上。"""
    r = tools.run(ctx, "limit_up_history", {"code": "贵州茅台"})
    assert r.ok and r.card["type"] == "limitup" and r.card["days"] == 600 and "涨停过" in r.text
    bars = pd.DataFrame(ctx.store.daily("sh600519", adjust="none", limit=750)["bars"])
    want = int((bars.close >= (bars.prev_close * 1.1 * 100 + 0.5).astype(int) / 100 - 0.001).sum())
    assert r.card["n"] == want and (r.card["next_n"] <= want)
    s = tools.run(ctx, "sector_today", {"code": "sh600519"})
    assert (s.ok and s.card["rank"] >= 1 and s.card["n"] >= 1) or "行业" in s.text       # 测试数据里没有行业分类时回一句话，不报错
    assert {"limit_up_history", "sector_today"} <= {t["function"]["name"] for t in tools.schemas()}
    cast = personas.all_personas(reload=True)
    assert {"lynch", "livermore", "templeton"} <= set(cast)
    for pid in ("lynch", "livermore", "templeton"):
        assert all(t in tools.REGISTRY for t in cast[pid].tools) and all(x in cast for x in cast[pid].rivals) and cast[pid].public()["lines"]


def test_persona_recent_lines(client: TestClient):
    """角色个人页：他最近在我的群里说过的话；别人的群不算。"""
    rid = client.post("/api/rooms", json={"code": "sh600519", "members": ["yangjia", "lynch"]}).json()["id"]
    room = wait_idle(client, rid)
    assert room["members"] == ["yangjia", "lynch"]
    said = client.get("/api/personas/lynch/recent").json()["items"]
    assert said and all(m["room_id"] == rid and m["title"] == "贵州茅台" and m["text"] for m in said)
    assert client.get("/api/personas/buffett/recent").json()["items"] == []
    client.app.state.auth.register("路人戊", "13711116666", "abcdef", "abcdef", status="active")
    other = TestClient(client.app)
    other.post("/api/auth/login", json={"account": "路人戊", "password": "abcdef"})
    assert other.get("/api/personas/lynch/recent").json()["items"] == []


def test_deep_chat(client: TestClient):
    """一对一深聊：只有装了深聊包的角色能开；提示词里是完整版的思维方式和深聊规矩；能说得比群聊长；没有主持人。"""
    from sixiang.room import prompts, skills
    sk = skills.load("buffett", reload=True)
    assert sk and "护城河" in sk.body and not sk.body.startswith("---") and "按需资源" not in sk.body and "research" in sk.references
    assert skills.load("yangjia") is None and skills.load("../etc") is None
    assert set(skills.installed()) == {"buffett", "munger", "taleb", "livermore", "soros", "lynch"}
    for pid in skills.installed():
        s = skills.load(pid, reload=True)
        assert s.source["license"] == "MIT" and s.source["version"] and s.source["repo"].startswith("https://github.com/") and len(s.body) > 3000
        assert s.style == ("framework" if pid in ("livermore", "soros", "lynch") else "persona")
    fw = skills.load("livermore")
    assert "Pivotal Point" in fw.body and "Podcasts" not in fw.body and "Playbooks" not in fw.body and not fw.body.startswith("---")
    assert skills.read_reference(sk, "research") and skills.read_reference(sk, "nope") == "没有这份资料。"

    listing = client.get("/api/personas").json()["items"]
    assert {p["id"]: p["deep"] for p in listing}["buffett"] is True and {p["id"]: p["deep"] for p in listing}["yangjia"] is False
    assert sorted(p["id"] for p in listing if p["deep"]) == ["buffett", "livermore", "lynch", "munger", "soros", "taleb"]
    assert client.post("/api/rooms", json={"code": "sh600519", "members": ["yangjia"], "mode": "deep"}).status_code == 422
    assert client.post("/api/rooms", json={"code": "sh600519", "members": ["buffett", "soros"], "mode": "deep"}).status_code == 422
    assert client.post("/api/rooms", json={"code": "sh600519", "members": ["buffett"], "mode": "x"}).status_code == 422

    long = "这门生意我愿意多看两眼。" * 12          # 群聊里会被截到 70 字，深聊不会
    model = FakeModel(default=long + "\n第二段。\n第三段。\n第四段。")
    client.app.state.rooms.model = model
    rid = client.post("/api/rooms", json={"code": "sh600519", "members": ["buffett"], "mode": "deep"}).json()["id"]
    room = wait_idle(client, rid)
    assert room["topic"]["mode"] == "deep" and room["members"] == ["buffett"]
    msgs = room["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "guest" and msgs[0]["persona_id"] == "buffett"      # 没有主持人开场
    assert msgs[0]["text"].split("\n")[0] == long and len(msgs[0]["text"].split("\n")) == 4
    call = model.calls[0]
    system = call["messages"][0]["content"]
    assert system.startswith(prompts.DEEP_RULES) and "核心思想模型" in system and "# 今天聊的" in system and "群里还有" not in system
    assert system.index("核心思想模型") < system.index("# 今天聊的")                                   # 不变的在前，会变的在后
    assert "read_reference" in {t["function"]["name"] for t in call["tools"]}

    client.post(f"/api/rooms/{rid}/say", json={"text": "最坏会怎样"})
    msgs = wait_idle(client, rid)["messages"]
    assert [m["role"] for m in msgs] == ["guest", "user", "guest"] and msgs[2]["reply_to"] == 2
    client.post(f"/api/rooms/{rid}/continue")
    assert [m["role"] for m in wait_idle(client, rid)["messages"]] == ["guest", "user", "guest", "guest"]
    assert client.post(f"/api/rooms/{rid}/members", json={"add": "soros"}).status_code == 422          # 一对一，不能拉人

    # 群聊不受影响：同一位角色在群里还是精简卡、短句
    model.calls.clear()
    rid2 = client.post("/api/rooms", json={"code": "sh600519", "members": ["buffett"]}).json()["id"]
    g = wait_idle(client, rid2)["messages"]
    guest = next(m for m in g if m["role"] == "guest")
    assert len(guest["text"].split("\n")[0]) <= 71 and "mode" not in client.get(f"/api/rooms/{rid2}").json()["topic"]
    assert all("核心思想模型" not in c["messages"][0]["content"] for c in model.calls)


def test_framework_pack_and_admin_deep(client: TestClient):
    """方法型的深聊包：口吻用我们的角色卡，方法用上游的框架。管理端能看、能关、能试聊。"""
    from sixiang.room import prompts
    model = FakeModel(default="价格自己会说话。\n等它站回前高再说。")
    client.app.state.rooms.model = model
    rid = client.post("/api/rooms", json={"code": "sh600519", "members": ["livermore"], "mode": "deep"}).json()["id"]
    wait_idle(client, rid)
    system = model.calls[0]["messages"][0]["content"]
    assert system.startswith(prompts.DEEP_RULES) and "# 你是谁、怎么说话" in system and "破产过四次" in system        # 我们的角色卡
    assert "# 你的方法" in system and "Line of Least Resistance" in system and "Reading List" not in system          # 上游的框架

    rows = {p["id"]: p for p in client.get("/api/admin/personas").json()["items"]}
    assert rows["yangjia"]["deep_pack"] is None and rows["livermore"]["deep_pack"]["style"] == "framework"
    assert rows["munger"]["deep_pack"]["enabled"] and rows["munger"]["deep_pack"]["source"]["license"] == "MIT"
    pack = client.get("/api/admin/personas/munger/deep").json()
    assert "反过来想" in pack["body"] and {r["name"] for r in pack["references"]} >= {"25-biases", "casebook", "voice"}
    assert client.get("/api/admin/personas/yangjia/deep").status_code == 404

    # 关掉：用户那边不再显示能深聊，也开不了；已经开始的那场还能接着聊
    assert client.post("/api/admin/personas/livermore/deep", json={"enabled": False}).json()["enabled"] is False
    assert {p["id"]: p["deep"] for p in client.get("/api/personas").json()["items"]}["livermore"] is False
    assert client.post("/api/rooms", json={"code": "sh600519", "members": ["livermore"], "mode": "deep"}).status_code == 422
    client.post(f"/api/rooms/{rid}/say", json={"text": "接着说"})
    assert wait_idle(client, rid)["messages"][-1]["persona_id"] == "livermore"
    assert client.post("/api/admin/personas/livermore/deep", json={"enabled": True}).json()["enabled"] is True
    assert client.post("/api/admin/personas/yangjia/deep", json={"enabled": True}).status_code == 404

    tried = client.post("/api/admin/personas/taleb/deep/try", json={"code": "sh600519", "say": "最坏会怎样"}).json()
    assert tried["ok"] and [t["role"] for t in tried["turns"]] == ["guest", "user", "guest"] and tried["usage"]["calls"] >= 2


def test_deep_drops_leading_disclaimer():
    """深聊包要求先声明“不是本人”的，开头那句去掉；正文里正常提到“本人”的不动。"""
    d = actor.drop_disclaimer
    assert d("下面是按查理·芒格公开的言行提炼出来的视角，不是他本人。\n先说我看到的这门生意。") == "先说我看到的这门生意。"
    assert d("先说一句：下面是按公开言行提炼的视角，不是他本人。先说生意。") == "先说生意。"
    assert d("我以巴菲特视角和你聊，基于公开言论推断，非本人意见。\n这门生意我看得懂。") == "这门生意我看得懂。"
    assert d("这门生意我看得懂。创始人本人还在一线，这点我喜欢。") == "这门生意我看得懂。创始人本人还在一线，这点我喜欢。"
    assert d("") == ""
