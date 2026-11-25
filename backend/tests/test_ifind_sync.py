from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from sixiang.data import versions
from sixiang.data.baseline_import import import_baseline
from sixiang.data.ifind import from_ths, to_ths
from sixiang.data.ifind_sync import SyncError, default_end, sync
from sixiang.data.scheduler import missed_today, next_run
from sixiang.data.store import MarketStore

from .conftest import write_daily

D = pd.Timestamp


class FakeIFind:
    """按代码给出日线；names 返回带 ST 的简称以验证逐日名称。"""

    def __init__(self, bars: dict[str, list[tuple]], universe: list[str]):
        self.bars = bars
        self._universe = universe
        self.calls = 0

    def universe(self, date):
        self.calls += 1
        return self._universe

    def history(self, codes, start, end, indicators, adjusted=False):
        self.calls += 1
        out = {}
        for c in codes:
            rows = [r for r in self.bars.get(c, []) if start <= r[0] <= end]
            if rows:
                if "preClose" in indicators:
                    out[c] = pd.DataFrame([{"date": D(r[0]).date(), "open": r[1], "high": r[2], "low": r[3], "close": r[4], "preClose": r[5],
                                            "volume": 1000.0, "amount": 10000.0, "floatCapitalOfAShares": 1e9, "totalCapital": 2e9} for r in rows])
                else:
                    out[c] = pd.DataFrame([{"date": D(r[0]).date(), "open": r[1], "high": r[2], "low": r[3], "close": r[4],
                                            "volume": 1.0, "amount": 1.0} for r in rows])
        return out

    def names(self, codes, date):
        self.calls += 1
        return {c: ("*ST平安" if c == "sz000001" and date >= "2026-11-20" else "名称", "银行") for c in codes}


def _base(tmp_path: Path, source: Path) -> Path:
    market = tmp_path / "m"
    import_baseline(source, market, "v0", workers=1, log=lambda *_: None)
    return market


# 与 conftest 基线 11-18 一致的重叠行，以及之后的新行
PINGAN = [("2026-11-18", 5.0, 5.3, 4.9, 5.2, 5.0), ("2026-11-19", 5.2, 5.4, 5.1, 5.3, 5.2),
          ("2026-11-20", 2.7, 2.8, 2.6, 2.7, 2.65)]  # 11-20 除权：前收 2.65（昨收 5.3）
PUFA = [("2026-11-18", 8.2, 8.4, 8.1, 8.3, 8.2), ("2026-11-19", 8.3, 8.5, 8.2, 8.4, 8.3), ("2026-11-20", 8.4, 8.6, 8.3, 8.5, 8.4)]
MAOTAI = [("2026-11-18", 1500, 1510, 1490, 1505, 1500), ("2026-11-19", 1505, 1520, 1500, 1510, 1505)]
NEW = [("2026-10-09", 20, 22, 19, 21, 10), ("2026-11-18", 21, 22, 20, 21.5, 21), ("2026-11-20", 21.5, 23, 21, 22, 21.5)]


def test_too_few_checked_aborts(tmp_path: Path, source: Path):
    """默认要求末日核对至少 1000 只；样本不足时不发布。"""
    market = _base(tmp_path, source)
    fake = FakeIFind({"sz000001": PINGAN, "sh600000": PUFA, "sh600519": MAOTAI}, ["sz000001", "sh600000", "sh600519"])
    with pytest.raises(SyncError, match="交叉核对"):
        sync(market, fake, dt.date(2026, 11, 20), log=lambda *_: None)
    assert versions.current_version_id(market) == "v0"


