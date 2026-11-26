from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sixiang.analysis.distribution import NotEnoughHistory, analyze, load, outcome
from sixiang.analysis.narrative import horizon_text, tens
from sixiang.api.app import create_app
from sixiang.config import Settings
from sixiang.data.baseline_import import import_baseline
from sixiang.judgments import estimate_due

from .conftest import login_as_admin, write_daily


@pytest.fixture
def app(tmp_path: Path):
    src = tmp_path / "src"
    (src / "daily").mkdir(parents=True)
    dates = pd.bdate_range("2024-01-01", periods=600)
    rng = np.random.default_rng(11)
    for code, name in (("sh600000", "浦发银行"), ("sz000001", "平安银行"), ("sh600519", "贵州茅台")):
        close = 20 * np.cumprod(1 + rng.normal(0.0005, .02, len(dates)))
        prev = np.r_[close[0], close[:-1]]
        rows = [(d.strftime("%Y-%m-%d"), round(p * 1.001, 2), round(max(c, p) * 1.01, 2), round(min(c, p) * .99, 2), round(c, 2), round(p, 2))
                for d, c, p in zip(dates, close, prev)]
        write_daily(src / "daily" / f"{code}.csv", code, name, rows)
    (src / "index").mkdir()
    idx = 3000 * np.cumprod(1 + rng.normal(0.0003, .012, len(dates)))
    lines = ["candle_end_time,open,high,low,close,amount,volume,index_code"]
    lines += [f"{d:%Y-%m-%d},{c:.2f},{c * 1.01:.2f},{c * .99:.2f},{c:.2f},1e11,1e8,sh000001" for d, c in zip(dates, idx)]
    (src / "index" / "sh000001.csv").write_bytes(chr(10).join(lines).encode("gbk"))
    data = tmp_path / "data"
    import_baseline(src, data / "market", "v-test", workers=1, log=lambda *_: None)
    return create_app(Settings(data_dir=data, frontend_dist=tmp_path / "none"))


@pytest.fixture
def client(app):
    c = TestClient(app)
    login_as_admin(c)
    return c


def test_engine_shapes(app):
    snap = app.state.market.snapshot()
    sf = load(snap, "sh600519")
    a = analyze(sf, 20, fee=0.05)
    assert a["all"]["n"] >= 500 and a["similar"]["n"] == max(200, round(a["all"]["n"] * .1))
    z = a["similar"]["zones"]
    assert z["down"] + z["up_not_breakeven"] + z["breakeven"] == pytest.approx(1)
    assert a["similar"]["breakeven_prob"] <= a["similar"]["up_prob"]
    assert sum(b["n"] for b in a["all"]["histogram"]) == a["all"]["n"]
    with pytest.raises(NotEnoughHistory):
        analyze(sf, 20, asof=sf.df.date.iloc[150].strftime("%Y-%m-%d"))   # 当时上市不久，起点不够
    # 到期结算：手工核对
    df = sf.df
    i = len(df) - 31
    res = outcome(sf, df.date.iloc[i].strftime("%Y-%m-%d"), 20)
    assert res["done"] and res["return"] == pytest.approx(df.close.iloc[i + 20] / df.close.iloc[i] - 1)
    assert outcome(sf, df.date.iloc[-5].strftime("%Y-%m-%d"), 20) == {"done": False, "elapsed": 4, "horizon": 20}


def test_narrative_helpers():
    assert horizon_text(63) == "3 个月" and horizon_text(7) == "7 个交易日"
    assert tens(0.476) == 5 and tens(0.04) == 0
    assert estimate_due("2026-11-20", 5) == "2026-11-27"     # 跳过周末


