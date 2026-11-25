"""每日行情同步调度：交易日收盘后自动运行 iFinD 增量同步，结果写入 sync-status.json。

启用：设置环境变量 SIXIANG_SYNC_AT=17:30（北京时间）并配置 iFinD 凭证。
失败时 30 分钟后重试，最多 3 次；仍失败则保留旧版本并记录原因。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
from pathlib import Path

from .ifind_sync import CN_TZ, SyncError, client_from_env, sync

log = logging.getLogger("sixiang.sync")
RETRY_MINUTES = 30
MAX_ATTEMPTS = 3
_run_lock = threading.Lock()


def status_path(market_dir: Path) -> Path:
    return market_dir / "sync-status.json"


def read_status(market_dir: Path) -> dict:
    p = status_path(market_dir)
    status = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"state": "never"}
    status["schedule"] = os.environ.get("SIXIANG_SYNC_AT") or None
    return status


def _write_status(market_dir: Path, **fields) -> None:
    p = status_path(market_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def run_once(market_dir: Path, client=None) -> dict:
    """运行一次同步（同一进程内不并发）。"""
    if not _run_lock.acquire(blocking=False):
        return {"state": "busy", "message": "同步正在进行"}
    started = dt.datetime.now(CN_TZ).isoformat(timespec="seconds")
    try:
        _write_status(market_dir, state="running", started_at=started)
        result = sync(market_dir, client or client_from_env(), log=lambda m: log.info(m))
        summary = {k: result.get(k) for k in ("status", "id", "data_end", "counts", "overlap_check", "elapsed")}
        _write_status(market_dir, state="ok", started_at=started,
                      finished_at=dt.datetime.now(CN_TZ).isoformat(timespec="seconds"), result=summary)
        return {"state": "ok", **summary}
    except Exception as exc:  # 记录失败原因，旧版本继续可用
        kind = "check_failed" if isinstance(exc, SyncError) else "error"
        _write_status(market_dir, state=kind, started_at=started,
                      finished_at=dt.datetime.now(CN_TZ).isoformat(timespec="seconds"), message=str(exc))
        log.exception("行情同步失败")
        return {"state": kind, "message": str(exc)}
    finally:
        _run_lock.release()


def next_run(at: dt.time, now: dt.datetime) -> dt.datetime:
    """下一个工作日的 at 时刻（节假日由同步自身判断“无新数据”）。"""
    candidate = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += dt.timedelta(days=1)
    return candidate


class DailySync:
    def __init__(self, market_dir: Path, at: str):
        hour, minute = (int(x) for x in at.split(":"))
        self.at = dt.time(hour, minute)
        self.market_dir = market_dir
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="daily-sync", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            target = next_run(self.at, dt.datetime.now(CN_TZ))
            log.info("下次行情同步：%s", target.isoformat())
            if self._stop.wait((target - dt.datetime.now(CN_TZ)).total_seconds()):
                return
            for attempt in range(1, MAX_ATTEMPTS + 1):
                result = run_once(self.market_dir)
                if result["state"] in ("ok", "busy") or self._stop.wait(RETRY_MINUTES * 60 if attempt < MAX_ATTEMPTS else 0):
                    break
