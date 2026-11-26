"""选股名单：问财结果的解析、存取、用日线算出来的表现、接口。全部不联网。"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sixiang.api.app import create_app
from sixiang.config import Settings
from sixiang.data.baseline_import import import_baseline
from sixiang.picks import service as pick_service
from sixiang.picks.wencai import parse_sjm, sjm_query
from sixiang.room import tools

from .conftest import login_as_admin, write_daily

DAYS = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"]


@pytest.fixture
def app(tmp_path: Path):
    src = tmp_path / "src"
    (src / "daily").mkdir(parents=True)
    # 甲：18 日高开 5%，收盘封住涨停（昨收 10 → 涨停 11）；19 日低开
    write_daily(src / "daily" / "sz000001.csv", "sz000001", "甲股份", [
        (DAYS[0], 10, 10.1, 9.9, 10.0, 10.0), (DAYS[1], 10, 10.1, 9.9, 10.0, 10.0),
        (DAYS[2], 10.5, 11.0, 10.4, 11.0, 10.0), (DAYS[3], 10.8, 11.2, 10.7, 11.1, 11.0)])
    # 乙：18 日高开 4%，摸到涨停后回落，收盘比开盘低
    write_daily(src / "daily" / "sh600000.csv", "sh600000", "乙股份", [
        (DAYS[0], 20, 20.2, 19.8, 20.0, 20.0), (DAYS[1], 20, 20.2, 19.8, 20.0, 20.0),
        (DAYS[2], 20.8, 22.0, 20.2, 20.4, 20.0), (DAYS[3], 20.4, 20.6, 20.0, 20.2, 20.4)])
    # 丙：不在名单里，18 日平开平收（对照组里的一只）
    write_daily(src / "daily" / "sh600519.csv", "sh600519", "丙股份", [
        (DAYS[0], 30, 30.3, 29.7, 30.0, 30.0), (DAYS[1], 30, 30.3, 29.7, 30.0, 30.0),
        (DAYS[2], 30, 30.3, 29.7, 30.0, 30.0), (DAYS[3], 30, 30.3, 29.7, 30.0, 30.0)])
    data = tmp_path / "data"
    import_baseline(src, data / "market", "v-test", workers=1, log=lambda *_: None)
    return create_app(Settings(data_dir=data, frontend_dist=tmp_path / "none"))


def table(day: str, prev: str) -> dict:
    d, p = day.replace("-", ""), prev.replace("-", "")
    return {"股票代码": ["600000.SH", "000001.SZ"], "股票简称": ["乙股份", "甲股份"], "上市板块": ["主板", "主板"],
            f"分时涨跌幅:前复权[{d} 09:25]": ["4.0", 5.0], f"涨停价[{d}]": [22.0, 11.0], f"涨停价[{p}]": [22.0, 11.0],
            f"收盘价:不复权[{p}]": [20.0, 10.0], f"换手率[{p}]": ["1.2", "2.3"], f"总市值[{p}]": [5e9, 3e9]}


def test_query_and_parse():
    q = sjm_query(dt.date(2026, 11, 18), dt.date(2026, 11, 17), dt.date(2026, 11, 16))
    assert "2026年11月18日09:25分未涨停且涨幅最高" in q and "2026年11月17日换手率小于5%" in q and "2026年11月16日成交量两倍" in q
    rows = parse_sjm(table(DAYS[2], DAYS[1]), dt.date(2026, 11, 18), dt.date(2026, 11, 17))
    assert [(r["rank"], r["code"]) for r in rows] == [(1, "sz000001"), (2, "sh600000")]      # 按竞价涨幅重排
    assert rows[0]["auction_pct"] == 5.0 and rows[0]["limit_price"] == 11.0 and rows[1]["prev_turnover"] == 1.2
    assert parse_sjm({}, dt.date(2026, 11, 18), dt.date(2026, 11, 17)) == []


def test_day_and_stats(app):
    svc = app.state.picks
    svc.store.save("sjm", DAYS[2], parse_sjm(table(DAYS[2], DAYS[1]), dt.date(2026, 11, 18), dt.date(2026, 11, 17)))
    day = svc.day("sjm")
    assert day["date"] == DAYS[2] and day["settled"] and len(day["items"]) == 2
    a, b = day["items"]
    assert a["code"] == "sz000001" and a["sealed"] and a["touched"] and a["auction_pct"] == pytest.approx(0.05)
    assert a["intraday"] == pytest.approx(11.0 / 10.5 - 1) and a["next_open_ret"] == pytest.approx(10.8 / 10.5 - 1)
    assert b["touched"] and not b["sealed"] and b["intraday"] < 0

    s = svc.summary("sjm")
    assert s["range"] == {"start": DAYS[2], "end": DAYS[2], "days": 1, "n": 2}
    assert s["overall"]["sealed_rate"] == 0.5 and s["overall"]["touched_rate"] == 1.0 and s["overall"]["intraday_win"] == 0.5
    assert s["per_day"]["any_sealed_rate"] == 1.0
    assert s["baseline"]["market"]["n"] == 3 and s["baseline"]["market"]["sealed_rate"] == pytest.approx(1 / 3)
    assert s["baseline"]["same_gap"] is None          # 当天没有别的同样高开的股票
    assert [x["label"] for x in s["by_rank"]] == ["第 1 名", "第 2–3 名"]


def test_unsettled_day_and_cache(app):
    """行情还没到的那天：名单照常给，结果留空；之后补了别的天，统计跟着变。"""
    svc = app.state.picks
    svc.store.save("sjm", "2026-11-20", [{"code": "sz000001", "name": "甲股份", "rank": 1, "auction_pct": 3.0, "limit_price": 12.2, "board": "主板"}])
    day = svc.day("sjm")
    assert day["date"] == "2026-11-20" and not day["settled"] and day["items"][0]["sealed"] is None and day["items"][0]["day_pct"] is None
    assert svc.summary("sjm")["range"] is None
    svc.store.save("sjm", DAYS[2], parse_sjm(table(DAYS[2], DAYS[1]), dt.date(2026, 11, 18), dt.date(2026, 11, 17)))
    assert svc.summary("sjm")["range"]["n"] == 2
    assert svc.day("sjm", DAYS[2])["settled"]


def test_fetch_skips_non_trading_day(app, monkeypatch):
    """问财给不出 09:25 的涨幅（不是交易日，或者竞价还没结束）时，不存名单。"""
    svc = app.state.picks
    monkeypatch.setattr(pick_service, "recent_trade_days", lambda client, day: [dt.date(2026, 11, 17), dt.date(2026, 11, 18)])
    empty = {"股票代码": ["000001.SZ"], "股票简称": ["甲股份"]}
    monkeypatch.setattr(pick_service, "ask", lambda client, q: empty)
    assert svc.fetch("sjm", dt.date(2026, 11, 19), client=object()) == 0 and svc.store.days("sjm") == {}
    monkeypatch.setattr(pick_service, "ask", lambda client, q: table("2026-11-19", DAYS[2]))
    assert svc.fetch("sjm", dt.date(2026, 11, 19), client=object()) == 2 and svc.store.days("sjm") == {"2026-11-19": 2}


def test_api_and_room_tool(app):
    svc = app.state.picks
    svc.store.save("sjm", DAYS[2], parse_sjm(table(DAYS[2], DAYS[1]), dt.date(2026, 11, 18), dt.date(2026, 11, 17)))
    c = TestClient(app)
    assert c.get("/api/picks").status_code == 401
    login_as_admin(c)
    listed = c.get("/api/picks").json()["items"][0]
    assert listed["name"] == "竞价先锋" and listed["alias"] == "三角猫" and listed["headline"]["sealed_rate"] == 0.5
    assert c.get("/api/picks/sjm", params={"date": DAYS[2]}).json()["items"][0]["name"] == "甲股份"
    assert c.get("/api/picks/sjm/stats").json()["overall"]["n"] == 2
    assert c.get("/api/picks/nope").status_code == 404 and c.get("/api/picks/sjm", params={"date": "x"}).status_code == 422
    assert c.get("/api/picks/stock/sz000001").json()["pick"]["rank"] == 1
    assert c.get("/api/picks/stock/sh600519").json()["pick"] is None

    ctx = tools.ToolContext(app.state.market, None, picks=svc)
    r = tools.run(ctx, "pick_list", {"code": "sz000001"})
    assert r.ok and "竞价先锋" in r.text and "第 1 名" in r.text and "50.0%" in r.text and r.card["hit"]["rank"] == 1
    assert "不在" in tools.run(ctx, "pick_list", {"code": "sh600519"}).text
    assert not tools.run(tools.ToolContext(app.state.market, None), "pick_list", {"code": "sz000001"}).ok


def test_report_and_highlights(app):
    """战报讲当天最亮的那件事；没收盘只给名单；数字都来自当天行情。"""
    svc = app.state.picks
    svc.store.save("sjm", DAYS[2], parse_sjm(table(DAYS[2], DAYS[1]), dt.date(2026, 11, 18), dt.date(2026, 11, 17)))
    r = svc.report("sjm")
    assert r["mode"] == "result" and r["title"] == "2 只里 1 只封住涨停" and r["big"] == {"num": "1", "unit": "只", "label": "封住涨停"}
    assert "另有 1 只盘中摸到过涨停" in r["sub"]
    assert [(x["name"], x["tag"]) for x in r["stars"]] == [("甲股份", "封板"), ("乙股份", "摸过涨停")]
    assert r["stars"][0]["value"] == pytest.approx(0.1) and "50%" in r["facts"][0]
    hl = svc.highlights("sjm")
    assert hl[0]["value"] == 0.5 and "33.3%" in hl[0]["note"] and len(hl) == 3

    def row(code, name, rank):
        return {"code": code, "name": name, "rank": rank, "auction_pct": 1.0, "limit_price": 99.0, "board": "主板"}

    # 没封板也没摸板的一天：讲涨得最多的那只
    svc.store.save("sjm", DAYS[3], [row("sz000001", "甲股份", 1), row("sh600000", "乙股份", 2)])
    r = svc.report("sjm", DAYS[3])
    assert r["big"]["label"] == "甲股份 当天涨幅" and r["big"]["num"] == "+0.9" and [x["name"] for x in r["stars"]] == ["甲股份"]

    # 行情还没到的一天：只有名单
    svc.store.save("sjm", "2026-11-20", [row("sz000001", "甲股份", 1)])
    r = svc.report("sjm")
    assert r["mode"] == "list" and r["big"] is None and r["stars"][0]["value"] == pytest.approx(0.01) and r["value_label"] == "竞价涨幅"

    c = TestClient(app)
    login_as_admin(c)
    listed = c.get("/api/picks").json()["items"][0]
    assert listed["latest"]["date"] == "2026-11-20" and listed["highlights"][0]["label"] == "当天封住涨停的"
    assert c.get("/api/picks/sjm/report", params={"date": DAYS[2]}).json()["title"] == "2 只里 1 只封住涨停"
    assert c.get("/api/picks/nope/report").status_code == 404
    # 筛选条件是平台自己的东西，任何接口都不带出去
    for path in ("/api/picks", "/api/picks/sjm", "/api/picks/sjm/stats", "/api/picks/sjm/report"):
        assert "rules" not in c.get(path).text and "换手" not in c.get(path).text


def test_today_list_gets_live_quotes(app, monkeypatch):
    """今天的名单在收盘行情到之前：挂实时行情，并标出此刻是不是封着板。取不到实时就原样返回。"""
    from sixiang.data import mcp
    svc = app.state.picks
    today = dt.datetime.now(pick_service.CN_TZ).date().isoformat()
    svc.store.save("sjm", today, [{"code": "sz000001", "name": "甲股份", "rank": 1, "auction_pct": 3.0, "limit_price": 12.2, "board": "主板"},
                                  {"code": "sh600000", "name": "乙股份", "rank": 2, "auction_pct": 2.0, "limit_price": 22.0, "board": "主板"}])
    c = TestClient(app)
    login_as_admin(c)
    assert "live" not in c.get("/api/picks/sjm").json()["items"][0]            # 没接实时行情：照旧
    monkeypatch.setattr(mcp, "quotes", lambda codes, ttl=8: {
        "sz000001": {"latest": 12.2, "change": 0.1, "high": 12.2, "time": "2026-11-26 10:30:00"},
        "sh600000": {"latest": 20.5, "change": 0.02, "high": 22.0, "time": "2026-11-26 10:30:03"}})
    day = c.get("/api/picks/sjm").json()
    a, b = day["items"]
    assert a["live"]["sealed"] and a["live"]["touched"] and not b["live"]["sealed"] and b["live"]["touched"] and day["live_time"] == "2026-11-26 10:30:03"
    assert a["sealed"] is None                                                   # 正式结果还是等收盘行情
    assert "live" not in c.get("/api/picks/sjm", params={"date": DAYS[2]}).json().get("items", [{}])[0] if svc.store.days("sjm").get(DAYS[2]) else True