def test_ask_and_seal(client: TestClient):
    s = client.get("/api/ask/stock", params={"code": "sh600519", "horizon": 20}).json()
    assert s["name"] == "贵州茅台" and s["verdict"]["value"] == round(s["analysis"]["similar"]["up_prob"] * 100)
    assert "每 10 次有" in s["verdict"]["plain"] and s["voice"]
    o = client.get("/api/ask/option", params={"code": "sh600519", "horizon": 63, "fee": 0.075}).json()
    assert o["price"] in ("偏贵", "偏便宜", "大致合理") and "回本" in o["verdict"]["plain"]
    assert client.get("/api/ask/option", params={"code": "sh600519", "horizon": 63}).status_code == 422
    assert client.get("/api/ask/stock", params={"code": "sz999999"}).status_code == 404

    j = client.post("/api/judgments", json={"kind": "option", "code": "sh600519", "horizon": 63, "fee": 0.075}).json()
    assert j["status"] == "sealed" and j["prediction"]["prob"] == o["verdict"]["value"] / 100 and j["fee"] == 0.075
    assert client.post("/api/judgments", json={"kind": "option", "code": "sh600519", "horizon": 63}).status_code == 422
    listing = client.get("/api/judgments").json()
    assert listing["items"][0]["id"] == j["id"] and listing["record"] == {"settled": 0}


def test_settlement(app, client: TestClient):
    """把封存日改到 30 根 K 线之前，读取时应自动揭晓。"""
    j = client.post("/api/judgments", json={"kind": "stock", "code": "sh600519", "horizon": 20}).json()
    sf = load(app.state.market.snapshot(), "sh600519")
    earlier = sf.df.date.iloc[-31].strftime("%Y-%m-%d")
    from sqlalchemy import update
    from sixiang.auth.db import judgments
    with app.state.auth.engine.begin() as conn:
        conn.execute(update(judgments).where(judgments.c.id == j["id"]).values(asof=earlier))
    got = client.get(f"/api/judgments/{j['id']}").json()
    assert got["status"] == "settled" and got["outcome"]["start_date"] == earlier
    i = len(sf.df) - 31
    assert got["outcome"]["return"] == pytest.approx(sf.df.close.iloc[i + 20] / sf.df.close.iloc[i] - 1)
    assert got["outcome"]["hit"] == (got["outcome"]["return"] > 0) and got["outcome"]["position"]
    rec = client.get("/api/judgments").json()["record"]
    assert rec["settled"] == 1 and rec["hits"] in (0, 1)
    # 别人看不到
    app.state.auth.register("路人甲", "13711112222", "abcdef", "abcdef", status="active")
    other = TestClient(app)
    other.post("/api/auth/login", json={"account": "路人甲", "password": "abcdef"})
    assert other.get(f"/api/judgments/{j['id']}").status_code == 404


def test_stance_and_record(app, client: TestClient):
    """封存时表态；揭晓后档案里能看到“我说对几次、小四对几次、意见不同时谁对”。"""
    from sqlalchemy import update
    from sixiang.auth.db import judgments
    assert client.post("/api/judgments", json={"kind": "stock", "code": "sh600519", "horizon": 20, "stance": "maybe"}).status_code == 422
    plain = client.post("/api/judgments", json={"kind": "stock", "code": "sh600000", "horizon": 20}).json()
    assert plain["prediction"]["stance"] is None
    sf = load(app.state.market.snapshot(), "sh600519")
    earlier = sf.df.date.iloc[-31].strftime("%Y-%m-%d")
    made = {}
    for stance in ("yes", "no", "follow"):
        j = client.post("/api/judgments", json={"kind": "stock", "code": "sh600519", "horizon": 20, "stance": stance}).json()
        assert j["prediction"]["stance"] == stance
        made[stance] = j
        with app.state.auth.engine.begin() as conn:
            conn.execute(update(judgments).where(judgments.c.id == j["id"]).values(asof=earlier))
    data = client.get("/api/judgments").json()
    rec = data["record"]
    hit = next(j for j in data["items"] if j["id"] == made["yes"]["id"])["outcome"]["hit"]
    lean = made["yes"]["prediction"]["prob"] >= 0.5
    # 三条已揭晓；其中表过“会 / 不会”的两条进入“我自己”的统计，“听小四的”不算
    assert rec["settled"] == 3 and rec["own"]["n"] == 2
    assert rec["own"]["right"] == 1                       # 一条说会、一条说不会，必然对一条
    assert rec["own"]["xiaosi_right"] == (2 if lean == hit else 0)
    assert rec["own"]["differ"] == 1 and rec["own"]["differ_right"] == (0 if lean == hit else 1)


