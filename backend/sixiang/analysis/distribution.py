"""收益分布引擎：一只股票未来 N 个交易日的涨跌分布，以及和“现在相似的时候”的对照。

口径：
- 价格用后复权；起点为某日收盘，终点为该股之后第 N 根日 K 的收盘（停牌日不计入 N）。
- 起点范围：2007-01-01 起、上市满 60 根 K 线之后，且之后还有 N 根 K 线。
- “相似的时候”：用三个当下特征——近 20 日涨跌幅、相对 60 日均线的位置、近 20 日波动率——
  在该股自己的历史里找最接近的若干个起点（标准化后的欧氏距离），数量取 max(200, 全部起点的 10%)，且不超过全部。
- 相邻起点的未来窗口互相重叠，不是独立样本；统计只描述历史，不预测未来。
- 场外期权（100% 平值看涨）：到期收益 = max(涨幅, 0) − 期权费，占名义本金。
- 场外期权持有满 5 个交易日后才能平仓：“中途最高”= 从第 5 个交易日到到期日之间，收盘价最高的那天相对起点的涨幅。
  只看收盘价，不看盘中最高价（日线数据不能冒充盘中）。
- 指数用同一套口径（指数点位本身不需要复权）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ..patterns.study import FRAME_COLUMNS, to_engine_frame

START = pd.Timestamp("2007-01-01")
MIN_BARS = 60
BIN = 0.025
LO, HI = -0.4, 0.6
FEE_CURVE = [round(0.01 + 0.005 * i, 4) for i in range(29)]   # 期权费 1% – 15%，每 0.5% 一档
LOCK = 5                                   # 场外期权买入后要持有满这么多个交易日才能平仓
LADDER = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]


class NotEnoughHistory(ValueError):
    pass


@dataclass
class StockFrame:
    code: str
    name: str
    df: pd.DataFrame


def load(snapshot, code: str) -> StockFrame:
    groups = snapshot.row_groups.get(code)
    if not groups:
        raise KeyError(code)
    pf = pq.ParquetFile(Path(snapshot.path) / "daily.parquet", metadata=snapshot.daily_meta)
    df = to_engine_frame(pf.read_row_groups(groups, columns=FRAME_COLUMNS))
    return StockFrame(code, df["name"].iloc[-1] if len(df) else code, df)


def load_index(store, code: str) -> StockFrame:
    """指数日线 → 引擎使用的格式。指数点位没有复权问题，close 与 raw_close 相同。"""
    data = store.index_daily(code, limit=None)
    df = pd.DataFrame(data["bars"])
    df["date"] = pd.to_datetime(df["date"])
    df["raw_close"] = df["close"]
    df["name"] = data["name"]
    return StockFrame(data["code"], data["name"], df.reset_index(drop=True))


def series(sf: StockFrame) -> dict:
    """画图用：2007 年起每天的收盘（前复权到最新一天，和看盘页一致）。"""
    df = sf.df[sf.df.date >= START - pd.Timedelta(days=120)]
    scale = float(sf.df.raw_close.iloc[-1] / sf.df.close.iloc[-1]) if len(sf.df) else 1.0
    return {"code": sf.code, "name": sf.name, "dates": df.date.dt.strftime("%Y-%m-%d").tolist(),
            "close": [round(float(v) * scale, 3) for v in df.close]}


def features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    ret = close.pct_change()
    return pd.DataFrame({
        "r20": close / close.shift(20) - 1,
        "pos60": close / close.rolling(60, min_periods=60).mean() - 1,
        "vol20": ret.rolling(20, min_periods=20).std() * np.sqrt(252),
    })


def _stats(r: np.ndarray, fee: float | None) -> dict:
    """一组到期涨跌幅的统计；fee 给定时同时给出期权口径。"""
    r = r[np.isfinite(r)]
    if not len(r):
        return {"n": 0}
    out = {"n": int(len(r)), "up_prob": float((r > 0).mean()), "mean": float(r.mean()), "median": float(np.median(r)),
           "p10": float(np.quantile(r, .1)), "p90": float(np.quantile(r, .9))}
    if fee is not None:
        payoff = np.maximum(r, 0) - fee
        out.update({"breakeven_prob": float((r > fee).mean()), "payoff_mean": float(payoff.mean()),
                    "payoff_p10": float(np.quantile(payoff, .1)), "payoff_p90": float(np.quantile(payoff, .9)),
                    "zones": {"down": float((r <= 0).mean()), "up_not_breakeven": float(((r > 0) & (r <= fee)).mean()),
                              "breakeven": float((r > fee).mean())}})
    else:
        out["zones"] = {"down": float((r <= 0).mean()), "up": float((r > 0).mean())}
    edges = np.arange(LO, HI + BIN / 2, BIN)
    counts, _ = np.histogram(np.clip(r, LO, HI - 1e-9), bins=edges)
    out["histogram"] = [{"from": round(float(a), 4), "to": round(float(b), 4), "n": int(c)} for a, b, c in zip(edges[:-1], edges[1:], counts)]
    return out


def _upside(end: np.ndarray, peak: np.ndarray | None, fee: float) -> dict:
    """上涨预期：到期涨多少、（能提前平仓的话）中途最高涨到过多少，以及每一档涨幅有多大可能。"""
    end = end[np.isfinite(end)]
    q = lambda r, p: float(np.quantile(r, p))  # noqa: E731
    out = {"end": {"median": q(end, .5), "p80": q(end, .8), "p90": q(end, .9), "over_fee": float((end > fee).mean())},
           "ladder": [{"x": x, "end": float((end > x).mean())} for x in LADDER], "peak": None}
    if peak is not None:
        peak = peak[np.isfinite(peak)]
        out["peak"] = {"median": q(peak, .5), "p80": q(peak, .8), "p90": q(peak, .9), "over_fee": float((peak > fee).mean())}
        for row in out["ladder"]:
            row["peak"] = float((peak > row["x"]).mean())
    # 花 1 块钱期权费，拿回几块（没扣期权费本身）：一般情况、好的情况、中途最高点卖的一般情况
    back = lambda r: max(r, 0.0) / fee  # noqa: E731
    out["back"] = {"typical": back(out["end"]["median"]), "good": back(out["end"]["p80"]),
                   "peak_typical": back(out["peak"]["median"]) if out["peak"] else None}
    return out


def analyze(sf: StockFrame, horizon: int, fee: float | None = None, asof: str | None = None) -> dict:
    """以 asof（默认最新一根 K 线）为“现在”，返回全部历史与相似时候的分布。"""
    if not 1 <= horizon <= 250:
        raise ValueError("期限需在 1–250 个交易日之间")
    df = sf.df if asof is None else sf.df[sf.df.date <= pd.Timestamp(asof)]
    df = df.reset_index(drop=True)
    if len(df) < MIN_BARS + horizon + 50:
        raise NotEnoughHistory(f"{sf.name} 上市时间太短，历史样本不够")
    feats = features(df)
    now = feats.iloc[-1]
    if now.isna().any():
        raise NotEnoughHistory("最近的行情不完整，无法描述当前状态")

    fwd = (df["close"].shift(-horizon) / df["close"] - 1).to_numpy()
    eligible = (df.index >= MIN_BARS) & (df.date >= START) & np.isfinite(fwd) & feats.notna().all(axis=1).to_numpy()
    idx = np.flatnonzero(eligible)
    if len(idx) < 200:
        raise NotEnoughHistory(f"{sf.name} 可用于统计的历史起点只有 {len(idx)} 个，太少")

    # 相似：标准化后按距离取最近的 k 个
    F = feats.iloc[idx].to_numpy()
    mu, sd = F.mean(axis=0), F.std(axis=0)
    sd[sd == 0] = 1
    dist = np.sqrt((((F - mu) / sd - (now.to_numpy() - mu) / sd) ** 2).sum(axis=1))
    k = int(min(len(idx), max(200, round(len(idx) * .1))))
    near = idx[np.argsort(dist)[:k]]

    vol_hist = feats["vol20"].iloc[idx]
    near_sorted = np.sort(near)
    fee_curve, upside = None, None
    if fee is not None:
        rs, ra = fwd[near], fwd[idx]
        peak = None
        if horizon > LOCK:
            win = horizon - LOCK + 1        # 第 LOCK 天到到期日，一共这么多根 K 线
            peak = (df["close"].rolling(win, min_periods=win).max().shift(-horizon) / df["close"] - 1).to_numpy()
        upside = {"lock": LOCK, "similar": _upside(rs, peak[near] if peak is not None else None, fee),
                  "all": _upside(ra, peak[idx] if peak is not None else None, fee)}
        fee_curve = [{"fee": f, "similar": float((rs > f).mean()), "all": float((ra > f).mean()),
                      "payoff_mean": float((np.maximum(rs, 0) - f).mean())} for f in FEE_CURVE]
    last = df.iloc[-1]
    return {
        "code": sf.code, "name": sf.name, "horizon": horizon, "fee": fee,
        "asof": last.date.strftime("%Y-%m-%d"), "close": float(last.raw_close),
        "state": {"r20": float(now.r20), "pos60": float(now.pos60), "vol20": float(now.vol20),
                  "vol_percentile": float((vol_hist < now.vol20).mean())},
        "sample_range": [df.date.iloc[idx[0]].strftime("%Y-%m-%d"), df.date.iloc[idx[-1]].strftime("%Y-%m-%d")],
        "all": _stats(fwd[idx], fee),
        "similar": _stats(fwd[near], fee),
        "similar_k": k,
        # 每个相似的起点：日期与之后 N 个交易日的涨跌（按日期排序），用于在走势图上标出来
        "similar_points": [[df.date.iloc[i].strftime("%Y-%m-%d"), round(float(fwd[i]), 5)] for i in near_sorted],
        "fee_curve": fee_curve,
        "upside": upside,
        "method": ("后复权价格；从某日收盘到之后第 N 根日 K 收盘（停牌日不计）。“相似的时候”：近 20 日涨跌幅、相对 60 日均线位置、"
                   "近 20 日波动率最接近当下的历史起点。相邻起点的窗口互相重叠，不是独立样本；只描述历史，不预测未来。"
                   + (f" 期权口径：100% 平值看涨，到期收益 = max(涨幅, 0) − 期权费，不含交易成本与报价差异。“中途最高”按收盘价算，从持有满 {LOCK} 个交易日那天起到到期日。" if fee is not None else "")),
    }


def outcome(sf: StockFrame, asof: str, horizon: int) -> dict | None:
    """到期结算：asof 收盘到之后第 N 根 K 线收盘的实际涨跌；尚未走完返回 None。"""
    df = sf.df.reset_index(drop=True)
    hit = np.flatnonzero((df.date == pd.Timestamp(asof)).to_numpy())
    if not len(hit):
        hit = np.flatnonzero((df.date <= pd.Timestamp(asof)).to_numpy())[-1:]
    if not len(hit):
        return None
    i = int(hit[-1])
    if i + horizon >= len(df):
        return {"done": False, "elapsed": len(df) - 1 - i, "horizon": horizon}
    start, end = df.iloc[i], df.iloc[i + horizon]
    return {"done": True, "elapsed": horizon, "horizon": horizon, "start_date": start.date.strftime("%Y-%m-%d"),
            "end_date": end.date.strftime("%Y-%m-%d"), "return": float(end.close / start.close - 1),
            "start_close": float(start.raw_close), "end_close": float(end.raw_close),
            "path": [round(float(v / start.close - 1), 5) for v in df.close.iloc[i:i + horizon + 1]]}
