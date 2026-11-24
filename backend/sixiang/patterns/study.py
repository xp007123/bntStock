"""形态历史研究：全市场扫描、未来收益、汇总统计。从 PatternLab engine.py 迁移，口径保持一致。

口径（与 PatternLab 相同）：
- 价格用后复权；信号日后第 1 个市场交易日开盘买入，至第 N 个市场交易日收盘。
- 排除：次日开盘涨停（按板块涨跌幅限制计算）、ST/退市名称、名称未核验、次日或第 N 日无成交。
- 停牌日不补价；观察期未走完的不计入该周期。
- 同一只股票两次信号间隔不超过 cooldown 根 K 线时，只保留第一次。
- 超额：同一信号日、同一过滤条件下全部合格股票的等权平均收益之差。
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .rules import comparison, signals

FRAME_COLUMNS = ["date", "open", "high", "low", "close", "prev_close", "volume", "amount", "float_mcap",
                 "adj_factor", "name", "name_verified", "sector_l1"]

METHOD = ("后复权价格；信号日后第 1 个市场交易日开盘至第 N 个市场交易日收盘。排除次日开盘涨停、ST/退及缺失交易；"
          "未完成观察期不计入该周期分母。未扣费。1 日仅为日内价格观察，非 A 股可执行 T+0 收益。")
REFERENCE = "超额为同一信号日、同一股票范围、同一上市天数/ST/交易过滤下的等权股票收益差；不是指数或可交易组合。"
LIMITATIONS = ["统计为事件表现，非资金曲线或策略回测。", "持有期按市场交易日；指标窗口与冷却按个股数据行。",
               "数据源历史覆盖与前收盘价准确性影响复权和样本；未验证财务字段可得时点。", "重复事件可能相关；反复调参后需要独立区间验证。"]


def to_engine_frame(table) -> pd.DataFrame:
    """快照行 → 引擎使用的字段：后复权 OHLC，保留原始价用于涨停判断。"""
    df = table.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open", "high", "low", "close"):
        df["raw_" + c] = df[c]
    if len(df):
        # 按 PatternLab 的运算顺序计算后复权价，保证浮点结果逐位一致。
        # 价格相等时（突破、涨停等常见情形）不同运算顺序的末位误差会改变 > / >= 的判断。
        adjustment = (df["close"] / df["prev_close"]).cumprod()
        adjusted = adjustment * (df["close"].iloc[0] / adjustment.iloc[0])
        for c in ("open", "high", "low"):
            df[c] = df[c] / df["raw_close"] * adjusted
        df["close"] = adjusted
    df = df.rename(columns={"prev_close": "prev", "float_mcap": "market_cap", "sector_l1": "sector"})
    df["name"] = df["name"].fillna("")
    df["sector"] = df["sector"].fillna("未分类")
    return df


def eligible(df: pd.DataFrame, rule: dict) -> pd.Series:
    ok = (df.index >= rule["min_bars"] - 1) & (df.volume > 0) & (df.amount > 0)
    if rule["exclude_st"]:
        ok &= ~df.name.str.contains("ST|退", case=False, regex=True, na=False)
        ok &= df.name_verified
    if "market_cap" in repr(rule.get("conditions", [])):
        ok &= df.market_cap.notna() & (df.market_cap > 0)
    return pd.Series(ok, index=df.index)


def limit_rate(code: str, names: pd.Series) -> pd.Series:
    """开盘涨停判断用的涨跌幅限制。"""
    rate = pd.Series(.1, index=names.index)
    rate = rate.mask(names.str.contains("ST", case=False), .05)
    if code.startswith("sh68"):
        rate[:] = .2
    if code.startswith("sz30"):
        rate.loc[rate.index >= pd.Timestamp("2020-08-24")] = .2
    if code.startswith("bj"):
        rate[:] = .3
    return rate


def forward_returns(df: pd.DataFrame, calendar: pd.DatetimeIndex, horizons: list[int], code: str) -> dict[int, np.ndarray]:
    """t+1 市场交易日开盘至 t+h 市场交易日收盘；停牌日不补价。"""
    z = df.set_index("date").reindex(calendar)
    names = z["name"].fillna("")
    upper = np.floor(z["prev"] * (1 + limit_rate(code, names)) * 100 + 0.50000001) / 100
    entry = z.open.shift(-1)
    tradable = (z.volume.shift(-1) > 0) & (z.amount.shift(-1) > 0) & (z.raw_open.shift(-1) < upper.shift(-1))
    tradable &= ~names.shift(-1).fillna("").str.contains("ST|退", case=False)
    tradable &= z.name_verified.shift(-1).eq(True)  # 停牌日（无记录）视为不可交易
    result = {}
    for h in horizons:
        exit_ok = (z.volume.shift(-h) > 0) & (z.amount.shift(-h) > 0)
        result[h] = (z.close.shift(-h) / entry - 1).where(tradable & exit_ok).reindex(df.date).to_numpy()
    return result


def _num(v) -> float | None:
    v = float(v)
    return v if np.isfinite(v) else None


def scan_stock(df: pd.DataFrame, code: str, rule: dict, calendar: pd.DatetimeIndex):
    """单只股票：今日是否符合、历史事件、基准收益。"""
    df = df[df.date <= rule["asof"]].reset_index(drop=True)
    if len(df) < rule["min_bars"]:
        return None
    ok = eligible(df, rule)
    mask, details = signals(df, rule)
    mask &= ok
    in_period = df.date >= rule["start"]
    returns = forward_returns(df, calendar, rule["horizons"], code)

    latest = None
    if df.date.iloc[-1].strftime("%Y-%m-%d") == rule["asof"] and mask.iloc[-1]:
        row = df.iloc[-1]
        known = df.sector[df.sector != "未分类"]  # 最新几日的免费源行情可能缺行业，取最近一次已知行业
        latest = {"code": code, "name": row["name"], "sector": known.iloc[-1] if len(known) else "未分类", "date": rule["asof"], "price": float(row.raw_close),
                  "change": float(row.raw_close / row.prev - 1), "amount": float(row.amount),
                  "reasons": [{"label": c["label"], "left": _num(l.iloc[-1]), "op": c["op"], "right": _num(r.iloc[-1])} for c, l, r in details]}

    positions = np.flatnonzero((mask & in_period).to_numpy())
    kept, previous = [], -100000
    for i in positions:
        if i - previous > rule["cooldown"]:
            kept.append(int(i))
            previous = i
    events = []
    for i in kept:
        row = df.iloc[i]
        events.append({"code": code, "name": row["name"], "date": row.date.strftime("%Y-%m-%d"), "price": float(row.raw_close),
                       "returns": {str(h): _num(returns[h][i]) for h in rule["horizons"]}})
    base_ix = np.flatnonzero((ok & in_period).to_numpy())
    base_pos = calendar.get_indexer(df.date.iloc[base_ix])
    base = {h: returns[h][base_ix] for h in rule["horizons"]}
    return latest, events, base_pos, base, len(positions)


@dataclass
class _Chunk:
    daily_path: str
    items: list[tuple[str, list[int]]]
    rule: dict
    calendar: np.ndarray  # datetime64[ns]


def _scan_chunk(chunk: _Chunk):
    calendar = pd.DatetimeIndex(chunk.calendar)
    pf = pq.ParquetFile(chunk.daily_path)
    horizons = chunk.rule["horizons"]
    sums = np.zeros((len(horizons), len(calendar)))
    counts = np.zeros((len(horizons), len(calendar)), dtype=np.int64)
    selected, events, errors, raw = [], [], [], 0
    for code, groups in chunk.items:
        try:
            df = to_engine_frame(pf.read_row_groups(groups, columns=FRAME_COLUMNS))
            result = scan_stock(df, code, chunk.rule, calendar)
        except Exception as exc:  # 单只异常不影响整体，计入 errors
            errors.append({"code": code, "error": str(exc)})
            continue
        if result is None:
            continue
        latest, es, pos, base, n = result
        if latest:
            selected.append(latest)
        events.extend(es)
        raw += n
        for k, h in enumerate(horizons):
            values = base[h]
            good = np.isfinite(values) & (pos >= 0)
            np.add.at(sums[k], pos[good], values[good])
            np.add.at(counts[k], pos[good], 1)
    return len(chunk.items), selected, events, errors, raw, sums, counts


def summarize(events: list[dict], horizons: list[int], baseline: dict[str, dict[str, float]]):
    rows, years = [], []
    if not events:
        return rows, years
    for h in horizons:
        values = np.array([e["returns"].get(str(h)) if e["returns"].get(str(h)) is not None else np.nan for e in events], dtype=float)
        x = values[np.isfinite(values)]
        excess = []
        for e, v in zip(events, values):
            b = baseline.get(e["date"], {}).get(str(h))
            if np.isfinite(v) and b is not None and np.isfinite(b):
                excess.append(v - b)
        rows.append({"horizon": h, "valid": len(x), "unavailable": len(events) - len(x),
                     "win_rate": float((x > 0).mean()) if len(x) else None,
                     "mean": float(x.mean()) if len(x) else None, "median": float(np.median(x)) if len(x) else None,
                     "p10": float(np.quantile(x, .1)) if len(x) else None, "p90": float(np.quantile(x, .9)) if len(x) else None,
                     "excess_mean": float(np.mean(excess)) if excess else None, "excess_n": len(excess)})
        for year in sorted({e["date"][:4] for e in events}):
            a = np.array([e["returns"].get(str(h)) for e in events if e["date"].startswith(year)], dtype=float)
            a = a[np.isfinite(a)]
            years.append({"year": year, "horizon": h, "valid": len(a), "mean": float(a.mean()) if len(a) else None,
                          "win_rate": float((a > 0).mean()) if len(a) else None})
    return rows, years


class Cancelled(Exception):
    pass


def run_study(snapshot, rule: dict, progress: Callable[[dict], None] | None = None,
              should_cancel: Callable[[], bool] | None = None, workers: int | None = None, chunk_size: int = 48) -> dict:
    """在一个行情版本上运行规则。snapshot 需提供 path、row_groups、version_id 与交易日历。"""
    started = time.time()
    calendar = snapshot.calendar[snapshot.calendar <= pd.Timestamp(rule["asof"])]
    codes = sorted(c for c in snapshot.row_groups if c[:2] in rule["markets"])
    daily_path = str(Path(snapshot.path) / "daily.parquet")
    chunks = [_Chunk(daily_path, [(c, snapshot.row_groups[c]) for c in codes[i:i + chunk_size]], rule, calendar.to_numpy())
              for i in range(0, len(codes), chunk_size)]
    h = rule["horizons"]
    sums = np.zeros((len(h), len(calendar)))
    counts = np.zeros((len(h), len(calendar)), dtype=np.int64)
    selected, events, errors, raw, done = [], [], [], 0, 0
    with ProcessPoolExecutor(max_workers=workers or max(1, min(8, (os.cpu_count() or 2) - 1))) as pool:
        futures = [pool.submit(_scan_chunk, c) for c in chunks]
        try:
            for f in futures:
                if should_cancel and should_cancel():
                    raise Cancelled()
                n, sel, ev, err, r, s, k = f.result()
                done += n
                selected.extend(sel); events.extend(ev); errors.extend(err); raw += r
                sums += s; counts += k
                if progress:
                    progress({"done": done, "total": len(codes), "selected_count": len(selected), "event_count": len(events)})
        except Cancelled:
            for f in futures:
                f.cancel()
            raise

    dates = calendar.strftime("%Y-%m-%d")
    baseline: dict[str, dict[str, float]] = {}
    for k, hz in enumerate(h):
        for j in np.flatnonzero(counts[k]):
            baseline.setdefault(dates[j], {})[str(hz)] = sums[k, j] / counts[k, j]
    summary, years = summarize(events, h, baseline)
    selected.sort(key=lambda x: x["amount"], reverse=True)
    events.sort(key=lambda e: (e["date"], e["code"]), reverse=True)
    return {
        "data_version": snapshot.version_id, "rule": rule,
        "summary": summary, "years": years, "selected": selected, "events": events, "errors": errors,
        "raw_signals": raw, "deduplicated_events": len(events), "stocks": len({e["code"] for e in events}),
        "scanned": len(codes), "elapsed": round(time.time() - started, 1),
        "method": METHOD, "reference": REFERENCE, "limitations": LIMITATIONS,
    }


def explain_stock(snapshot, rule: dict, code: str, date: str | None = None) -> dict:
    """单只股票在该规则下的入选日（已去重）以及指定日期每个条件的实际数值。"""
    groups = snapshot.row_groups.get(code)
    if not groups:
        raise KeyError(code)
    pf = pq.ParquetFile(Path(snapshot.path) / "daily.parquet", metadata=snapshot.daily_meta)
    df = to_engine_frame(pf.read_row_groups(groups, columns=FRAME_COLUMNS))
    df = df[df.date <= rule["asof"]].reset_index(drop=True)
    if df.empty:
        return {"code": code, "signal_dates": [], "date": date, "conditions": [], "passed": False}
    ok = eligible(df, rule)
    mask, details = signals(df, rule)
    mask &= ok & (df.date >= rule["start"]) & (code[:2] in rule["markets"])
    kept, previous = [], -100000
    for i in np.flatnonzero(mask.to_numpy()):
        if i - previous > rule["cooldown"]:
            kept.append(df.date.iloc[i].strftime("%Y-%m-%d"))
            previous = i
    day = date or df.date.iloc[-1].strftime("%Y-%m-%d")
    hit = np.flatnonzero((df.date == pd.Timestamp(day)).to_numpy())
    conditions = []
    if len(hit):
        i = int(hit[-1])
        for c, left, right in details:
            conditions.append({"label": c["label"], "op": c["op"], "left": _num(left.iloc[i]), "right": _num(right.iloc[i]),
                               "passed": bool(comparison(left, right, c["op"]).iloc[i])})
    return {"code": code, "signal_dates": kept, "date": day, "conditions": conditions,
            "eligible": bool(len(hit) and ok.iloc[int(hit[-1])]), "passed": bool(len(hit) and mask.iloc[int(hit[-1])])}
