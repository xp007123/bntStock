"""收益分布引擎：一只股票未来 N 个交易日的涨跌分布，以及和“现在相似的时候”的对照。

口径：
- 价格用后复权；起点为某日收盘，终点为该股之后第 N 根日 K 的收盘（停牌日不计入 N）。
- 起点范围：2007-01-01 起、上市满 60 根 K 线之后，且之后还有 N 根 K 线。
- “相似的时候”：用三个当下特征——近 20 日涨跌幅、相对 60 日均线的位置、近 20 日波动率——
  在该股自己的历史里找最接近的若干个起点（标准化后的欧氏距离），数量取 max(200, 全部起点的 10%)，且不超过全部。
- 相邻起点的未来窗口互相重叠，不是独立样本；统计只描述历史，不预测未来。
- 场外期权（100% 平值看涨）：到期收益 = max(涨幅, 0) − 期权费，占名义本金。
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
        "method": ("后复权价格；从某日收盘到之后第 N 根日 K 收盘（停牌日不计）。“相似的时候”：近 20 日涨跌幅、相对 60 日均线位置、"
                   "近 20 日波动率最接近当下的历史起点。相邻起点的窗口互相重叠，不是独立样本；只描述历史，不预测未来。"
                   + (" 期权口径：100% 平值看涨，到期收益 = max(涨幅, 0) − 期权费，不含交易成本与报价差异。" if fee is not None else "")),
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
