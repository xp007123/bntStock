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
