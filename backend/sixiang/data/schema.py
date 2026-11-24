"""统一的日线字段规范。所有数据源（PatternLab 基线、iFinD 同步）都先转换成这套字段。

价格一律保存不复权原始值；复权由 adj_factor 计算：
    后复权价 = 原始价 × adj_factor
    前复权价 = 原始价 × adj_factor ÷ 最新 adj_factor
adj_factor 由“前收盘价”推出：第一天为 1，之后每天乘以 昨收 ÷ 今日前收盘价。
"""
from __future__ import annotations

import pyarrow as pa

DAILY_SCHEMA = pa.schema([
    ("code", pa.string()),          # 小写交易所 + 六位代码，如 sz000001
    ("date", pa.date32()),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("prev_close", pa.float64()),   # 交易所前收盘价（已考虑除权）
    ("volume", pa.float64()),       # 股
    ("amount", pa.float64()),       # 元
    ("float_mcap", pa.float64()),   # 流通市值，元
    ("total_mcap", pa.float64()),   # 总市值，元
    ("adj_factor", pa.float64()),
    ("name", pa.string()),          # 当日简称（可能含 ST）
    ("name_verified", pa.bool_()),
    ("sector_l1", pa.string()),     # 申万一级行业
])

SECURITY_SCHEMA = pa.schema([
    ("code", pa.string()),
    ("name", pa.string()),
    ("exchange", pa.string()),      # sh / sz / bj
    ("sector_l1", pa.string()),
    ("first_date", pa.date32()),
    ("last_date", pa.date32()),
    ("rows", pa.int32()),
    ("omitted_prefix_rows", pa.int32()),
])

INDEX_SCHEMA = pa.schema([
    ("code", pa.string()),
    ("date", pa.date32()),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("volume", pa.float64()),
    ("amount", pa.float64()),
])

INDEX_NAMES = {
    "sh000001": "上证指数", "sh000016": "上证50", "sh000300": "沪深300", "sh000680": "科创综指",
    "sh000688": "科创50", "sh000852": "中证1000", "sh000905": "中证500", "sz399006": "创业板指",
    "sz399011": "深证1000", "sz399101": "中小综指", "sz399102": "创业板综", "sz399106": "深证综指",
    "sz399303": "国证2000", "sz399330": "深证100",
}
