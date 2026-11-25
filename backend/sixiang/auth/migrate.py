"""把业务库整库复制到另一个数据库（如本地 SQLite → 线上 MySQL），保留原有 id。

用法：
    python -m sixiang.auth.migrate --source sqlite:///data/app.db --target "mysql+pymysql://user:pass@host:3306/sixiang?charset=utf8mb4"

目标库里这些表必须是空的，避免把两份数据混在一起；加 --dry-run 只看各表行数。
"""
from __future__ import annotations

import argparse

from sqlalchemy import func, select

from .db import make_engine, metadata


def migrate(source_url: str, target_url: str, dry_run: bool = False) -> dict[str, int]:
    src, dst = make_engine(source_url), make_engine(target_url)
    counts: dict[str, int] = {}
    with src.connect() as s, dst.connect() as d:
        for table in metadata.sorted_tables:
            counts[table.name] = s.execute(select(func.count()).select_from(table)).scalar_one()
            existing = d.execute(select(func.count()).select_from(table)).scalar_one()
            if existing:
                raise SystemExit(f"目标库的 {table.name} 已有 {existing} 行，停止迁移")
    if dry_run:
        return counts
    with src.connect() as s, dst.begin() as d:
        for table in metadata.sorted_tables:
            rows = [dict(r._mapping) for r in s.execute(select(table))]
            if rows:
                d.execute(table.insert(), rows)
    with dst.connect() as d:
        for table in metadata.sorted_tables:
            got = d.execute(select(func.count()).select_from(table)).scalar_one()
            if got != counts[table.name]:
                raise SystemExit(f"{table.name} 复制后行数不一致：源 {counts[table.name]}，目标 {got}")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for name, n in migrate(args.source, args.target, args.dry_run).items():
        print(f"{name:16} {n}")
    print("只检查，未写入" if args.dry_run else "迁移完成，行数一致")


if __name__ == "__main__":
    main()