def test_watchlist(app, client: TestClient):
    assert client.get("/api/watchlist").json()["items"] == []
    got = client.post("/api/watchlist/SH600519").json()
    assert [i["code"] for i in got["items"]] == ["sh600519"]
    row = got["items"][0]
    a = analyze(load(app.state.market.snapshot(), "sh600519"), 21)
    assert row["name"] == "贵州茅台" and row["prob"] == pytest.approx(a["similar"]["up_prob"]) and row["base_prob"] == pytest.approx(a["all"]["up_prob"])
    assert row["close"] == pytest.approx(a["close"]) and row["date"] == a["asof"]
    client.post("/api/watchlist/sh600519")                # 重复添加不报错、不重复
    client.post("/api/watchlist/sz000001")
    assert [i["code"] for i in client.get("/api/watchlist").json()["items"]] == ["sh600519", "sz000001"]
    assert client.post("/api/watchlist/sz999999").status_code == 404
    assert [i["code"] for i in client.post("/api/watchlist/sh600519/remove").json()["items"]] == ["sz000001"]
    # 各人的自选互不可见
    app.state.auth.register("路人乙", "13711113333", "abcdef", "abcdef", status="active")
    other = TestClient(app)
    other.post("/api/auth/login", json={"account": "路人乙", "password": "abcdef"})
    assert other.get("/api/watchlist").json()["items"] == []


def test_similar_points_and_fee_curve(app):
    sf = load(app.state.market.snapshot(), "sh600519")
    a = analyze(sf, 20, fee=0.05)
    pts = a["similar_points"]
    assert len(pts) == a["similar"]["n"] and [p[0] for p in pts] == sorted(p[0] for p in pts)
    assert np.mean([r > 0 for _, r in pts]) == pytest.approx(a["similar"]["up_prob"])
    curve = {round(c["fee"], 4): c for c in a["fee_curve"]}
    assert curve[0.05]["similar"] == pytest.approx(a["similar"]["breakeven_prob"])
    probs = [c["similar"] for c in a["fee_curve"]]
    assert probs == sorted(probs, reverse=True)          # 期权费越高，回本越难
    assert analyze(sf, 20)["fee_curve"] is None


def test_ask_index_compare_series(client: TestClient):
    i = client.get("/api/ask/index", params={"code": "sh000001", "horizon": 21}).json()
    assert i["kind"] == "index" and "指数在 60 日均线" in i["voice"] and i["analysis"]["similar"]["n"] >= 200
    c = client.get("/api/ask/compare", params={"a": "sh600519", "b": "sz000001", "horizon": 21}).json()
    assert [x["code"] for x in c["items"]] == ["sh600519", "sz000001"] and c["question"].startswith("贵州茅台和平安银行")
    assert client.get("/api/ask/compare", params={"a": "sh600519", "b": "SH600519"}).status_code == 422
    s = client.get("/api/ask/series", params={"code": "sh600519"}).json()
    assert len(s["dates"]) == len(s["close"]) and s["dates"] == sorted(s["dates"])
    assert client.get("/api/ask/series", params={"code": "sh000001", "index": True}).status_code == 200


