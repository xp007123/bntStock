"""把 PatternLab 随包财务数据导入当前行情版本，发布为新版本（行情文件以硬链接复用）。

用法：python -m sixiang.data.financial_import --source <PatternLab 快照>/financial
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..config import load_settings
from . import versions
from .financials import read_patternlab_stock, write_parquet


def _read(path: str):
    try:
        return read_patternlab_stock(Path(path)), None
    except Exception as exc:  # 单只异常不影响整体，记录原因
        return None, f"{type(exc).__name__}: {exc}"


def import_financials(source: Path, market_dir: Path, workers: int | None = None, log=print) -> dict:
    base_id = versions.current_version_id(market_dir)
    if not base_id:
        raise SystemExit("请先导入行情数据")
    base = versions.read_manifest(market_dir, base_id)
    dirs = sorted(p for p in source.iterdir() if p.is_dir() and len(p.name) == 8 and p.name[:2] in ("sh", "sz", "bj"))
    version_id = f"{base_id}-fin"
    staged = versions.stage_from(market_dir, base_id, version_id, skip=("financials.parquet",))
    started = time.time()
    errors, stocks = [], 0

    def frames():
        nonlocal stocks
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for i, (d, (frame, err)) in enumerate(zip(dirs, pool.map(_read, map(str, dirs), chunksize=16)), 1):
                if err:
                    errors.append({"code": d.name, "reason": err})
                elif len(frame):
                    stocks += 1
                    yield frame
                if i % 1000 == 0 or i == len(dirs):
                    log(f"  财务 {i}/{len(dirs)}  用时 {time.time() - started:.0f}s")

    rows = write_parquet(frames(), staged / "financials.parquet")
    manifest = {**base, "id": version_id, "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "source": {**base.get("source", {}), "financial": {"kind": "patternlab-bundled", "path": str(source), "base_version": base_id}},
                "financials": {"stocks": stocks, "rows": rows, "errors": errors[:50], "error_count": len(errors),
                               "point_in_time": "按披露日与 available_from 过滤；保留全部修订"}}
    versions.write_manifest(staged, manifest)
    versions.publish(market_dir, staged, version_id)
    log(f"已发布 {version_id}：财务 {stocks} 只、{rows} 行，异常 {len(errors)}，用时 {time.time() - started:.0f}s")
    return manifest


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="导入 PatternLab 随包财务数据")
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--workers", type=int)
    args = ap.parse_args(argv)
    import_financials(args.source.resolve(), load_settings().market_dir, args.workers)


if __name__ == "__main__":
    sys.exit(main())
