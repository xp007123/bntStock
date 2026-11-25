"""形态研究任务：提交、排队、运行、取消、读取结果。

M1 采用文件存储（data/research/jobs/<id>/meta.json、result.json）；业务数据库确定后迁移。
任务按提交顺序逐个运行（全市场扫描本身已多进程并行）。每个任务固定在提交时的行情版本上。
同一规则在同一数据版本上已有完成结果时直接复用，不重复计算。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..data.store import MarketStore
from ..patterns.rules import validate_rule
from ..patterns.study import Cancelled, run_study

ACTIVE = ("queued", "running")


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _save(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_clean(obj), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def rule_hash(rule: dict) -> str:
    return hashlib.sha256(json.dumps(rule, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


class JobError(ValueError):
    pass


class JobManager:
    def __init__(self, root: Path, market: MarketStore, workers: int | None = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.market = market
        self.workers = workers
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._cancel: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pattern-job")
        self._results: dict[str, dict] = {}
        for p in self.root.glob("*/meta.json"):
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if meta.get("status") in ACTIVE:
                meta.update(status="interrupted", message="服务重启，任务未完成；可重新运行")
                _save(p, meta)
            self._jobs[meta["id"]] = meta

    # ---------------------------------------------------------- 提交
    def submit(self, raw: dict, owner: int | None = None, context: dict | None = None) -> dict:
        snap = self.market.snapshot()
        rule = validate_rule(raw, snap.data_end)
        digest = rule_hash(rule)
        with self._lock:
            for m in sorted(self._jobs.values(), key=lambda j: j["created"], reverse=True):
                if (m["rule_hash"] == digest and m["data_version"] == snap.version_id and m.get("owner") == owner
                        and m["status"] in ("completed", *ACTIVE)):
                    return {**m, "reused": True}
            jid = uuid.uuid4().hex[:12]
            (self.root / jid).mkdir()
            meta = {"id": jid, "name": rule["name"], "status": "queued", "progress": 0.0, "done": 0, "total": 0,
                    "selected_count": 0, "event_count": 0, "message": "排队等待",
                    "created": time.strftime("%Y-%m-%d %H:%M:%S"), "rule": rule, "rule_hash": digest,
                    "data_version": snap.version_id, "data_end": snap.data_end, "owner": owner, **(context or {})}
            self._jobs[jid] = meta
            _save(self.root / jid / "meta.json", meta)
        self._executor.submit(self._run, jid)
        return dict(meta)

    def _run(self, jid: str) -> None:
        meta = self._jobs[jid]
        if jid in self._cancel:
            self._finish(jid, status="cancelled", message="已取消")
            return
        try:
            snap = self.market.snapshot()
            if snap.version_id != meta["data_version"]:
                raise JobError("行情数据已更新，请重新提交以使用新数据")
            meta.update(status="running", message="扫描全市场")
            started = time.time()

            def progress(p: dict) -> None:
                meta.update(done=p["done"], total=p["total"], selected_count=p["selected_count"], event_count=p["event_count"],
                            progress=round(p["done"] / max(1, p["total"]) * 100, 1),
                            message=f"已扫描 {p['done']:,} / {p['total']:,} 只股票")

            result = run_study(snap, meta["rule"], progress=progress, should_cancel=lambda: jid in self._cancel, workers=self.workers)
            _save(self.root / jid / "result.json", result)
            self._finish(jid, status="completed", progress=100.0, message="选股与历史复盘已完成",
                         elapsed=round(time.time() - started, 1), selected_count=len(result["selected"]),
                         event_count=len(result["events"]), errors=len(result["errors"]))
        except Cancelled:
            self._finish(jid, status="cancelled", message="已取消，未保存不完整结果")
        except Exception as exc:  # 失败原因如实写入任务
            self._finish(jid, status="failed", message=str(exc))

    def _finish(self, jid: str, **fields) -> None:
        with self._lock:
            self._jobs[jid].update(fields)
            _save(self.root / jid / "meta.json", self._jobs[jid])
            self._cancel.discard(jid)

    # ---------------------------------------------------------- 查询
    def get(self, jid: str) -> dict:
        with self._lock:
            if jid not in self._jobs:
                raise KeyError(jid)
            return json.loads(json.dumps(_clean(self._jobs[jid])))

    def list(self, owner: int | None = None) -> list[dict]:
        """owner 为 None 时返回全部（管理员）；否则只返回该用户的研究。"""
        with self._lock:
            items = [{k: v for k, v in m.items() if k != "rule"} | {"conditions": len(m["rule"]["conditions"])}
                     for m in self._jobs.values() if owner is None or m.get("owner") == owner]
        return sorted(_clean(items), key=lambda j: j["created"], reverse=True)

    def cancel(self, jid: str) -> dict:
        with self._lock:
            meta = self.get(jid)
            if meta["status"] in ACTIVE:
                self._cancel.add(jid)
                self._jobs[jid]["message"] = "正在取消…"
        return self.get(jid)

    def result(self, jid: str) -> dict:
        meta = self.get(jid)
        if meta["status"] != "completed":
            raise JobError("任务尚未完成")
        with self._lock:
            if jid not in self._results:
                if len(self._results) > 8:
                    self._results.pop(next(iter(self._results)))
                self._results[jid] = json.loads((self.root / jid / "result.json").read_text(encoding="utf-8"))
            return self._results[jid]

    def shutdown(self) -> None:
        with self._lock:
            self._cancel.update(j for j, m in self._jobs.items() if m["status"] in ACTIVE)
        self._executor.shutdown(wait=False, cancel_futures=True)
