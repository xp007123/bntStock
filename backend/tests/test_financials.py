from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sixiang.api.app import create_app
from sixiang.config import Settings
from sixiang.data import versions
from sixiang.data.baseline_import import import_baseline
from sixiang.data.financial_import import import_financials
from sixiang.data.financials import disclosed, read_patternlab_stock, summarize

from .conftest import login_as_admin

HEAD = "report_date,publish_date,抓取时间,available_from,statement_format,R_np_atoopc@xbx,R_operating_total_revenue@xbx,B_total_equity_atoopc@xbx,B_total_liab@xbx,B_total_assets@xbx"


def write_fin(directory: Path, name: str, rows: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(("测试财务\n" + HEAD + "\n" + "\n".join(rows) + "\n").encode("gbk"))


@pytest.fixture
def fin_source(tmp_path: Path) -> Path:
    root = tmp_path / "financial"
    write_fin(root / "sz000001", "base.csv", [
        "20241231,2025-03-20,,,一般企业,100,1000,500,800,1300",
        "20250930,2025-10-25,,,一般企业,80,750,520,820,1340",
        "20251231,2026-03-20,,,一般企业,120,1100,540,830,1370",
        "20260930,2026-10-25,,,一般企业,90,800,560,850,1410",
    ])
    # 三季报事后修订：2026-11-10 才可得，修订前的时点不能看到
    write_fin(root / "sz000001", "revision.csv", ["20260930,2026-10-25,2026-11-10 10:00:00,2026-11-10,一般企业,95,800,560,850,1410"])
    return root


def test_point_in_time_and_ttm(fin_source: Path):
    df = read_patternlab_stock(fin_source / "sz000001")
    assert len(df) == 5
    before = disclosed(df, "2026-11-01")
    assert before.iloc[0]["R_np_atoopc"] == 90                 # 修订尚未可得
    assert disclosed(df, "2026-11-18").iloc[0]["R_np_atoopc"] == 95
    assert disclosed(df, "2026-10-01").iloc[0]["report_date"] == dt.date(2025, 12, 31)   # 三季报尚未披露
    s = summarize(df, "2026-11-18")
    assert s["ttm_profit"] == pytest.approx(95 + 120 - 80)     # 本期累计 + 上年年报 − 上年同期
    assert s["annual_profit"] == 120
    assert s["reports"][0]["yoy"]["R_np_atoopc"] == pytest.approx((95 - 80) / 80)


def test_import_api_and_sync_carry(fin_source: Path, source: Path, tmp_path: Path):
    data = tmp_path / "data"
    import_baseline(source, data / "market", "v0", workers=1, log=lambda *_: None)
    manifest = import_financials(fin_source, data / "market", workers=1, log=lambda *_: None)
    assert manifest["id"] == "v0-fin" and manifest["financials"]["stocks"] == 1
    assert versions.current_version_id(data / "market") == "v0-fin"
    # 行情文件以硬链接或复制复用
    assert (data / "market" / "versions" / "v0-fin" / "daily.parquet").exists()

    c = TestClient(create_app(Settings(data_dir=data, frontend_dist=tmp_path / "none")))
    login_as_admin(c)
    f = c.get("/api/securities/sz000001/financials").json()
    assert f["available"] and f["asof"] == "2026-11-18" and f["reports"][0]["values"]["R_np_atoopc"] == 95
    v = f["valuation"]
    assert v["total_mcap"] == 2e9 and v["pe_ttm"] == pytest.approx(2e9 / 135) and v["pb"] == pytest.approx(2e9 / 560)
    assert c.get("/api/securities/sz000001/financials", params={"asof": "2026-11-01"}).json()["reports"][0]["values"]["R_np_atoopc"] == 90
    none = c.get("/api/securities/sh600000/financials").json()
    assert none["reports"] == []


def test_ifind_sync_keeps_financials(fin_source: Path, source: Path, tmp_path: Path, monkeypatch):
    import sixiang.data.ifind_sync as mod
    from .test_ifind_sync import FakeIFind, MAOTAI, PINGAN, PUFA
    monkeypatch.setattr(mod, "MIN_OVERLAP_CHECKED", 1)
    market = tmp_path / "m"
    import_baseline(source, market, "v0", workers=1, log=lambda *_: None)
    import_financials(fin_source, market, workers=1, log=lambda *_: None)
    fake = FakeIFind({"sz000001": PINGAN, "sh600000": PUFA, "sh600519": MAOTAI}, ["sz000001", "sh600000", "sh600519"])
    result = mod.sync(market, fake, dt.date(2026, 11, 20), log=lambda *_: None)
    new = versions.version_path(market, result["id"])
    assert (new / "financials.parquet").exists() and result["financials"]["stocks"] == 1
    assert pd.read_parquet(new / "financials.parquet").shape[0] == 5
