"""文哥选股的历史名单。

导入旧回测用过的名单（旧四象回测库导出的 TSV：日期、代码如 600519.SH、名称、排名）：
    python -m sixiang.picks.wenge_backfill --import-tsv a.tsv b.tsv
按新算法补算某段日子（要有 iFinD 凭证；每周算一次候选池，开盘价用日线里的）：
    python -m sixiang.picks.wenge_backfill --start 2026-09-25 [--end 2026-11-24] [--redo]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from collections import defaultdict

from ..auth.db import make_engine, metadata
from ..config import load_settings
from ..data.ifind import from_ths
from ..data.ifind_sync import client_from_env
from ..data.store import MarketStore
from .service import PickService
from .store import PickStore

STRATEGY = "wenge"


def import_tsv(store: PickStore, market: MarketStore, paths: list[str], redo: bool) -> None:
    days: dict[str, dict[str, int]] = defaultdict(dict)
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for row in csv.reader(f, delimiter="\t"):
                if len(row) >= 4:
                    days[row[0]].setdefault(from_ths(row[1]), int(float(row[3] or 0)))   # 两份名单重叠的日子内容一样，取先读到的
    _, cur = market._current()
    names = dict(cur.execute("SELECT code, name FROM securities").fetchall())
    done = store.days(STRATEGY)
    for day in sorted(days):
        if day in done and not redo:
            continue
        ranked = sorted(days[day].items(), key=lambda kv: (kv[1], kv[0]))
        store.save(STRATEGY, day, [{"rank": i + 1, "code": c, "name": names.get(c) or c} for i, (c, _) in enumerate(ranked)])
    print(f"导入 {len(days)} 天，{min(days)} 到 {max(days)}", flush=True)


def compute(service: PickService, market: MarketStore, start: dt.date, end: dt.date | None, redo: bool) -> None:
    snap, cur = market._current()
    calendar = [d.date() for d in snap.calendar]
    end = end or calendar[-1]
    done = service.store.days(STRATEGY)
    client = client_from_env()
    for day in calendar:
        if not start <= day <= end or (day.isoformat() in done and not redo):
            continue
        prev = [d for d in calendar if d < service._monday(day)]
        service.ensure_pool(client, day, prev[-1] if prev else None)
        o = cur.execute("SELECT code, open FROM daily WHERE date = ? AND open > 0", [day]).df()
        rows = service._fetch_wenge(client, day, dict(zip(o.code, o.open)))
        service.store.save(STRATEGY, day.isoformat(), rows)
        print(f"{day} {len(rows)} 只", flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="文哥选股的历史名单")
    ap.add_argument("--import-tsv", nargs="+", metavar="TSV")
    ap.add_argument("--start", type=dt.date.fromisoformat)
    ap.add_argument("--end", type=dt.date.fromisoformat)
    ap.add_argument("--redo", action="store_true", help="已经有的日子也重来")
    args = ap.parse_args(argv)
    settings = load_settings()
    engine = make_engine(settings.db_url())
    metadata.create_all(engine)
    market = MarketStore(settings.market_dir)
    store = PickStore(engine)
    if args.import_tsv:
        import_tsv(store, market, args.import_tsv, args.redo)
    if args.start:
        compute(PickService(store, market), market, args.start, args.end, args.redo)


if __name__ == "__main__":
    sys.exit(main())
