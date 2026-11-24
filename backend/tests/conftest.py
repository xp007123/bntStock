"""测试用的小型 PatternLab 格式数据。"""
from __future__ import annotations

from pathlib import Path

import pytest

HEADER = "股票代码,股票名称,交易日期,开盘价,最高价,最低价,收盘价,前收盘价,成交量,成交额,流通市值,总市值,新版申万一级行业名称,名称已核验,数据来源"


def write_daily(path: Path, code: str, name: str, rows: list[tuple]) -> None:
    lines = ["Pattern Lab 测试数据", HEADER]
    for date, o, h, lo, c, prev in rows:
        lines.append(f"{code},{name},{date},{o},{h},{lo},{c},{prev},1000,10000,1e9,2e9,银行,1,test")
    path.write_bytes(("\n".join(lines) + "\n").encode("gbk"))


@pytest.fixture
def source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "daily").mkdir(parents=True)
    (src / "index").mkdir()
    # 第 3 天除权：前收盘价 5.0（昨收 10.0），复权因子应翻倍
    write_daily(src / "daily" / "sz000001.csv", "sz000001", "平安银行", [
        ("2026-11-16", 10, 10.5, 9.8, 10.0, 9.9),
        ("2026-11-17", 10, 10.2, 9.9, 10.0, 10.0),
        ("2026-11-18", 5.0, 5.3, 4.9, 5.2, 5.0),
    ])
    write_daily(src / "daily" / "sh600000.csv", "sh600000", "浦发银行", [
        ("2026-11-16", 8, 8.2, 7.9, 8.1, 8.0),
        ("2026-11-17", 8.1, 8.3, 8.0, 8.2, 8.1),
        ("2026-11-18", 8.2, 8.4, 8.1, 8.3, 8.2),
    ])
    # 2007 年后最高价低于收盘价：整只拒绝
    write_daily(src / "daily" / "sz000002.csv", "sz000002", "万科A", [
        ("2026-11-17", 8, 8.2, 7.9, 8.1, 8.0),
        ("2026-11-18", 8.1, 8.0, 7.9, 8.3, 8.1),
    ])
    # 2007 年前有坏行：丢弃该行及之前
    write_daily(src / "daily" / "sh600519.csv", "sh600519", "贵州茅台", [
        ("2001-08-27", 0, 0, 0, 0, 0),
        ("2001-08-28", 35, 37, 34, 36, 35),
        ("2026-11-18", 1500, 1510, 1490, 1505, 1500),
    ])
    (src / "index" / "sh000001.csv").write_bytes(
        ("candle_end_time,open,high,low,close,amount,volume,index_code\n"
         "2026-11-17,3500,3520,3490,3510,1e11,1e8,sh000001\n"
         "2026-11-18,3510,3530,3500,3521.1,1e11,1e8,sh000001\n").encode("gbk"))
    return src
