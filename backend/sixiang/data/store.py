"""行情查询。读取当前版本的 Parquet 快照，用 DuckDB 按需查询。

CURRENT 指针变化时自动切换到新版本；查询结果带版本 id，便于研究记录追溯。
"""
from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import pyarrow.parquet as pq

from . import versions

Adjust = Literal["none", "qfq", "hfq"]


class NoDataVersion(RuntimeError):
    """尚未发布任何行情版本。"""


class UnknownSecurity(KeyError):
    pass


@dataclass(frozen=True)
class _Snapshot:
    version_id: str
    path: Path
    manifest: dict
    daily_meta: pq.FileMetaData
    row_groups: dict[str, list[int]]  # code -> daily.parquet 中的行组序号（导入时每只股票一个行组）


def _index_row_groups(meta: pq.FileMetaData) -> dict[str, list[int]]:
    col = meta.schema.to_arrow_schema().get_field_index("code")
    index: dict[str, list[int]] = {}
    for i in range(meta.num_row_groups):
        stats = meta.row_group(i).column(col).statistics
        if stats is None or not stats.has_min_max or stats.min != stats.max:
            raise ValueError("daily.parquet 行组未按股票划分，无法建立索引")
        index.setdefault(stats.min, []).append(i)
    return index


class MarketStore:
    def __init__(self, market_dir: Path):
        self.market_dir = market_dir
        self._lock = threading.Lock()
        self._snapshot: _Snapshot | None = None
        self._con: duckdb.DuckDBPyConnection | None = None

    # ---- 版本 ----
    def _current(self) -> tuple[_Snapshot, duckdb.DuckDBPyConnection]:
        version_id = versions.current_version_id(self.market_dir)
        if not version_id:
            raise NoDataVersion("尚未发布行情数据版本")
        with self._lock:
            if self._snapshot is None or self._snapshot.version_id != version_id:
                path = versions.version_path(self.market_dir, version_id)
                con = duckdb.connect(config={"enable_object_cache": True})
                for table in ("daily", "securities", "indices", "calendar"):
                    file = path / f"{table}.parquet"
                    if file.exists():
                        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{file.as_posix()}')")
                meta = pq.read_metadata(path / "daily.parquet")
                old, self._con = self._con, con
                self._snapshot = _Snapshot(version_id, path, versions.read_manifest(self.market_dir, version_id),
                                           meta, _index_row_groups(meta))
                if old is not None:
                    old.close()
            return self._snapshot, self._con.cursor()

    def version(self) -> dict:
        snap, _ = self._current()
        m = snap.manifest
        return {"id": m["id"], "data_end": m["data_end"], "created_at": m["created_at"],
                "source": m["source"]["kind"], "counts": m["counts"], "adjustment": m["adjustment"]}

    # ---- 证券 ----
    def search(self, q: str = "", limit: int = 20) -> list[dict]:
        _, cur = self._current()
        q = q.strip().lower()
        if not q:
            sql = "SELECT code, name, sector_l1, last_date FROM securities ORDER BY code LIMIT ?"
            rows = cur.execute(sql, [limit]).fetchall()
        else:
            # 代码精确/前缀优先，其次名称包含
            sql = """
                SELECT code, name, sector_l1, last_date FROM securities
                WHERE code LIKE ? OR substr(code, 3) LIKE ? OR name LIKE ?
                ORDER BY CASE WHEN substr(code, 3) = ? OR code = ? THEN 0
                              WHEN code LIKE ? OR substr(code, 3) LIKE ? THEN 1 ELSE 2 END, code
                LIMIT ?"""
            like = f"{q}%"
            rows = cur.execute(sql, [like, like, f"%{q}%", q, q, like, like, limit]).fetchall()
        return [{"code": c, "name": n, "sector": s, "last_date": d.isoformat()} for c, n, s, d in rows]

    def security(self, code: str) -> dict:
        snap, cur = self._current()
        row = cur.execute("SELECT code, name, exchange, sector_l1, first_date, last_date, rows FROM securities WHERE code = ?",
                          [code.lower()]).fetchone()
        if not row:
            raise UnknownSecurity(code)
        c, name, exchange, sector, first, last, rows = row
        return {"code": c, "name": name, "exchange": exchange, "sector": sector,
                "first_date": first.isoformat(), "last_date": last.isoformat(), "rows": rows,
                "data_version": snap.version_id}

    def daily(self, code: str, start: dt.date | None = None, end: dt.date | None = None,
              adjust: Adjust = "qfq", limit: int | None = None) -> dict:
        """日线。limit 表示取截止 end 的最近 N 根。只读取该股票所在的行组。"""
        snap, _ = self._current()
        meta = self.security(code)
        groups = snap.row_groups.get(meta["code"], [])
        cols = ["date", "open", "high", "low", "close", "prev_close", "volume", "amount", "name", "adj_factor"]
        df = pq.ParquetFile(snap.path / "daily.parquet", metadata=snap.daily_meta).read_row_groups(groups, columns=cols).to_pandas()
        if len(df):
            factor = {"none": 1.0, "hfq": df["adj_factor"], "qfq": df["adj_factor"] / df["adj_factor"].iloc[-1]}[adjust]
            for c in ("open", "high", "low", "close", "prev_close"):
                df[c] = (df[c] * factor).round(4)
        if start:
            df = df[df["date"] >= start]
        if end:
            df = df[df["date"] <= end]
        if limit:
            df = df.tail(int(limit))
        df["date"] = df["date"].map(lambda d: d.isoformat())
        bars = df.drop(columns="adj_factor").to_dict("records")
        return {"code": meta["code"], "name": meta["name"], "adjust": adjust, "data_version": snap.version_id, "bars": bars}

    # ---- 指数 ----
    def indices(self) -> list[dict]:
        snap, cur = self._current()
        names = snap.manifest.get("index_names", {})
        rows = cur.execute("""
            SELECT code, arg_max(close, date), arg_max(date, date),
                   arg_max(close, date) / nullif(list_extract(list(close ORDER BY date DESC), 2), 0) - 1
            FROM indices GROUP BY code ORDER BY code""").fetchall()
        return [{"code": c, "name": names.get(c, c), "close": close, "date": d.isoformat(),
                 "change": round(chg, 6) if chg is not None else None} for c, close, d, chg in rows]

    def index_daily(self, code: str, limit: int | None = 250) -> dict:
        snap, cur = self._current()
        rows = cur.execute(f"""
            SELECT date, open, high, low, close, volume, amount FROM
              (SELECT * FROM indices WHERE code = ? ORDER BY date DESC {'LIMIT ' + str(int(limit)) if limit else ''})
            ORDER BY date""", [code.lower()]).fetchall()
        if not rows:
            raise UnknownSecurity(code)
        names = snap.manifest.get("index_names", {})
        return {"code": code.lower(), "name": names.get(code.lower(), code), "data_version": snap.version_id,
                "bars": [{"date": d.isoformat(), "open": o, "high": h, "low": lo, "close": c, "volume": v, "amount": a}
                         for d, o, h, lo, c, v, a in rows]}
