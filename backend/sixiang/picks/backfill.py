"""回填历史名单：python -m sixiang.picks.backfill --start 2026-01-07 [--end 2026-11-24] [--redo]"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

from ..auth.db import make_engine
from ..config import load_settings
from ..data.ifind_sync import client_from_env
from ..data.store import MarketStore
from .store import PickStore
from .wencai import ask, parse_sjm, sjm_query

STRATEGY = "sjm"


def fetch_day(client, calendar: list[dt.date], day: dt.date) -> list[dict]:
    """取某个交易日的三角猫名单。calendar 是升序的交易日，要包含 day 前面两天。"""
    i = calendar.index(day)
    if i < 2:
        raise ValueError(f"{day} 前面不够两个交易日")
    prev, prev2 = calendar[i - 1], calendar[i - 2]
    return parse_sjm(ask(client, sjm_query(day, prev, prev2)), day, prev)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="回填三角猫历史名单")
    ap.add_argument("--start", type=dt.date.fromisoformat, required=True)
    ap.add_argument("--end", type=dt.date.fromisoformat)
    ap.add_argument("--redo", action="store_true", help="已经取过的日子也重取")
    args = ap.parse_args(argv)
    settings = load_settings()
    snap = MarketStore(settings.market_dir).snapshot()
    calendar = [d.date() for d in snap.calendar]
    store = PickStore(make_engine(settings.db_url()))
    done = store.days(STRATEGY)
    end = args.end or calendar[-1]
    client = client_from_env()
    for day in calendar:
        if not args.start <= day <= end or (day.isoformat() in done and not args.redo):
            continue
        try:
            rows = fetch_day(client, calendar, day)
        except Exception as exc:  # noqa: BLE001  一天失败不影响别的天，下次再跑会补
            print(f"{day} 失败：{exc}", flush=True)
            continue
        store.save(STRATEGY, day.isoformat(), rows)
        print(f"{day} {len(rows)} 只", flush=True)
        time.sleep(0.4)


if __name__ == "__main__":
    sys.exit(main())
