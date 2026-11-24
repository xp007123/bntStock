"""读取 PatternLab（邢不行兼容格式）的日线与指数 CSV，转换为统一字段。

校验规则与 PatternLab 一致：
- 2007-01-01 起出现缺失、非正价格或异常 OHLC：整只股票拒绝导入，不自动修补；
- 2007 年前的坏数据：丢弃最后一个坏行及之前的全部历史，保留之后连续的部分。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

STRICT_PRICE_START = pd.Timestamp("2007-01-01")

DAILY_COLUMNS = {
    "股票代码": "code", "股票名称": "name", "交易日期": "date",
    "开盘价": "open", "最高价": "high", "最低价": "low", "收盘价": "close", "前收盘价": "prev_close",
    "成交量": "volume", "成交额": "amount", "流通市值": "float_mcap", "总市值": "total_mcap",
    "新版申万一级行业名称": "sector_l1", "名称已核验": "name_verified",
}
REQUIRED = {"code", "name", "date", "open", "high", "low", "close", "prev_close", "volume", "amount"}
NUMERIC = ["open", "high", "low", "close", "prev_close", "volume", "amount", "float_mcap", "total_mcap"]


class RejectedFile(Exception):
    """文件不满足校验，整只股票不导入。"""


@dataclass
class ParsedDaily:
    code: str
    frame: pd.DataFrame
    omitted_prefix_rows: int = 0
    notes: list[str] = field(default_factory=list)


def compute_adj_factor(close: pd.Series, prev_close: pd.Series) -> pd.Series:
    """第一天为 1；之后 factor_t = factor_{t-1} × close_{t-1} ÷ prev_close_t。"""
    ratio = (close.shift(1) / prev_close).fillna(1.0)
    ratio.iloc[0] = 1.0
    return ratio.cumprod()


def read_daily(path: Path) -> ParsedDaily:
    code = path.stem.lower()
    df = pd.read_csv(path, encoding="gbk", skiprows=1, usecols=lambda c: c in DAILY_COLUMNS)
    df = df.rename(columns=DAILY_COLUMNS)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise RejectedFile(f"缺少字段 {','.join(sorted(missing))}")
    has_verified_column = "name_verified" in df.columns
    for col in ("float_mcap", "total_mcap", "sector_l1", "name_verified"):
        if col not in df:
            df[col] = np.nan
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    if df["date"].duplicated().any():
        raise RejectedFile("交易日期重复")
    df = df.sort_values("date").reset_index(drop=True)
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    prices = df[["open", "high", "low", "close", "prev_close"]]
    valid = (
        np.isfinite(prices).all(axis=1)
        & (prices > 0).all(axis=1)
        & (df["high"] >= df[["open", "close", "low"]].max(axis=1))
        & (df["low"] <= df[["open", "close", "high"]].min(axis=1))
    )
    if ((~valid) & (df["date"] >= STRICT_PRICE_START)).any():
        first_bad = df.loc[(~valid) & (df["date"] >= STRICT_PRICE_START), "date"].iloc[0]
        raise RejectedFile(f"2007 年起存在缺失、非正价格或异常 OHLC（首个 {first_bad:%Y-%m-%d}）")
    omitted = 0
    notes: list[str] = []
    if not valid.all():
        omitted = int(df.index[~valid][-1]) + 1
        notes.append(f"丢弃 2007 年前 {omitted} 行（截至 {df['date'].iloc[omitted - 1]:%Y-%m-%d}）以保证价格链连续")
        df = df.iloc[omitted:].reset_index(drop=True)
    if df.empty:
        raise RejectedFile("有效行情为空")

    df["code"] = code
    df["adj_factor"] = compute_adj_factor(df["close"], df["prev_close"])
    df["name"] = df["name"].fillna("").astype(str)
    df["sector_l1"] = df["sector_l1"].where(df["sector_l1"].notna(), None)
    # 与 PatternLab 一致：有“名称已核验”列时按 1 判定，缺列时视为已核验
    if has_verified_column:
        df["name_verified"] = pd.to_numeric(df["name_verified"], errors="coerce").fillna(0).eq(1)
    else:
        df["name_verified"] = True
    df["date"] = df["date"].dt.date
    cols = ["code", "date", "open", "high", "low", "close", "prev_close", "volume", "amount",
            "float_mcap", "total_mcap", "adj_factor", "name", "name_verified", "sector_l1"]
    return ParsedDaily(code=code, frame=df[cols], omitted_prefix_rows=omitted, notes=notes)


def read_index(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="gbk")
    df = df.rename(columns={"candle_end_time": "date", "index_code": "code"})
    df["code"] = path.stem.lower()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date")
    ok = (df[["open", "high", "low", "close"]] > 0).all(axis=1) & (df["high"] >= df[["open", "close"]].max(axis=1)) & (df["low"] <= df[["open", "close"]].min(axis=1))
    # 异常 K 线保留原值但不进入快照（与 PatternLab 不展示的处理一致）
    return df.loc[ok, ["code", "date", "open", "high", "low", "close", "volume", "amount"]].reset_index(drop=True)
