"""财务报表：导入、按披露时点查询、TTM 与估值（口径迁移自 PatternLab market_view）。

存储：版本目录下 financials.parquet，每只股票一个行组；保留同一报告期的全部修订版本，
查询时只使用“截止日前已披露”的版本（publish_date ≤ 截止日，且 available_from 为空或 ≤ 截止日），
同一报告期取最后一次修订，避免把后来才知道的数据用于历史时点。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# 展示与计算使用的字段（键名去掉 @xbx 后缀）
FIELDS: dict[str, list[tuple[str, str]]] = {
    "income": [
        ("营业总收入", "R_operating_total_revenue"), ("营业收入", "R_revenue"), ("营业总成本", "R_operating_total_cost"),
        ("营业成本", "R_operating_cost"), ("税金及附加", "R_operating_taxes_and_surcharge"), ("销售费用", "R_sales_fee"),
        ("管理费用", "R_manage_fee"), ("研发费用", "R_rad_cost_sum"), ("财务费用", "R_financing_expenses"),
        ("利息费用", "R_interest_fee"), ("利息收入（一般企业）", "R_fc_interest_income"), ("利息净收入", "R_interest_net_income"),
        ("利息收入（金融）", "R_interest_income"), ("手续费及佣金净收入", "R_commi_net_income"), ("营业支出", "R_operating_payout"),
        ("业务及管理费", "R_business_and_manage_fee"), ("资产减值损失", "R_asset_impairment_loss"),
        ("信用减值损失", "R_credit_impairment_loss"), ("公允价值变动收益", "R_fv_chg_income"), ("投资收益", "R_invest_income"),
        ("其他收益", "R_other_income"), ("营业利润", "R_op"), ("营业外收入", "R_non_operating_income"),
        ("营业外支出", "R_nonoperating_cost"), ("利润总额", "R_total_profit"), ("所得税费用", "R_income_tax_cost"),
        ("净利润", "R_np"), ("归母净利润", "R_np_atoopc"), ("少数股东损益", "R_minority_gal"), ("基本每股收益", "R_basic_eps"),
        ("稀释每股收益", "R_dlt_earnings_per_share")],
    "balance": [
        ("货币资金", "B_currency_fund"), ("现金及存放中央银行款项", "B_central_bank_cash_and_deposit"),
        ("存放同业款项", "B_interbank_storage"), ("应收账款", "B_account_receivable"),
        ("应收票据及应收账款", "B_bill_and_account_receivable"), ("存货", "B_inventory"), ("固定资产", "B_fixed_asset"),
        ("固定资产合计", "B_fixed_asset_sum"), ("在建工程合计", "B_construction_in_process_sum"), ("商誉", "B_goodwill"),
        ("流动资产合计", "B_total_current_assets"), ("非流动资产合计", "B_total_noncurrent_assets"), ("资产总计", "B_total_assets"),
        ("负债合计", "B_total_liab"), ("实收资本（或股本）", "B_actual_received_capital"),
        ("归母所有者权益", "B_total_equity_atoopc"), ("少数股东权益", "B_minority_equity"), ("所有者权益合计", "B_total_owner_equity")],
    "cashflow": [
        ("销售商品、提供劳务收到的现金", "C_cash_received_of_sales_service"), ("经营活动现金流入小计", "C_sub_total_of_ci_from_oa"),
        ("经营活动现金流出小计", "C_sub_total_of_cos_from_oa"), ("经营活动现金流量净额", "C_ncf_from_oa"),
        ("购建长期资产支付的现金", "C_cash_paid_for_assets"), ("投资活动现金流量净额", "C_ncf_from_ia"),
        ("筹资活动现金流量净额", "C_ncf_from_fa"), ("现金及现金等价物净增加额", "C_net_increase_in_cce"),
        ("期末现金及现金等价物余额", "C_final_balance_of_cce")],
}
VALUE_KEYS = [k for items in FIELDS.values() for _, k in items]
PER_SHARE = {"R_basic_eps", "R_dlt_earnings_per_share"}

SCHEMA = pa.schema([("code", pa.string()), ("report_date", pa.date32()), ("publish_date", pa.date32()),
                    ("available_from", pa.date32()), ("captured", pa.timestamp("s")), ("statement_format", pa.string()),
                    ("source", pa.string())] + [(k, pa.float64()) for k in VALUE_KEYS])


# ---------------------------------------------------------------- 导入（PatternLab / 邢不行格式）

def read_patternlab_stock(directory: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(directory.glob("*.csv")):
        f = pd.read_csv(path, encoding="gbk", skiprows=1, low_memory=False)
        f["source"] = path.name
        frames.append(f)
    if not frames:
        return pd.DataFrame(columns=SCHEMA.names)
    df = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({
        "code": directory.name.lower(),
        "report_date": pd.to_datetime(df["report_date"].astype(str).str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce"),
        "publish_date": pd.to_datetime(df.get("publish_date"), errors="coerce"),
        "available_from": pd.to_datetime(df["available_from"], errors="coerce") if "available_from" in df else pd.NaT,
        "captured": pd.to_datetime(df.get("抓取时间"), errors="coerce"),
        "statement_format": df.get("statement_format", pd.Series([None] * len(df))).astype("string"),
        "source": df["source"],
    })
    for k in VALUE_KEYS:
        col = k + "@xbx"
        out[k] = pd.to_numeric(df[col], errors="coerce").astype(float) if col in df else np.nan
    # 没有报告期或披露日的行无法做时点判断，不导入
    out = out[out.report_date.notna() & out.publish_date.notna()]
    for c in ("report_date", "publish_date", "available_from"):
        out[c] = out[c].dt.date
    out["captured"] = out["captured"].dt.floor("s")
    return out.sort_values(["report_date", "publish_date"], kind="stable").reset_index(drop=True)


def write_parquet(frames, path: Path) -> int:
    """frames：按股票代码排序的 DataFrame 迭代器；每只股票一个行组。"""
    rows = 0
    with pq.ParquetWriter(path, SCHEMA, compression="zstd") as w:
        for f in frames:
            if len(f):
                w.write_table(pa.Table.from_pandas(f[SCHEMA.names], schema=SCHEMA, preserve_index=False))
                rows += len(f)
    return rows


# ---------------------------------------------------------------- 时点查询

def _finite(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def disclosed(df: pd.DataFrame, asof) -> pd.DataFrame:
    """截止日前已披露的报告，每个报告期取最后一次修订，按报告期倒序。"""
    if df.empty:
        return df
    end = pd.Timestamp(asof).date()
    z = df[(df.report_date <= end) & (df.publish_date <= end)]
    z = z[z.available_from.isna() | (z.available_from <= end)]
    return (z.sort_values(["report_date", "publish_date", "captured", "source"], na_position="first", kind="stable")
             .drop_duplicates("report_date", keep="last").sort_values("report_date", ascending=False))


def summarize(df: pd.DataFrame, asof) -> dict:
    """报告列表（含同比）、TTM 归母净利润、最近年报归母净利润。"""
    z = disclosed(df, asof)
    reports = []
    for _, r in z.iterrows():
        reports.append({"date": r.report_date.isoformat(), "published": r.publish_date.isoformat(),
                        "format": None if pd.isna(r.statement_format) else str(r.statement_format), "source": r.source,
                        "values": {k: _finite(r[k]) for k in VALUE_KEYS}})
    lookup = {r["date"]: r["values"] for r in reports}
    for r in reports:
        prev = lookup.get(str(int(r["date"][:4]) - 1) + r["date"][4:], {})
        r["yoy"] = {k: ((v - prev[k]) / abs(prev[k]) if v is not None and prev.get(k) not in (None, 0) else None)
                    for k, v in r["values"].items()}
    ttm = annual = None
    if reports:
        latest = reports[0]
        d, v = latest["date"], latest["values"]["R_np_atoopc"]
        year = int(d[:4])
        last_annual = lookup.get(f"{year - 1}-12-31", {}).get("R_np_atoopc")
        same_last_year = lookup.get(f"{year - 1}{d[4:]}", {}).get("R_np_atoopc")
        if d.endswith("12-31"):
            ttm = v
        elif None not in (v, last_annual, same_last_year):
            ttm = v + last_annual - same_last_year       # TTM = 本期累计 + 上年年报 − 上年同期累计
        annual = next((r["values"]["R_np_atoopc"] for r in reports if r["date"].endswith("12-31")), None)
    return {"reports": reports, "ttm_profit": ttm, "annual_profit": annual, "asof": str(pd.Timestamp(asof).date())}


def valuation(summary: dict, total_mcap: float | None, float_mcap: float | None, close: float | None) -> dict:
    latest = summary["reports"][0]["values"] if summary["reports"] else {}
    equity = latest.get("B_total_equity_atoopc")
    ttm = summary["ttm_profit"]
    liab, assets = latest.get("B_total_liab"), latest.get("B_total_assets")
    ratio = lambda a, b: a / b if a is not None and b not in (None, 0) else None
    return {
        "total_mcap": total_mcap, "float_mcap": float_mcap,
        "pe_ttm": ratio(total_mcap, ttm) if (ttm or 0) > 0 else None, "ttm_loss": ttm is not None and ttm < 0,
        "pb": ratio(total_mcap, equity) if (equity or 0) > 0 else None,
        "debt_ratio": ratio(liab, assets),
        "total_shares": ratio(total_mcap, close), "float_shares": ratio(float_mcap, close),
    }
