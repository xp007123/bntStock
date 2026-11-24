from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sixiang.api.app import create_app
from sixiang.config import Settings
from sixiang.data.baseline_import import import_baseline
from sixiang.patterns.rules import TEMPLATES, RuleError, comparison, evaluate, validate_rule

from .conftest import write_daily

LATEST = "2026-11-18"


def test_templates_are_valid():
    for t in TEMPLATES:
        r = validate_rule(dict(t), LATEST)
        assert r["start"] == "2007-01-01" and r["asof"] == LATEST and r["horizons"] == [1, 3, 5, 10, 20]


@pytest.mark.parametrize("bad, message", [
    ({"name": "x", "conditions": []}, "1–16"),
    ({"name": "x", "conditions": [{"label": "a", "left": {"field": "pe"}, "op": ">", "right": 1}]}, "行情字段"),
    ({"name": "x", "conditions": [{"label": "a", "left": {"fn": "sma", "x": {"field": "close"}, "n": 0}, "op": ">", "right": 1}]}, "窗口"),
    ({"name": "x", "conditions": [{"label": "a", "left": {"fn": "eval"}, "op": ">", "right": 1}]}, "指标函数"),
    ({"name": "x", "conditions": [{"label": "a", "left": 1, "op": "==", "right": 1}]}, "比较操作"),
    ({"name": "", "conditions": [{"label": "a", "left": 1, "op": ">", "right": 0}]}, "名称"),
    ({"name": "x", "foo": 1, "conditions": [{"label": "a", "left": 1, "op": ">", "right": 0}]}, "未知规则字段"),
])
def test_rejects_invalid_rules(bad, message):
    with pytest.raises(RuleError, match=message):
        validate_rule(bad, LATEST)


def test_evaluate_and_cross():
    df = pd.DataFrame({"close": [1.0, 2, 3, 4, 3, 2, 3, 4]})
    cache: dict = {}
    sma2 = evaluate(df, {"fn": "sma", "x": {"field": "close"}, "n": 2}, cache)
    assert np.isnan(sma2.iloc[0]) and sma2.iloc[1] == 1.5
    up = comparison(df["close"], sma2, "cross_up")
    # 第 6 根（3 > 2.5）由下方上穿；窗口未满的位置不触发
    assert up.tolist() == [False, False, False, False, False, False, True, False]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    src = tmp_path / "src"
    (src / "daily").mkdir(parents=True)
    dates = pd.bdate_range("2025-09-01", periods=320)
    rng = np.random.default_rng(7)
    for code, name in (("sh600000", "浦发银行"), ("sz000001", "平安银行"), ("sh600519", "贵州茅台")):
        close = 10 * np.cumprod(1 + rng.normal(0, .02, len(dates)))
        prev = np.r_[close[0], close[:-1]]
        rows = [(d.strftime("%Y-%m-%d"), round(p * 1.001, 2), round(max(c, p) * 1.01, 2), round(min(c, p) * .99, 2), round(c, 2), round(p, 2))
                for d, c, p in zip(dates, close, prev)]
        write_daily(src / "daily" / f"{code}.csv", code, name, rows)
    data = tmp_path / "data"
    import_baseline(src, data / "market", "v-test", workers=1, log=lambda *_: None)
    app = create_app(Settings(data_dir=data, frontend_dist=tmp_path / "none"))
    app.state.jobs.workers = 1
    return TestClient(app)


RULE = {"name": "收阳线", "min_bars": 60, "cooldown": 0, "horizons": [1, 5],
        "conditions": [{"label": "收阳", "left": {"field": "close"}, "op": ">", "right": {"field": "open"}}]}


def _wait(client: TestClient, jid: str) -> dict:
    for _ in range(300):
        meta = client.get(f"/api/patterns/jobs/{jid}").json()
        if meta["status"] not in ("queued", "running"):
            return meta
        time.sleep(.2)
    raise AssertionError("任务超时")


def test_job_flow(client: TestClient):
    assert client.get("/api/patterns/templates").json()["templates"][0]["name"] == "放量突破"
    assert client.post("/api/patterns/validate", json={"rule": {"name": "x", "conditions": []}}).status_code == 422

    meta = client.post("/api/patterns/jobs", json={"rule": RULE}).json()
    assert meta["data_version"] == "v-test"
    done = _wait(client, meta["id"])
    assert done["status"] == "completed", done["message"]

    result = client.get(f"/api/patterns/jobs/{meta['id']}/result").json()
    assert result["event_total"] > 0 and [s["horizon"] for s in result["summary"]] == [1, 5]
    assert "events" not in result
    page = client.get(f"/api/patterns/jobs/{meta['id']}/events", params={"limit": 5}).json()
    assert page["total"] == result["event_total"] and len(page["items"]) == 5

    ev = page["items"][0]
    ex = client.get(f"/api/patterns/jobs/{meta['id']}/explain/{ev['code']}", params={"date": ev["date"]}).json()
    assert ex["passed"] and ev["date"] in ex["signal_dates"] and ex["conditions"][0]["passed"]

    again = client.post("/api/patterns/jobs", json={"rule": RULE}).json()
    assert again["id"] == meta["id"] and again["reused"]
    assert client.get("/api/patterns/jobs").json()[0]["id"] == meta["id"]


def test_unknown_job_404(client: TestClient):
    assert client.get("/api/patterns/jobs/nope").status_code == 404
