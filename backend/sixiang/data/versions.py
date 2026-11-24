"""行情数据版本。

目录结构（market_dir 下）：
    versions/<id>/manifest.json, daily.parquet, securities.parquet, indices.parquet, calendar.parquet
    staging/<id>/            导入或同步中的暂存目录，校验通过后才发布
    CURRENT                  当前版本 id，发布时原子替换

研究记录引用版本 id，旧版本不删除，保证结论可复现。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

MANIFEST = "manifest.json"


def versions_dir(market_dir: Path) -> Path:
    return market_dir / "versions"


def staging_dir(market_dir: Path, version_id: str) -> Path:
    path = market_dir / "staging" / version_id
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def current_version_id(market_dir: Path) -> str | None:
    pointer = market_dir / "CURRENT"
    if not pointer.exists():
        return None
    value = pointer.read_text(encoding="utf-8").strip()
    return value or None


def version_path(market_dir: Path, version_id: str) -> Path:
    return versions_dir(market_dir) / version_id


def read_manifest(market_dir: Path, version_id: str) -> dict:
    return json.loads((version_path(market_dir, version_id) / MANIFEST).read_text(encoding="utf-8"))


def write_manifest(directory: Path, manifest: dict) -> None:
    (directory / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def publish(market_dir: Path, staged: Path, version_id: str) -> Path:
    """把暂存目录移入 versions/ 并原子切换 CURRENT。已存在的版本不覆盖。"""
    target = version_path(market_dir, version_id)
    if target.exists():
        raise FileExistsError(f"版本 {version_id} 已存在，不覆盖")
    if not (staged / MANIFEST).exists():
        raise ValueError("暂存目录缺少 manifest.json，拒绝发布")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged), str(target))
    tmp = market_dir / "CURRENT.tmp"
    tmp.write_text(version_id, encoding="utf-8")
    os.replace(tmp, market_dir / "CURRENT")
    return target