def test_sync_end_to_end(tmp_path: Path, source: Path, monkeypatch):
    import sixiang.data.ifind_sync as mod
    monkeypatch.setattr(mod, "MIN_OVERLAP_CHECKED", 1)
    market = _base(tmp_path, source)
    fake = FakeIFind({"sz000001": PINGAN, "sh600000": PUFA, "sh600519": MAOTAI, "sz301716": NEW,
                      "sh000001": [("2026-11-19", 3520, 3530, 3500, 3525, 0)]},
                     ["sz000001", "sh600000", "sh600519", "sz301716"])
    result = sync(market, fake, dt.date(2026, 11, 20), log=lambda *_: None)
    assert result["status"] == "published" and result["data_end"] == "2026-11-20"
    assert result["overlap_check"]["mismatched"] == 0
    assert [a["code"] for a in result["added_securities"]] == ["sz301716"]

    store = MarketStore(market)
    raw = store.daily("sz000001", adjust="none")["bars"]
    hfq = store.daily("sz000001", adjust="hfq")["bars"]
    assert [b["date"] for b in raw[-3:]] == ["2026-11-18", "2026-11-19", "2026-11-20"]
    # 基线因子 2（11-18 除权）；11-20 再除权：× 5.3/2.65 = 2 → 4
    assert hfq[-1]["close"] == pytest.approx(2.7 * 4)
    assert raw[-1]["name"] == "*ST平安"
    added = store.daily("sz301716", adjust="none")["bars"]
    assert added[0]["date"] == "2026-10-09" and len(added) == 3
    assert store.indices()[0]["date"] == "2026-11-19"
    assert sync(market, fake, dt.date(2026, 11, 20), log=lambda *_: None)["status"] == "up_to_date"


def test_overlap_mismatch_aborts(tmp_path: Path, source: Path, monkeypatch):
    import sixiang.data.ifind_sync as mod
    monkeypatch.setattr(mod, "MIN_OVERLAP_CHECKED", 1)
    market = _base(tmp_path, source)
    wrong = [("2026-11-18", 5.0, 5.3, 4.9, 5.25, 5.0)] + PINGAN[1:]   # 末日收盘与基线不一致
    fake = FakeIFind({"sz000001": wrong, "sh600000": PUFA, "sh600519": MAOTAI}, ["sz000001", "sh600000", "sh600519"])
    with pytest.raises(SyncError):
        sync(market, fake, dt.date(2026, 11, 20), log=lambda *_: None)
    assert versions.current_version_id(market) == "v0"


def test_code_conversion_and_dates():
    assert to_ths("sh600519") == "600519.SH" and from_ths("920000.BJ") == "bj920000"
    cn = dt.timezone(dt.timedelta(hours=8))
    assert default_end(dt.datetime(2026, 11, 25, 15, 59, tzinfo=cn)) == dt.date(2026, 11, 24)
    assert default_end(dt.datetime(2026, 11, 25, 16, 0, tzinfo=cn)) == dt.date(2026, 11, 25)
    fri = dt.datetime(2026, 11, 27, 18, 0, tzinfo=cn)
    assert next_run(dt.time(17, 30), fri).weekday() == 0  # 周五收盘后 → 下周一


def test_missed_today_catch_up():
    at = dt.time(18, 30)
    wed_evening = dt.datetime(2026, 11, 25, 19, 2)
    assert missed_today(at, wed_evening, {"state": "never"})                       # 晚上发布，今天还没同步 → 补
    assert missed_today(at, wed_evening, {"state": "ok", "finished_at": "2026-11-24T18:31:00+08:00"})
    assert missed_today(at, wed_evening, {"state": "running", "finished_at": None})  # 上次同步中途进程退出
    assert not missed_today(at, wed_evening, {"state": "ok", "finished_at": "2026-11-25T18:32:00+08:00"})
    assert not missed_today(at, dt.datetime(2026, 11, 25, 10, 0), {"state": "never"})  # 还没到点
    assert not missed_today(at, dt.datetime(2026, 11, 28, 20, 0), {"state": "never"})  # 周六


def test_prune_keeps_newest_and_current(tmp_path: Path):
    market = tmp_path / "market"
    for i, vid in enumerate(["v1", "v2", "v3", "v4"]):
        d = versions.version_path(market, vid)
        d.mkdir(parents=True)
        versions.write_manifest(d, {"id": vid, "created_at": f"2026-11-2{i}T18:00:00+08:00"})
    (market / "CURRENT").write_text("v2", encoding="utf-8")  # 当前版本不是最新的（例如回滚过）
    removed = versions.prune(market, keep=2)
    assert sorted(removed) == ["v1"]
    assert sorted(p.name for p in versions.versions_dir(market).iterdir()) == ["v2", "v3", "v4"]
    assert versions.prune(market, keep=0) == []  # 最少保留 2 个 + 当前
