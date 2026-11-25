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

from .conftest import login_as_admin, write_daily

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
    c = TestClient(app)
    login_as_admin(c)
    return c


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


RULE2 = {"name": "收阳且放量", "min_bars": 60, "cooldown": 0, "horizons": [1, 5], "conditions": [
    {"label": "收阳", "left": {"field": "close"}, "op": ">", "right": {"field": "open"}},
    {"label": "自定义放量", "left": {"field": "volume"}, "op": ">", "right": {"fn": "mul", "x": {"fn": "lag", "x": {"fn": "sma", "x": {"field": "volume"}, "n": 7}, "n": 1}, "y": 0.5}}]}


def test_variant_compare_library(client: TestClient):
    base = client.post("/api/patterns/jobs", json={"rule": RULE2}).json()
    assert base["library_save"]["conditions_added"] == 1   # “收阳”已在内置条件库，只保存自定义放量
    assert _wait(client, base["id"])["status"] == "completed"

    # 去掉第 2 条：新研究记录变更来源
    v = client.post(f"/api/patterns/jobs/{base['id']}/variant", json={"action": "remove", "index": 1}).json()
    assert v["comparison_base"] == base["id"] and v["comparison_change"]["action"] == "remove"
    assert len(v["rule"]["conditions"]) == 1 and "去掉「自定义放量」" in v["name"]
    assert _wait(client, v["id"])["status"] == "completed"

    # 增加已存在的条件被拒绝；增加库里的新条件可以
    dup = client.post(f"/api/patterns/jobs/{base['id']}/variant", json={"action": "add", "condition": RULE2["conditions"][0]})
    assert dup.status_code == 422
    lib = client.get("/api/patterns/library").json()
    assert lib["categories"] and len(lib["modules"]) >= 20
    assert [c["name"] for c in lib["conditions"]] == ["自定义放量"]
    assert next(p for p in lib["patterns"] if p["name"] == "收阳且放量")["last_job"] == base["id"]
    rsi = next(m for m in lib["modules"] if m["key"] == "rsi")
    added = client.post(f"/api/patterns/jobs/{base['id']}/variant", json={"action": "add", "condition": rsi["condition"]}).json()
    assert len(added["rule"]["conditions"]) == 3

    cmp = client.get("/api/patterns/compare", params={"left": base["id"], "right": v["id"]}).json()
    assert cmp["comparable"] and [c["label"] for c in cmp["only_left"]] == ["自定义放量"] and cmp["only_right"] == []
    assert cmp["overlap"]["only_right"] == 0                      # 去掉条件后事件只多不少
    assert cmp["overlap"]["common"] + cmp["overlap"]["only_left"] == cmp["left"]["events"]
    assert cmp["right"]["events"] >= cmp["left"]["events"]

    worst = client.get(f"/api/patterns/jobs/{v['id']}/events", params={"sort": "worst", "horizon": 5, "limit": 3}).json()["items"]
    best = client.get(f"/api/patterns/jobs/{v['id']}/events", params={"sort": "best", "horizon": 5, "limit": 3}).json()["items"]
    assert worst[0]["returns"]["5"] <= best[0]["returns"]["5"]
    assert client.get(f"/api/patterns/jobs/{v['id']}/events", params={"sort": "typical", "horizon": 5}).json()["total"] > 0

    # 同一数据版本上重跑会复用原结果
    assert client.post(f"/api/patterns/jobs/{base['id']}/rerun").json()["id"] == base["id"]

    pid = lib["patterns"][0]["id"]
    assert client.post(f"/api/patterns/library/patterns/{pid}/remove").status_code == 200
    assert client.post(f"/api/patterns/library/patterns/{pid}/remove").status_code == 404


def test_method_library(client: TestClient):
    """方法库：第一次查看时系统自动排队计算内置模板，算完后所有人都能直接看到结论。"""
    first = client.get("/api/patterns/methods").json()["methods"]
    assert len(first) == len(TEMPLATES) and first[0]["name"] == "放量突破"
    for m in first:
        assert m["status"] in ("queued", "running", "completed") and m["job"]
        _wait(client, m["job"])
    done = client.get("/api/patterns/methods").json()["methods"]
    assert [m["job"] for m in done] == [m["job"] for m in first]            # 不重复计算
    assert all(m["status"] == "completed" and "summary" in m and "years" in m for m in done), [(m["name"], m["status"], m.get("message")) for m in done]
    # 系统算的结果不出现在个人的研究记录里，但普通用户可以打开
    assert client.get("/api/patterns/jobs").json() == [] or all(not j.get("system") for j in client.get("/api/patterns/jobs").json())
    client.app.state.auth.register("路人丙", "13711114444", "abcdef", "abcdef", status="active")
    other = TestClient(client.app)
    other.post("/api/auth/login", json={"account": "路人丙", "password": "abcdef"})
    assert other.get("/api/patterns/jobs").json() == []
    assert other.get(f"/api/patterns/jobs/{done[0]['job']}/result").status_code == 200


def test_watchlist_signals(client: TestClient):
    """自选 × 方法库：自选里今天符合某个方法的股票，和方法结果里的“今日符合”一致。"""
    for m in client.get("/api/patterns/methods").json()["methods"]:
        _wait(client, m["job"])
    methods = client.get("/api/patterns/methods").json()["methods"]
    today = {}
    for m in methods:
        for x in client.get(f"/api/patterns/jobs/{m['job']}/result").json()["selected"]:
            today.setdefault(x["code"], set()).add(m["name"])
    codes = client.get("/api/securities", params={"q": "", "limit": 5}).json()
    watch = sorted(set(list(today)[:2]) | {codes[0]["code"]})
    for c in watch:
        client.post(f"/api/watchlist/{c}")
    sig = client.get("/api/watchlist/signals").json()
    assert sig["methods_ready"] == sig["methods_total"] == len(methods) and sig["watch_count"] == len(watch)
    got = {i["code"]: {h["method"] for h in i["hits"]} for i in sig["items"]}
    assert got == {c: today[c] for c in watch if c in today}
    assert set(sig["quiet"]) == {c for c in watch if c not in today}
