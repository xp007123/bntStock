"""文哥选股：初筛、多头判定、仿真模拟盘接口，以及规则不外露。全部不联网。"""
from __future__ import annotations

import json

import pandas as pd
from fastapi.testclient import TestClient

from sixiang.picks import service as pick_service
from sixiang.picks import wenge

from .conftest import login_as_admin
from .test_picks import DAYS, app  # noqa: F401  复用同一份小行情


def test_screen_matches_percent_rank():
    """行业内 PERCENT_RANK（降序）≤ 0.3、净利润同比 > 40、EPS 为空或不为负，和旧程序的 SQL 一样。"""
    rows = pd.DataFrame([
        # 银行 4 只：名次 0, 1/3, 2/3, 1 → 只有第一只在前 30%
        {"code": "a", "sw": "银行", "np_yoy": 50, "undistri": 9, "capital": 9, "eps": 1},
        {"code": "b", "sw": "银行", "np_yoy": 50, "undistri": 8, "capital": 8, "eps": 1},
        {"code": "c", "sw": "银行", "np_yoy": 50, "undistri": 7, "capital": 7, "eps": None},
        {"code": "d", "sw": "银行", "np_yoy": 50, "undistri": None, "capital": 6, "eps": 1},
        # 只有自己一只的行业：名次算 0；但净利润同比不够
        {"code": "e", "sw": "电子", "np_yoy": 30, "undistri": 1, "capital": 1, "eps": 1},
        {"code": "f", "sw": "传媒", "np_yoy": 80, "undistri": 1, "capital": 1, "eps": -0.1},   # EPS 为负
        {"code": "g", "sw": None, "np_yoy": 80, "undistri": 1, "capital": 1, "eps": 1},       # 没有行业
        {"code": "h", "sw": "汽车", "np_yoy": 41, "undistri": 2, "capital": 2, "eps": None},
    ])
    assert sorted(wenge.screen(rows).code) == ["a", "h"]


def test_bullish_needs_open_above_all_three_closes():
    pool = [{"code": "x", "name": "X", "undistri": 1.0}, {"code": "y", "name": "Y", "undistri": 3.0},
            {"code": "z", "name": "Z", "undistri": 2.0}, {"code": "w", "name": "W", "undistri": 5.0}]
    closes = pd.DataFrame([{"code": "x", "c5": 9, "c10": 9, "c20": 9, "prev_close": 9.5},
                           {"code": "y", "c5": 9, "c10": 9, "c20": 9, "prev_close": 9.8},
                           {"code": "z", "c5": 9, "c10": 11, "c20": 9, "prev_close": 9.9}])   # 开盘没高过 10 天前
    rows = wenge.bullish(pool, closes, {"x": 10, "y": 10, "z": 10, "w": 10})                    # w 没有足够历史
    assert [r["code"] for r in rows] == ["y", "x"] and rows[0]["rank"] == 1                    # 按每股未分配利润从高到低
    assert abs(rows[0]["open_pct"] - (10 / 9.8 - 1)) < 1e-9
    assert wenge.bullish(pool, closes, {"x": 0}) == []                                          # 集合竞价零成交


def test_api_sim_and_no_rules(app):  # noqa: F811
    svc = app.state.picks
    svc.store.save("wenge", DAYS[2], [{"rank": 1, "code": "sh600000", "name": "乙股份", "pick_open": 20.8, "pick_open_pct": 0.04, "undistri": 3.2},
                                      {"rank": 2, "code": "sz000001", "name": "甲股份", "pick_open": 10.5, "pick_open_pct": 0.05, "undistri": 1.1}])
    c = TestClient(app)
    login_as_admin(c)
    items = {s["id"]: s for s in c.get("/api/picks").json()["items"]}
    w = items["wenge"]
    m = pick_service.sim()
    assert w["record"] == "sim" and w["highlights"][0]["value"] == m["summary"]["total_return"]
    # 趋势类不讲当天收盘，讲入选以来：甲 18 日开盘 10.5 入选，19 日收 11.1；乙 20.8 → 20.2
    assert w["latest"]["title"] == "甲股份 入选 1 天涨 6%" and [x["name"] for x in w["latest"]["stars"]] == ["甲股份", "乙股份"]
    day = c.get("/api/picks/wenge", params={"date": DAYS[2]}).json()
    assert [i["name"] for i in day["items"]] == ["乙股份", "甲股份"] and day["settled"]
    assert abs(day["items"][0]["open_pct"] - 0.04) < 1e-9 and "undistri" not in day["items"][0]
    jia = day["items"][1]
    assert jia["pick_price"] == 10.5 and jia["since_days"] == 1 and abs(jia["since_ret"] - (11.1 / 10.5 - 1)) < 1e-9
    assert abs(jia["since_max"] - (11.2 / 10.5 - 1)) < 1e-9 and day["follow_days"] == 20 and day["best"][0]["code"] == "sz000001"
    stats = c.get("/api/picks/wenge/stats").json()
    assert stats["kind"] == "sim" and len(stats["sim"]["nav"]) == len(stats["sim"]["dates"]) == m["days"]
    assert stats["sim"]["summary"]["max_drawdown"] < 0.1 and stats["facts"]
    hit = c.get("/api/picks/stock/sz000001").json()["pick"]
    assert hit["strategy"] == "wenge" and hit["rank"] == 2 and "仿真模拟盘" in hit["facts"][0]
    # 选股、买卖的规则不出现在任何接口里
    blob = json.dumps([items, day, stats, hit], ensure_ascii=False)
    for word in ("未分配", "资本公积", "净利润", "undistri", "np_yoy", "冲高", "振幅", "止盈", "止损", "均线", "MA", "冷却"):
        assert word not in blob, word
