"""运行配置。只从环境变量读取，默认值适合本地开发。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    frontend_dist: Path

    @property
    def market_dir(self) -> Path:
        return self.data_dir / "market"


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """读取仓库根目录 .env（不入库，存放 iFinD 凭证等）。已设置的环境变量优先。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def load_settings() -> Settings:
    load_dotenv()
    data_dir = Path(os.environ.get("SIXIANG_DATA_DIR", REPO_ROOT / "data")).resolve()
    dist = Path(os.environ.get("SIXIANG_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist")).resolve()
    return Settings(data_dir=data_dir, frontend_dist=dist)