def test_option_upside(app):
    """问期权讲的是“能涨多少”：阶梯、到期和中途最高（持有满 5 天后才能平仓），数字和日线对得上。"""
    sf = load(app.state.market.snapshot(), "sh600519")
    a = analyze(sf, 63, fee=0.075)
    up = a["upside"]["similar"]
    assert a["upside"]["lock"] == 5 and [r["x"] for r in up["ladder"]] == [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
    assert all(r["peak"] >= r["end"] for r in up["ladder"])                       # 中途到过的，一定不比到期还在的少
    assert [r["end"] for r in up["ladder"]] == sorted((r["end"] for r in up["ladder"]), reverse=True)
    assert up["peak"]["median"] >= up["end"]["median"] and up["peak"]["over_fee"] >= up["end"]["over_fee"]
    assert up["end"]["over_fee"] == pytest.approx(a["similar"]["breakeven_prob"])
    assert up["back"]["typical"] == pytest.approx(max(up["end"]["median"], 0) / 0.075)
    # 手算一个起点：第 5 天到第 63 天收盘价的最高点
    df = sf.df.reset_index(drop=True)
    date, _ = a["similar_points"][0]
    i = int(df.index[df.date == date][0])
    peak = df.close.iloc[i + 5:i + 64].max() / df.close.iloc[i] - 1
    assert peak >= df.close.iloc[i + 63] / df.close.iloc[i] - 1
    # 期限不到 5 天：没有“中途”，只讲到期
    short = analyze(sf, 5, fee=0.03)["upside"]["similar"]
    assert short["peak"] is None and "peak" not in short["ladder"][0] and short["back"]["peak_typical"] is None
    assert analyze(sf, 63)["upside"] is None


def test_checkup_and_mcp_tools_degrade(client, monkeypatch):
    """体检接口：几个期限 + 能取到的几项。没接 MCP 时相关几项不出现，接口不报错。"""
    r = client.get("/api/ask/checkup", params={"code": "sh600519"})
    assert r.status_code == 200
    body = r.json()
    assert [h["horizon"] for h in body["horizons"]] == [5, 10, 21, 63] and all(h["low"] <= h["close"] * (1 + h["median"]) <= h["high"] for h in body["horizons"])
    names = [i["tool"] for i in body["items"]]
    assert "limit_up_history" in names and "stock_live" not in names and "money_flow" not in names
    assert client.get("/api/ask/checkup", params={"code": "nope"}).status_code == 404

    # 接上（假的）MCP：实时行情那一项出现，名单页的今日名单挂上实时
    from sixiang.data import mcp
    from sixiang.room import tools

    class Fake:
        def call(self, tool, args, ttl=0):
            assert tool == "get_realtime_quotes" and args["symbols"] == ["600519.SH"]
            return {"snapshots": [{"symbol": "600519.SH", "quoteTime": "2026-11-26 10:31:00", "latest": 33.0, "changeRatio": 10.0, "amount": 2e8, "high": 33.0, "low": 30.5, "open": 30.6}]}
    monkeypatch.setattr(mcp, "_client", Fake())
    monkeypatch.setattr(mcp, "_loaded", True)
    assert mcp.symbol("sz002145") == "002145.SZ" and mcp.code("600519.SH") == "sh600519"
    live = tools.run(tools.ToolContext(client.app.state.market), "stock_live", {"code": "sh600519"})
    assert live.ok and "现在 33.00" in live.text and "+10.00%" in live.text and live.card["change"] == pytest.approx(0.1)


def test_market_breadth_and_env(client, monkeypatch):
    """涨跌家数用自己的日线算；市场环境接口在没接 MCP 时只给算得出来的那项。"""
    from sixiang.room import tools
    r = tools.run(tools.ToolContext(client.app.state.market), "market_breadth", {})
    assert r.ok and r.card["up"] + r.card["down"] <= r.card["n"] and r.card["n"] >= 1 and "全市场" in r.text
    env = client.get("/api/ask/market-env").json()["items"]
    assert [i["tool"] for i in env] == ["market_breadth"]

    from sixiang.data import mcp

    class Fake:
        def call(self, tool, args, ttl=0):
            if tool == "get_cn_market_snapshot":
                return {"indices": [{"name": "上证综指", "observedAt": "2026-11-26 15:00", "last": 3476.88, "changePct": 0.5},
                                    {"name": "中证1000", "observedAt": "2026-11-26 15:00", "last": 5531.84, "changePct": -0.3}],
                        "crossSection": {"smallMinusLargePct": -0.8}}
            if tool == "get_overseas_market_close_snapshot":
                return {"sessionDate": "2026-11-25", "indices": [{"name": "纳斯达克综合指数", "close": 23585.8, "changeRatio": -0.62}],
                        "semiconductorBellwethers": [{"name": "英伟达", "close": 149.3, "changeRatio": -3.91}]}
            raise mcp.McpError(tool)
    monkeypatch.setattr(mcp, "_client", Fake())
    monkeypatch.setattr(mcp, "_loaded", True)
    ctx = tools.ToolContext(client.app.state.market)
    m = tools.run(ctx, "market_today", {})
    assert m.ok and "上证综指 +0.50%" in m.text and "大盘股更强" in m.text and m.card["small_minus_large"] == pytest.approx(-0.008)
    u = tools.run(ctx, "us_overnight", {})
    assert u.ok and "纳斯达克综合 -0.62%" in u.text and "英伟达 -3.91%" in u.text and u.card["date"] == "2026-11-25"
    assert not tools.run(ctx, "hot_concepts", {}).ok                       # 取不到的工具回一句话，不抛异常
