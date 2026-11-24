"""形态规则：格式、校验与计算。从 PatternLab rules.py 迁移，规则 JSON 格式保持兼容。

规则是声明式 JSON，不执行任何代码。一条规则包含 1–16 个 AND 条件，
每个条件比较左右两个表达式（行情字段、常数或指标函数）。
所有价格类计算使用后复权价格。
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

FIELDS = ["open", "high", "low", "close", "volume", "amount", "market_cap"]
OPS = [">", ">=", "<", "<=", "cross_up", "cross_down"]
FUNCS = ["sma", "ema", "max", "min", "lag", "change", "ratio", "add", "sub", "mul", "rsi", "atr",
         "macd", "macd_signal", "boll_upper", "boll_lower", "abs"]

NO_X = {"atr", "macd", "macd_signal"}           # 不接受 x，固定使用行情
BINARY = {"ratio", "add", "sub", "mul"}          # 需要 y
WINDOWED = {"sma", "ema", "lag", "change", "rsi", "atr", "boll_upper", "boll_lower"}
DEFAULT_N = {"rsi": 14, "atr": 14}

STUDY_START = "2007-01-01"


def field(name: str) -> dict:
    return {"field": name}


def fn(name: str, x: Any = None, n: int | None = None, **kw) -> dict:
    out: dict = {"fn": name}
    if x is not None:
        out["x"] = x
    if n is not None:
        out["n"] = n
    out.update(kw)
    return out


def cond(label: str, left: Any, op: str, right: Any) -> dict:
    return {"label": label, "left": left, "op": op, "right": right}


TEMPLATES = [
    {"name": "放量突破", "description": "收盘突破此前 20 根 K 线最高价，同时成交量达到此前 20 根均量的 1.5 倍。", "conditions": [
        cond("突破前期高点", field("close"), ">", fn("lag", fn("max", field("high"), 20), 1)),
        cond("成交量达到放量要求", field("volume"), ">", fn("mul", fn("lag", fn("sma", field("volume"), 20), 1), y=1.5)),
        cond("收阳线", field("close"), ">", field("open"))]},
    {"name": "均线金叉", "description": "MA5 上穿 MA20，且当日成交量高于此前 20 根均量。", "conditions": [
        cond("短期均线上穿长期均线", fn("sma", field("close"), 5), "cross_up", fn("sma", field("close"), 20)),
        cond("成交量高于均量", field("volume"), ">", fn("lag", fn("sma", field("volume"), 20), 1))]},
    {"name": "下跌后长下影", "description": "截至昨日的 20 日跌幅至少 10%；今日下影线占开盘价至少 3%，实体不超过 2%，收盘位于当日振幅上方 40% 内。", "conditions": [
        cond("此前已经下跌", fn("lag", fn("change", field("close"), 20), 1), "<=", -.10),
        cond("下影线足够长", fn("ratio", fn("sub", fn("min", field("open"), y=field("close")), y=field("low")), y=field("open")), ">=", .03),
        cond("实体较小", fn("ratio", fn("abs", fn("sub", field("close"), y=field("open"))), y=field("open")), "<=", .02),
        cond("收盘靠近当日高位", fn("ratio", fn("sub", field("close"), y=field("low")), y=fn("sub", field("high"), y=field("low"))), ">=", .6)]},
    {"name": "缩量整理", "description": "最近 10 根高低价区间小于 10%，今日量低于此前 20 根均量的 60%，收盘高于 MA60。", "conditions": [
        cond("整理区间足够窄", fn("ratio", fn("max", field("high"), 10), y=fn("min", field("low"), 10)), "<", 1.1),
        cond("成交量满足缩量要求", field("volume"), "<", fn("mul", fn("lag", fn("sma", field("volume"), 20), 1), y=.6)),
        cond("保持中期趋势", field("close"), ">", fn("sma", field("close"), 60))]},
    {"name": "缩量回踩均线", "description": "日线定义：MA20 高于 5 日前，昨日收盘高于昨日 MA20；今日最低价低于昨日，且位于今日收盘后 MA20 的上下 2% 内；今日收盘不低于 MA20，全天成交量低于此前 20 日均量的 80%。仅按收盘后的日线数据判定。", "conditions": [
        cond("均线仍向上", fn("sma", field("close"), 20), ">", fn("lag", fn("sma", field("close"), 20), 5)),
        cond("昨日收盘在均线上方", fn("lag", field("close"), 1), ">", fn("lag", fn("sma", field("close"), 20), 1)),
        cond("当日最低价低于昨日", field("low"), "<", fn("lag", field("low"), 1)),
        cond("最低价相对均线下界", fn("ratio", field("low"), y=fn("sma", field("close"), 20)), ">=", .98),
        cond("最低价相对均线上界", fn("ratio", field("low"), y=fn("sma", field("close"), 20)), "<=", 1.02),
        cond("收盘不低于均线", field("close"), ">=", fn("sma", field("close"), 20)),
        cond("当日成交量低于此前均量的指定比例", field("volume"), "<", fn("mul", fn("lag", fn("sma", field("volume"), 20), 1), y=.8))]},
    {"name": "超跌后转强", "description": "截至昨日的 20 日跌幅至少 15%；今日收盘从均线下方上穿 MA5，并且收阳线。", "conditions": [
        cond("截至昨日跌幅达到阈值", fn("lag", fn("change", field("close"), 20), 1), "<=", -.15),
        cond("收盘重新上穿短期均线", field("close"), "cross_up", fn("sma", field("close"), 5)),
        cond("当日收阳", field("close"), ">", field("open"))]},
]

DEFAULTS = {"version": 1, "start": STUDY_START, "asof": "", "cooldown": 10, "min_bars": 250, "exclude_st": True,
            "markets": ["sh", "sz", "bj"], "horizons": [1, 3, 5, 10, 20], "source": "网页", "source_note": ""}


class RuleError(ValueError):
    """规则不合法，信息可直接展示给用户。"""


# ---------------------------------------------------------------- 校验

def validate_expr(e: Any, depth: int = 0) -> None:
    if depth > 10:
        raise RuleError("表达式最多嵌套 10 层")
    if isinstance(e, (int, float)) and not isinstance(e, bool):
        if not math.isfinite(e) or abs(e) > 1e15:
            raise RuleError("常数超出范围")
        return
    if not isinstance(e, dict):
        raise RuleError("条件值必须是数字或表达式对象")
    if "field" in e:
        if set(e) != {"field"} or e["field"] not in FIELDS:
            raise RuleError("不支持的行情字段")
        return
    name = e.get("fn")
    if name not in FUNCS:
        raise RuleError("不支持的指标函数")
    if set(e) - {"fn", "x", "y", "n", "k"}:
        raise RuleError("指标包含未知参数")
    permitted = {"fn"}
    if name not in NO_X:
        permitted.add("x")
    if name in BINARY:
        permitted.add("y")
    if name in ("max", "min"):
        permitted.update(["y"] if "y" in e else ["n"])
    if name in WINDOWED:
        permitted.add("n")
    if name in ("boll_upper", "boll_lower"):
        permitted.add("k")
    if set(e) - permitted:
        raise RuleError(f"{name} 包含不适用参数")
    if name not in NO_X:
        if "x" not in e:
            raise RuleError(f"{name} 缺少 x")
        validate_expr(e["x"], depth + 1)
    pairwise = name in ("max", "min") and "y" in e
    if name in BINARY or pairwise:
        if "y" not in e:
            raise RuleError(f"{name} 缺少 y")
        validate_expr(e["y"], depth + 1)
    if name in WINDOWED or (name in ("max", "min") and not pairwise):
        n = e.get("n", DEFAULT_N.get(name, 20))
        if type(n) is not int or not 1 <= n <= 500:
            raise RuleError("窗口 n 必须为 1–500 的整数")
    if "k" in e and (not isinstance(e["k"], (int, float)) or not 0 < e["k"] <= 10):
        raise RuleError("k 必须为 0–10")


def validate_rule(raw: Any, latest: str) -> dict:
    """返回规范化后的规则。统计区间统一为 2007-01-01 至数据末日。"""
    if not isinstance(raw, dict):
        raise RuleError("规则必须为 JSON 对象")
    allowed = set(DEFAULTS) | {"name", "description", "conditions", "reference_id"}
    unknown = set(raw) - allowed
    if unknown:
        raise RuleError("未知规则字段：" + ", ".join(sorted(unknown)))
    r = {**DEFAULTS, **raw}
    if r["version"] != 1:
        raise RuleError("仅支持 version: 1")
    for key, limit in (("name", 80), ("description", 2000), ("source", 80), ("source_note", 4000)):
        value = r.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            raise RuleError(f"{key} 内容过长或类型错误")
    if not r.get("name", "").strip():
        raise RuleError("请填写形态名称")
    if not isinstance(r.get("conditions"), list) or not 1 <= len(r["conditions"]) <= 16:
        raise RuleError("每个规则支持 1–16 个 AND 条件")
    for c in r["conditions"]:
        if not isinstance(c, dict) or set(c) - {"label", "left", "op", "right"}:
            raise RuleError("条件格式错误")
        if not isinstance(c.get("label"), str) or not 1 <= len(c["label"]) <= 120:
            raise RuleError("每个条件需要 label")
        if c.get("op") not in OPS:
            raise RuleError("不支持的比较操作")
        validate_expr(c.get("left"))
        validate_expr(c.get("right"))
    r["asof"] = r["asof"] or latest
    for key in ("start", "asof"):
        if not isinstance(r[key], str) or len(r[key]) != 10:
            raise RuleError("日期格式 YYYY-MM-DD")
        try:
            pd.Timestamp(r[key])
        except ValueError as exc:
            raise RuleError("日期格式 YYYY-MM-DD") from exc
    if r["start"] > r["asof"] or r["asof"] > latest:
        raise RuleError("研究区间超出数据截止日，或开始日晚于截止日")
    r["start"], r["asof"] = STUDY_START, latest
    for key, lo, hi in (("cooldown", 0, 250), ("min_bars", 60, 1000)):
        if type(r[key]) is not int or not lo <= r[key] <= hi:
            raise RuleError(f"{key} 超出允许范围")
    if type(r["exclude_st"]) is not bool:
        raise RuleError("exclude_st 应为布尔值")
    if not isinstance(r["markets"], list) or not r["markets"] or any(m not in ("sh", "sz", "bj") for m in r["markets"]):
        raise RuleError("市场范围无效")
    h = r["horizons"]
    if not isinstance(h, list) or not h or len(h) > 10 or any(type(n) is not int or not 1 <= n <= 120 for n in h):
        raise RuleError("观察周期范围为 1–120")
    r["horizons"] = sorted(set(h))
    return r


# ---------------------------------------------------------------- 计算

def evaluate(df: pd.DataFrame, expression: Any, cache: dict) -> pd.Series:
    """计算表达式序列。df 需含后复权 open/high/low/close 与 volume/amount/market_cap。"""
    key = json.dumps(expression, sort_keys=True)
    if key in cache:
        return cache[key]
    if isinstance(expression, (int, float)):
        return pd.Series(float(expression), index=df.index)
    if "field" in expression:
        return df[expression["field"]]
    e = expression
    name = e["fn"]
    n = e.get("n", DEFAULT_N.get(name, 20))
    x = evaluate(df, e["x"], cache) if "x" in e else df["close"]
    y = evaluate(df, e["y"], cache) if "y" in e else None
    if name == "sma":
        out = x.rolling(n, min_periods=n).mean()
    elif name == "ema":
        out = x.ewm(span=n, adjust=False, min_periods=n).mean()
    elif name in ("max", "min"):
        if y is not None:
            # 两个操作数都要求有值（含各自的预热期）
            values = pd.concat([x, y], axis=1).replace([np.inf, -np.inf], np.nan)
            out = getattr(values, name)(axis=1, skipna=False)
        else:
            out = getattr(x.rolling(n, min_periods=n), name)()
    elif name == "lag":
        out = x.shift(n)
    elif name == "change":
        out = x / x.shift(n).replace(0, np.nan) - 1
    elif name == "ratio":
        out = x / y.replace(0, np.nan)
    elif name == "add":
        out = x + y
    elif name == "sub":
        out = x - y
    elif name == "mul":
        out = x * y
    elif name == "abs":
        out = x.abs()
    elif name == "rsi":
        delta = x.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        out = 100 - 100 / (1 + up / down.replace(0, np.nan))
        out = out.mask((down == 0) & (up > 0), 100).mask((down == 0) & (up == 0), 50)
    elif name == "atr":
        tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
        out = pd.Series(np.nan, index=df.index, dtype=float)
        if len(tr) >= n:
            # 与图表一致：首个 TR 为高低差；用前 N 个 TR 的均值做种子
            seeded = tr.iloc[n - 1:].copy()
            seeded.iloc[0] = tr.iloc[:n].mean()
            out.loc[seeded.index] = seeded.ewm(alpha=1 / n, adjust=False).mean()
    elif name in ("macd", "macd_signal"):
        out = df.close.ewm(span=12, adjust=False, min_periods=12).mean() - df.close.ewm(span=26, adjust=False, min_periods=26).mean()
        if name == "macd_signal":
            out = out.ewm(span=9, adjust=False, min_periods=9).mean()
    else:  # boll_upper / boll_lower
        sign = 1 if name == "boll_upper" else -1
        out = x.rolling(n).mean() + sign * e.get("k", 2) * x.rolling(n).std(ddof=0)
    cache[key] = out.replace([np.inf, -np.inf], np.nan)
    return cache[key]


def comparison(left: pd.Series, right: pd.Series, op: str) -> pd.Series:
    """cross_up / cross_down 为相邻两根日线的比较，不代表盘中交叉时点。"""
    if op == "cross_up":
        ok = (left > right) & (left.shift() <= right.shift())
    elif op == "cross_down":
        ok = (left < right) & (left.shift() >= right.shift())
    elif op == ">":
        ok = left > right
    elif op == ">=":
        ok = left >= right
    elif op == "<":
        ok = left < right
    else:
        ok = left <= right
    return ok.fillna(False) & left.notna() & right.notna()


def signals(df: pd.DataFrame, rule: dict) -> tuple[pd.Series, list]:
    """所有条件同时满足的位置，以及每个条件的左右值（用于解释入选原因）。"""
    cache: dict = {}
    mask = pd.Series(True, index=df.index)
    details = []
    for c in rule["conditions"]:
        left = evaluate(df, c["left"], cache)
        right = evaluate(df, c["right"], cache)
        mask &= comparison(left, right, c["op"])
        details.append((c, left, right))
    return mask, details
