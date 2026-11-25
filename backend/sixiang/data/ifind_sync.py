"""iFinD 增量同步：在当前行情版本之后补齐日线，校验通过后发布新版本。

流程：
1. 以当前版本为基础，向 iFinD 拉取 [数据末日, 目标日] 的不复权日线（含末日用于交叉核对）；
2. 交叉核对：末日的收盘、前收、成交量、成交额与已有数据比较，不一致比例超过阈值则中止，不发布；
3. 基础版本中没有的股票（新上市或基线遗漏）补齐全部历史；
4. 新交易日逐日获取简称（含 ST/退）与申万一级行业；逐只追加新行，延续复权因子；异常行情的股票本次不更新并记录原因；新上市股票加入；
5. 写入暂存目录，生成 manifest，原子切换为当前版本。旧版本保留。

用法：python -m sixiang.data.ifind_sync [--end YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import load_settings
from . import versions
from .ifind import INDEX_DAILY, STOCK_DAILY, IFindClient
from .schema import DAILY_SCHEMA, INDEX_SCHEMA, SECURITY_SCHEMA
from .store import MarketStore

CALENDAR_SAMPLES = ("sh600000", "sz000001", "sh600519")
CN_TZ = dt.timezone(dt.timedelta(hours=8))
DAILY_READY_HOUR = 16          # 收盘数据在 16:00 后才视为完整
STOCK_BATCH = 100
NAME_BATCH = 400
MAX_OVERLAP_MISMATCH = 0.01    # 末日交叉核对允许的不一致比例
MIN_OVERLAP_CHECKED = 1000     # 末日交叉核对至少覆盖的股票数
HISTORY_START = "1990-01-01"


class SyncError(RuntimeError):
    pass


def default_end(now: dt.datetime | None = None) -> dt.date:
    now = now or dt.datetime.now(CN_TZ)
    return now.date() if now.hour >= DAILY_READY_HOUR else now.date() - dt.timedelta(days=1)


def _close(a, b, rel=1e-6, abs_=1e-6) -> bool:
    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b):
        return False
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def _valid_rows(df: pd.DataFrame) -> pd.Series:
    p = df[["open", "high", "low", "close", "prev_close"]]
    return (np.isfinite(p).all(axis=1) & (p > 0).all(axis=1)
            & (df.high >= df[["open", "close", "low"]].max(axis=1))
            & (df.low <= df[["open", "close", "high"]].min(axis=1)))


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={"preClose": "prev_close", "floatCapitalOfAShares": "float_mcap", "totalCapital": "total_mcap"})
    for c in ("open", "high", "low", "close", "prev_close", "volume", "amount", "float_mcap", "total_mcap"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce").astype(float)
    # 停牌日不记录（与基线一致：缺失停牌日不补价）
    return df[df["close"].notna() & (df["volume"].fillna(0) > 0)].reset_index(drop=True)


def sync(market_dir: Path, client: IFindClient, end: dt.date | None = None, dry_run: bool = False, log=print) -> dict:
    started = time.time()
    store = MarketStore(market_dir)
    base = store.snapshot()
    base_end = dt.date.fromisoformat(base.data_end)
    end = end or default_end()
    if end <= base_end:
        log(f"数据已是最新（{base.data_end}），无需同步")
        return {"status": "up_to_date", "data_end": base.data_end}

    pf = pq.ParquetFile(base.path / "daily.parquet", metadata=base.daily_meta)
    securities = pq.read_table(base.path / "securities.parquet").to_pandas()
    recent = securities[securities.last_date >= base_end - dt.timedelta(days=400)].code.tolist()
    universe = client.universe(end.isoformat())
    codes = sorted(set(universe) | set(recent))
    log(f"同步 {base.data_end} → {end}：请求 {len(codes)} 只（全部A股 {len(universe)}，近一年有行情 {len(recent)}）")

    # 1. 拉取日线（含基础版本末日用于核对）
    fetched: dict[str, pd.DataFrame] = {}
    for i in range(0, len(codes), STOCK_BATCH):
        part = client.history(codes[i:i + STOCK_BATCH], base_end.isoformat(), end.isoformat(), STOCK_DAILY)
        fetched.update({c: _normalize(f) for c, f in part.items()})
        if (i // STOCK_BATCH) % 10 == 0:
            log(f"  日线 {min(i + STOCK_BATCH, len(codes))}/{len(codes)}")

    # 2. 末日交叉核对
    checked, mismatched = 0, []
    for code, frame in fetched.items():
        groups = base.row_groups.get(code)
        new_row = frame[frame.date == base_end]
        if not groups or new_row.empty:
            continue
        old = pf.read_row_group(groups[-1], columns=["date", "close", "prev_close", "volume", "amount"]).to_pandas()
        old = old[old.date == base_end]
        if old.empty:
            continue
        checked += 1
        a, b = old.iloc[0], new_row.iloc[0]
        diffs = [f for f in ("close", "prev_close", "volume") if not _close(a[f], b[f])]
        if not _close(a["amount"], b["amount"], rel=1e-6, abs_=1.0):
            diffs.append("amount")
        if diffs:
            mismatched.append({"code": code, "fields": diffs})
    ratio = len(mismatched) / max(1, checked)
    log(f"末日核对：{checked} 只，不一致 {len(mismatched)}（{ratio:.2%}）")
    if checked < MIN_OVERLAP_CHECKED or ratio > MAX_OVERLAP_MISMATCH:
        raise SyncError(f"末日交叉核对未通过：核对 {checked} 只，不一致 {len(mismatched)}；未发布新版本")

    # 3. 基础版本中没有的股票（新上市，或基线数据源遗漏的近期上市股）补齐全部历史
    added = sorted(c for c in fetched if c not in base.row_groups)
    full_history: dict[str, pd.DataFrame] = {}
    for i in range(0, len(added), STOCK_BATCH):
        part = client.history(added[i:i + STOCK_BATCH], HISTORY_START, end.isoformat(), STOCK_DAILY)
        full_history.update({c: _normalize(f) for c, f in part.items()})
    if added:
        log(f"补齐 {len(added)} 只基础版本中没有的股票的全部历史")

    # 4. 新交易日的简称与行业
    new_rows = {c: (full_history[c] if c in full_history else f[f.date > base_end]).reset_index(drop=True) for c, f in fetched.items()}
    new_rows = {c: f for c, f in new_rows.items() if len(f)}
    new_dates = sorted({d for f in new_rows.values() for d in f.date if d > base_end})
    if not new_dates:
        log("iFinD 暂无新交易日数据")
        return {"status": "no_new_data", "data_end": base.data_end}
    names: dict[tuple[str, dt.date], tuple[str | None, str | None]] = {}
    for d in new_dates:
        day_codes = sorted(c for c, f in new_rows.items() if (f.date == d).any())
        for i in range(0, len(day_codes), NAME_BATCH):
            for c, v in client.names(day_codes[i:i + NAME_BATCH], d.isoformat()).items():
                names[(c, d)] = v
    log(f"新交易日 {len(new_dates)} 天：{new_dates[0]} … {new_dates[-1]}")

    # 5. 合并写入暂存版本
    version_id = f"ifind-{new_dates[-1]:%Y%m%d}"
    if versions.version_path(market_dir, version_id).exists():
        version_id += time.strftime("-%H%M%S")
    staged = versions.staging_dir(market_dir, version_id)
    writer = pq.ParquetWriter(staged / "daily.parquet", DAILY_SCHEMA, compression="zstd")
    out_secs, rejected, listed, appended = [], [], [], 0
    sec_by_code = securities.set_index("code")
    try:
        for code in sorted(set(base.row_groups) | set(new_rows)):
            old = pf.read_row_groups(base.row_groups[code]).to_pandas() if code in base.row_groups else None
            add = new_rows.get(code)
            if add is not None:
                bad = ~_valid_rows(add)
                if bad.any():
                    rejected.append({"code": code, "reason": f"{int(bad.sum())} 行异常 OHLC，本次未更新", "dates": [str(d) for d in add.date[bad]]})
                    add = None
            if add is not None:
                add = add.copy()
                add["code"] = code
                nm = [names.get((code, d), (None, None)) for d in add.date]
                known = [n for n, _ in nm if n]
                last_name = old["name"].iloc[-1] if old is not None and len(old) else (known[0] if known else "")
                add["name"] = [n or last_name for n, _ in nm]
                add["name_verified"] = [n is not None for n, _ in nm]
                add["sector_l1"] = [s for _, s in nm]
                if old is not None and len(old):
                    prev_close_series = pd.concat([old["close"].iloc[-1:], add["close"].iloc[:-1]], ignore_index=True)
                    ratio_ = (prev_close_series.to_numpy() / add["prev_close"].to_numpy())
                    add["adj_factor"] = old["adj_factor"].iloc[-1] * np.cumprod(ratio_)
                else:
                    listed.append({"code": code, "first_date": str(add["date"].iloc[0]), "rows": len(add)})
                    ratio_ = np.r_[1.0, add["close"].to_numpy()[:-1] / add["prev_close"].to_numpy()[1:]]
                    add["adj_factor"] = np.cumprod(ratio_)
                frame = pd.concat([old, add[old.columns if old is not None else DAILY_SCHEMA.names]], ignore_index=True) if old is not None else add[DAILY_SCHEMA.names]
                appended += len(add)
            else:
                frame = old
            if frame is None or frame.empty:
                continue
            writer.write_table(pa.Table.from_pandas(frame[DAILY_SCHEMA.names], schema=DAILY_SCHEMA, preserve_index=False))
            prev = sec_by_code.loc[code] if code in sec_by_code.index else None
            known_sector = frame["sector_l1"].dropna()
            out_secs.append({"code": code, "name": frame["name"].iloc[-1], "exchange": code[:2],
                             "sector_l1": known_sector.iloc[-1] if len(known_sector) else None,
                             "first_date": frame["date"].iloc[0], "last_date": frame["date"].iloc[-1], "rows": len(frame),
                             "omitted_prefix_rows": int(prev["omitted_prefix_rows"]) if prev is not None else 0})
    finally:
        writer.close()
    pq.write_table(pa.Table.from_pylist(out_secs, schema=SECURITY_SCHEMA), staged / "securities.parquet")

    calendar = set(pq.read_table(base.path / "calendar.parquet")["date"].to_pylist())
    for c in CALENDAR_SAMPLES:
        if c in new_rows:
            calendar.update(new_rows[c].date)
    pq.write_table(pa.table({"date": sorted(calendar)}, schema=pa.schema([("date", pa.date32())])), staged / "calendar.parquet")

    # 指数
    old_idx = pq.read_table(base.path / "indices.parquet").to_pandas()
    idx_codes = sorted(old_idx.code.unique())
    idx_new = client.history(idx_codes, (base_end + dt.timedelta(days=1)).isoformat(), end.isoformat(), INDEX_DAILY, adjusted=True)
    frames = [old_idx]
    for code, f in idx_new.items():
        f = f.copy(); f["code"] = code
        for c in ("open", "high", "low", "close", "volume", "amount"):
            f[c] = pd.to_numeric(f[c], errors="coerce").astype(float)
        frames.append(f[f.close.notna()][INDEX_SCHEMA.names])
    idx = pd.concat(frames, ignore_index=True).sort_values(["code", "date"])
    pq.write_table(pa.Table.from_pandas(idx, schema=INDEX_SCHEMA, preserve_index=False), staged / "indices.parquet", compression="zstd")

    # 财务数据本次不变，沿用基础版本（硬链接）
    fin = base.path / "financials.parquet"
    if fin.exists():
        try:
            os.link(fin, staged / "financials.parquet")
        except OSError:
            shutil.copy2(fin, staged / "financials.parquet")

    data_end = max(s["last_date"] for s in out_secs)
    manifest = {
        "id": version_id,
        "created_at": dt.datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "source": {"kind": "ifind-incremental", "base_version": base.version_id, "requested_end": end.isoformat()},
        "data_end": data_end.isoformat(),
        "counts": {"securities": len(out_secs), "daily_rows": int(base.manifest["counts"]["daily_rows"]) + appended,
                   "appended_rows": appended, "new_trading_days": len(new_dates), "added_securities": len(listed),
                   "rejected": len(rejected), "indices": int(idx.code.nunique()), "calendar_days": len(calendar),
                   "active_on_data_end": sum(1 for s in out_secs if s["last_date"] == data_end)},
        "adjustment": base.manifest["adjustment"],
        "index_names": base.manifest.get("index_names", {}),
        "financials": base.manifest.get("financials"),
        "overlap_check": {"date": base.data_end, "checked": checked, "mismatched": len(mismatched), "examples": mismatched[:20]},
        "added_securities": listed,  # 早于本次窗口的历史行未逐日核验简称（name_verified=False）
        "rejected": rejected,
        "ifind_calls": client.calls,
        "elapsed": round(time.time() - started, 1),
    }
    versions.write_manifest(staged, manifest)
    if dry_run:
        log(f"试运行完成，未发布。暂存目录：{staged}")
        return {"status": "dry_run", **manifest}
    versions.publish(market_dir, staged, version_id)
    log(f"已发布 {version_id}：新增 {appended} 行、{len(new_dates)} 个交易日、新增证券 {len(listed)}、拒绝 {len(rejected)}，"
        f"数据截至 {data_end}，iFinD 调用 {client.calls} 次，用时 {manifest['elapsed']}s")
    return {"status": "published", **manifest}


def client_from_env() -> IFindClient:
    import os
    return IFindClient(refresh_token=os.environ.get("SIXIANG_IFIND_REFRESH_TOKEN") or None,
                       access_token=os.environ.get("SIXIANG_IFIND_ACCESS_TOKEN") or None)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="iFinD 增量同步日线")
    ap.add_argument("--end", type=dt.date.fromisoformat)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    settings = load_settings()
    sync(settings.market_dir, client_from_env(), args.end, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
