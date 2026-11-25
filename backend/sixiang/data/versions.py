"""行情数据版本。

目录结构（market_dir 下）：
    versions/<id>/manifest.json, daily.parquet, securities.parquet, indices.parquet, calendar.parquet
    staging/<id>/            导入或同步中的暂存目录，校验通过后才发布
    CURRENT                  当前版本 id，发布时原子替换

研究记录和判断只引用版本 id（作为标签），不读取旧版本的文件。数据只追加、按点时截取，
旧结论用更新的版本按当时日期截取即可复现，所以旧版本可以清理（见 prune），当前版本永远保留。
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


def prune(market_dir: Path, keep: int) -> list[str]:
    """只保留最新的 keep 个版本（至少 2 个，含当前版本），删除更早的，返回删掉的版本 id。

    新旧版本之间未变化的文件是硬链接，删旧版本只减少链接数，不影响新版本。
    """
    keep = max(2, keep)
    current = current_version_id(market_dir)
    root = versions_dir(market_dir)
    if not root.exists():
        return []

    def created(path: Path) -> str:
        try:
            return json.loads((path / MANIFEST).read_text(encoding="utf-8")).get("created_at", "")
        except (OSError, ValueError):
            return ""

    ordered = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: (created(p), p.name), reverse=True)
    survivors = {p.name for p in ordered[:keep]} | ({current} if current else set())
    removed = []
    for path in ordered:
        if path.name not in survivors:
            shutil.rmtree(path)
            removed.append(path.name)
    return removed


def stage_from(market_dir: Path, base_id: str, version_id: str, skip: tuple[str, ...] = ()) -> Path:
    """以已有版本为基础建立暂存目录：未变化的文件用硬链接（同一磁盘上不占额外空间），失败时复制。"""
    staged = staging_dir(market_dir, version_id)
    for file in version_path(market_dir, base_id).iterdir():
        if file.name in skip or file.name == MANIFEST:
            continue
        try:
            os.link(file, staged / file.name)
        except OSError:
            shutil.copy2(file, staged / file.name)
    return staged
