from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sixiang.api.app import create_app
from sixiang.config import Settings
from sixiang.data import versions
from sixiang.data.baseline_import import import_baseline
from sixiang.data.patternlab_csv import RejectedFile, read_daily

from .conftest import login_as_admin


def test_adj_factor_follows_prev_close(source: Path):
    parsed = read_daily(source / "daily" / "sz000001.csv")
    assert parsed.frame["adj_factor"].tolist() == [1.0, 1.0, 2.0]


def test_rejects_bad_ohlc_after_2007(source: Path):
    with pytest.raises(RejectedFile):
        read_daily(source / "daily" / "sz000002.csv")


def test_drops_bad_prefix_before_2007(source: Path):
    parsed = read_daily(source / "daily" / "sh600519.csv")
    assert parsed.omitted_prefix_rows == 1
    assert str(parsed.frame["date"].iloc[0]) == "2001-08-28"


@pytest.fixture
def client(source: Path, tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    import_baseline(source, data_dir / "market", "v-test", workers=1, log=lambda *_: None)
    c = TestClient(create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist")))
    login_as_admin(c)
    return c


def test_version_and_manifest(client: TestClient):
    v = client.get("/api/data/version").json()
    assert v["id"] == "v-test" and v["data_end"] == "2026-11-18"
    assert v["counts"]["securities"] == 3 and v["counts"]["rejected"] == 1


def test_publish_refuses_overwrite(source: Path, tmp_path: Path):
    market = tmp_path / "m"
    import_baseline(source, market, "v1", workers=1, log=lambda *_: None)
    with pytest.raises(FileExistsError):
        import_baseline(source, market, "v1", workers=1, log=lambda *_: None)
    assert versions.current_version_id(market) == "v1"


def test_search(client: TestClient):
    assert client.get("/api/securities", params={"q": "000001"}).json()[0]["code"] == "sz000001"
    assert client.get("/api/securities", params={"q": "茅台"}).json()[0]["code"] == "sh600519"


def test_daily_adjustments(client: TestClient):
    raw = client.get("/api/securities/sz000001/daily", params={"adjust": "none"}).json()["bars"]
    hfq = client.get("/api/securities/sz000001/daily", params={"adjust": "hfq"}).json()["bars"]
    qfq = client.get("/api/securities/sz000001/daily", params={"adjust": "qfq"}).json()["bars"]
    assert [b["close"] for b in raw] == [10.0, 10.0, 5.2]
    assert [b["close"] for b in hfq] == [10.0, 10.0, 10.4]
    assert [b["close"] for b in qfq] == [5.0, 5.0, 5.2]
    last2 = client.get("/api/securities/sz000001/daily", params={"limit": 2}).json()["bars"]
    assert [b["date"] for b in last2] == ["2026-11-17", "2026-11-18"]


def test_unknown_code_404(client: TestClient):
    assert client.get("/api/securities/sz999999").status_code == 404


def test_indices(client: TestClient):
    idx = client.get("/api/indices").json()
    assert idx[0]["code"] == "sh000001" and idx[0]["name"] == "上证指数"
    assert idx[0]["change"] == pytest.approx(3521.1 / 3510 - 1, abs=1e-6)


def test_no_version_returns_503(tmp_path: Path):
    c = TestClient(create_app(Settings(data_dir=tmp_path / "empty", frontend_dist=tmp_path / "x")))
    login_as_admin(c)
    assert c.get("/api/data/version").status_code == 503
