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
    # 趋势类不讲当天收盘，讲入选后最高涨过多少：甲 18 日开盘 10.5 入选，之后最高 11.2；乙 20.8 → 22.0
    assert w["latest"]["title"] == "甲股份 入选后最高涨过 7%" and [x["name"] for x in w["latest"]["stars"]] == ["甲股份", "乙股份"]
    day = c.get("/api/picks/wenge", params={"date": DAYS[2]}).json()
    assert [i["name"] for i in day["items"]] == ["乙股份", "甲股份"] and day["settled"]
    assert abs(day["items"][0]["open_pct"] - 0.04) < 1e-9 and "undistri" not in day["items"][0]
    jia = day["items"][1]
    assert jia["pick_price"] == 10.5 and jia["since_days"] == 1 and jia["streak"] == 1 and "since_ret" not in jia
    assert abs(jia["since_max"] - (11.2 / 10.5 - 1)) < 1e-9 and day["follow_days"] == 20 and day["best"][0]["code"] == "sz000001"
    assert all("no_open" in i and "skip" not in i for i in day["items"]) and day["open_count"] == sum(not i["no_open"] for i in day["items"])
    assert day["heat"] == {"count": 2, "level": "cold", "history": None}                 # 历史不够长：只说冷热，不给统计
    stats = c.get("/api/picks/wenge/stats").json()
    assert stats["kind"] == "sim" and len(stats["sim"]["nav"]) == len(stats["sim"]["dates"]) == m["days"]
    assert stats["sim"]["summary"]["max_drawdown"] < 0.1 and stats["facts"] and stats["sim"]["trades"]["win_avg"] > -stats["sim"]["trades"]["loss_avg"]
    hit = c.get("/api/picks/stock/sz000001").json()["pick"]
    assert hit["strategy"] == "wenge" and hit["rank"] == 2 and "仿真模拟盘" in hit["facts"][0]
    # 选股、买卖的规则不出现在任何接口里
    blob = json.dumps([items, day, stats, hit], ensure_ascii=False)
    for word in ("未分配", "资本公积", "净利润", "undistri", "np_yoy", "冲高", "振幅", "止盈", "止损", "均线", "MA", "冷却", "成交额", "ma20", "amplitude", "surge"):
        assert word not in blob, word


def test_streak_counts_consecutive_list_days():
    """连续入选第几天：按出名单的日子数，断一天重新数。"""
    m = pd.DataFrame({"code": ["a", "a", "a", "b", "b", "a"], "date": ["d1", "d2", "d3", "d1", "d3", "d5"]})
    m = pd.concat([m, pd.DataFrame({"code": ["c"], "date": ["d4"]})])          # d4 这天有名单，但没有 a
    out = pick_service._streaks(m).set_index(["code", "date"]).streak.to_dict()
    assert out[("a", "d3")] == 3 and out[("b", "d3")] == 1 and out[("a", "d5")] == 1
    assert [pick_service._level(n) for n in (4, 15, 40, 41)] == ["cold", "normal", "normal", "hot"]


def _bars(code, closes, amount=5e8, high_pad=0.02, low_pad=0.02, last=None):
    """造一串日线：每天开盘等于前一天收盘，最高最低各留一点振幅。last 可以改写最后一根。"""
    rows, prev = [], closes[0]
    for i, c in enumerate(closes):
        rows.append({"code": code, "date": i, "open": prev, "high": max(prev, c) * (1 + high_pad), "low": min(prev, c) * (1 - low_pad),
                     "close": c, "amount": amount, "adj_factor": 1.0})
        prev = c
    if last:
        rows[-1].update(last)
    return rows


def test_skip_reasons_follow_live_gates(monkeypatch):
    """入选后开不开仓：和实盘程序线上版的那几道闸门一致（成交额那道名单页默认不判断，见下）。"""
    monkeypatch.setattr(wenge, "AMOUNT_MIN", 3e8)
    flat = [10.0] * 25
    bars = pd.DataFrame(
        _bars("sh600001", flat)                                           # 一切正常
        + _bars("sh600002", [10.0] * 20 + [10.0, 10.5, 11.0, 11.6, 12.2])   # 从 5 日低点涨了 20% 多
        + _bars("sh600003", flat, last={"high": 10.6})                    # 昨天冲高 6% 又回落
        + _bars("sh600004", flat)                                         # 今天高开 6%
        + _bars("sh600005", flat, high_pad=0.002, low_pad=0.002)          # 振幅太小
        + _bars("sh600006", flat, amount=1e8)                             # 成交额不够
        + _bars("sz300007", flat)                                         # 板块指数双下拐
        + _bars("sh600008", [12.0] * 15 + [10.0] * 10)                    # 在 20 日线下面
        + _bars("sh600009", flat[:3])                                     # 上市没几天
    )
    opens = {c: 10.0 for c in bars.code.unique()} | {"sh600004": 10.6, "sh600002": 12.2}
    out = wenge.skip_reasons(bars, opens, {"main": False, "gem": True, "star": False})
    assert out == {"sh600002": "gain", "sh600003": "surge", "sh600004": "gap", "sh600005": "amplitude", "sh600006": "amount",
                   "sz300007": "index", "sh600008": "ma20", "sh600009": "history"}
    assert wenge.skip_reasons(bars, {"sh600001": 11.0}, {}) == {"sh600001": "gap"} and wenge._limit_up("sz300007", 10.0) == 12.0
    monkeypatch.setattr(wenge, "AMOUNT_MIN", 0.0)                         # 名单页不看成交额
    assert "sh600006" not in wenge.skip_reasons(bars, opens, {})
