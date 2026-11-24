"""把 PatternLab 随包数据导入为行情快照 v0。

用法：
    python -m sixiang.data.baseline_import --source <PatternLab 快照目录>
快照目录下应有 daily/ 与 index/（如 PatternLab/app/runtime/data-store/snapshots/baseline-bundled-20261118）。

只读源文件，不修改原始 CSV。拒绝导入的股票写入 manifest 的 rejected 列表。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import load_settings
from . import versions
from .patternlab_csv import ParsedDaily, RejectedFile, read_daily, read_index
from .schema import DAILY_SCHEMA, INDEX_NAMES, INDEX_SCHEMA, SECURITY_SCHEMA

CALENDAR_SAMPLES = ("sh600000", "sz000001", "sh600519")
DEFAULT_VERSION_ID = "v0-baseline-20261118"


def _parse(path: str) -> tuple[str, ParsedDaily | None, str | None]:
    try:
        return path, read_daily(Path(path)), None
    except RejectedFile as exc:
        return path, None, str(exc)
    except Exception as exc:  # 解析异常同样拒绝，并记录原因
        return path, None, f"{type(exc).__name__}: {exc}"


def import_baseline(source: Path, market_dir: Path, version_id: str, workers: int | None = None, log=print) -> dict:
    daily_dir, index_dir = source / "daily", source / "index"
    if not daily_dir.is_dir():
        raise SystemExit(f"找不到日线目录 {daily_dir}")
    files = sorted(p for p in daily_dir.glob("*.csv") if len(p.stem) == 8 and p.stem[:2].lower() in ("sh", "sz", "bj"))
    if not any(p.stem.lower() in CALENDAR_SAMPLES for p in files):
        raise SystemExit("缺少 sh600000 / sz000001 / sh600519，无法建立交易日历")
    staged = versions.staging_dir(market_dir, version_id)
    log(f"导入 {len(files)} 只股票 → {staged}")

    started = time.time()
    writer = pq.ParquetWriter(staged / "daily.parquet", DAILY_SCHEMA, compression="zstd")
    securities, rejected, notes, calendar = [], [], [], set()
    total_rows = 0
    try:
        with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1)) as pool:
            for i, (path, parsed, error) in enumerate(pool.map(_parse, map(str, files), chunksize=16), 1):
                code = Path(path).stem.lower()
                if error:
                    rejected.append({"code": code, "reason": error})
                else:
                    frame = parsed.frame
                    writer.write_table(pa.Table.from_pandas(frame, schema=DAILY_SCHEMA, preserve_index=False))
                    total_rows += len(frame)
                    last = frame.iloc[-1]
                    securities.append({
                        "code": code, "name": last["name"], "exchange": code[:2],
                        "sector_l1": frame["sector_l1"].dropna().iloc[-1] if frame["sector_l1"].notna().any() else None,
                        "first_date": frame["date"].iloc[0], "last_date": frame["date"].iloc[-1],
                        "rows": len(frame), "omitted_prefix_rows": parsed.omitted_prefix_rows,
                    })
                    if parsed.notes:
                        notes.append({"code": code, "notes": parsed.notes})
                    if code in CALENDAR_SAMPLES:
                        calendar.update(frame["date"])
                if i % 500 == 0 or i == len(files):
                    log(f"  {i}/{len(files)}  用时 {time.time() - started:.0f}s")
    finally:
        writer.close()

    pq.write_table(pa.Table.from_pylist(securities, schema=SECURITY_SCHEMA), staged / "securities.parquet")
    pq.write_table(pa.table({"date": sorted(calendar)}, schema=pa.schema([("date", pa.date32())])), staged / "calendar.parquet")

    index_frames = [read_index(p) for p in sorted(index_dir.glob("*.csv"))] if index_dir.is_dir() else []
    if index_frames:
        pq.write_table(pa.Table.from_pandas(pd.concat(index_frames, ignore_index=True), schema=INDEX_SCHEMA, preserve_index=False),
                       staged / "indices.parquet", compression="zstd")

    data_end = max(s["last_date"] for s in securities)
    manifest = {
        "id": version_id,
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {"kind": "patternlab-bundled", "path": str(source)},
        "data_end": data_end.isoformat(),
        "counts": {
            "securities": len(securities), "daily_rows": total_rows, "rejected": len(rejected),
            "indices": len(index_frames), "calendar_days": len(calendar),
            "active_on_data_end": sum(1 for s in securities if s["last_date"] == data_end),
        },
        "adjustment": "保存不复权原始价；adj_factor 由前收盘价推出，后复权 = 原始价 × adj_factor",
        "index_names": {f["code"].iloc[0]: INDEX_NAMES.get(f["code"].iloc[0], f["code"].iloc[0]) for f in index_frames if len(f)},
        "rejected": rejected,
        "notes": notes,
    }
    versions.write_manifest(staged, manifest)
    versions.publish(market_dir, staged, version_id)
    log(f"已发布 {version_id}：{len(securities)} 只股票，{total_rows} 行，拒绝 {len(rejected)}，数据截至 {data_end}，用时 {time.time() - started:.0f}s")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="导入 PatternLab 随包数据为行情快照")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--version-id", default=DEFAULT_VERSION_ID)
    parser.add_argument("--workers", type=int)
    args = parser.parse_args(argv)
    settings = load_settings()
    import_baseline(args.source.resolve(), settings.market_dir, args.version_id, args.workers)


if __name__ == "__main__":
    sys.exit(main())
