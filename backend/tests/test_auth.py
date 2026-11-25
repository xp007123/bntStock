from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sixiang.api.app import create_app
from sixiang.auth.db import users
from sixiang.config import Settings

from .conftest import login_as_admin


@pytest.fixture
def app(tmp_path: Path):
    return create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none"))


def _register(c: TestClient, username="张三", phone="13912345678", password="123456", confirm=None):
    return c.post("/api/auth/register", json={"username": username, "phone": phone, "password": password,
                                               "confirm": password if confirm is None else confirm})


def test_api_requires_login(app):
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/data/version").status_code == 401
    assert c.get("/api/patterns/jobs").status_code == 401
    assert c.get("/api/admin/users").status_code == 401


@pytest.mark.parametrize("kwargs, field", [
    ({"username": "1"}, "username"),
    ({"username": "12345"}, "username"),           # 纯数字会与手机号登录冲突
    ({"phone": "1234"}, "phone"),
    ({"password": "12345"}, "password"),           # 至少 6 位
    ({"confirm": "654321"}, "confirm"),
])
def test_register_validation(app, kwargs, field):
    r = _register(TestClient(app), **kwargs)
    assert r.status_code == 422 and r.json()["detail"]["field"] == field


def test_register_review_login_flow(app):
    user, admin = TestClient(app), TestClient(app)
    assert _register(user).json()["status"] == "pending"
    assert _register(user, phone="13900000000").json()["detail"]["field"] == "username"      # 用户名重复
    assert _register(user, username="李四").json()["detail"]["field"] == "phone"             # 手机号重复

    r = user.post("/api/auth/login", json={"account": "张三", "password": "123456"})
    assert r.status_code == 403 and r.json()["detail"]["field"] == "pending"

    login_as_admin(admin)
    listing = admin.get("/api/admin/users", params={"status": "pending"}).json()
    assert listing["counts"]["pending"] == 1
    uid = listing["items"][0]["id"]
    assert admin.post(f"/api/admin/users/{uid}/status", json={"status": "active"}).json()["status"] == "active"

    # 用户名或手机号都能登录；密码只存哈希
    for account in ("张三", "13912345678"):
        r = user.post("/api/auth/login", json={"account": account, "password": "123456"})
        assert r.status_code == 200 and r.json()["phone"] == "139****5678"
    assert user.get("/api/auth/me").json()["username"] == "张三"
    with app.state.auth.engine.connect() as conn:
        stored = conn.execute(select(users.c.password_hash).where(users.c.id == uid)).scalar_one()
    assert "123456" not in stored and stored.startswith("scrypt$")

    # 普通用户不能访问管理端
    assert user.get("/api/admin/users").status_code == 403

    # 管理员重置密码后旧会话失效，新密码可登录
    assert admin.post(f"/api/admin/users/{uid}/password", json={"password": "888888"}).status_code == 200
    assert user.get("/api/auth/me").status_code == 401
    assert user.post("/api/auth/login", json={"account": "张三", "password": "888888"}).status_code == 200

    # 停用后会话失效、无法登录
    admin.post(f"/api/admin/users/{uid}/status", json={"status": "disabled"})
    assert user.get("/api/auth/me").status_code == 401
    assert user.post("/api/auth/login", json={"account": "张三", "password": "888888"}).json()["detail"]["field"] == "disabled"

    user.post("/api/auth/logout")
    assert user.get("/api/auth/me").status_code == 401


def test_lockout_after_failures(app):
    c = TestClient(app)
    login_as_admin(c)
    c.post("/api/auth/logout")
    for _ in range(5):
        assert c.post("/api/auth/login", json={"account": "管理员", "password": "wrong-pass"}).status_code == 401
    r = c.post("/api/auth/login", json={"account": "管理员", "password": "admin123"})
    assert r.status_code == 429


def test_jobs_are_private(app):
    admin = TestClient(app)
    login_as_admin(admin)
    other = TestClient(app)
    app.state.auth.register("王五", "13700000000", "abcdef", "abcdef", status="active")
    other.post("/api/auth/login", json={"account": "王五", "password": "abcdef"})
    jobs = app.state.jobs
    jobs._jobs["x1"] = {"id": "x1", "owner": 1, "name": "a", "status": "completed", "created": "1", "rule": {"conditions": []},
                        "rule_hash": "h", "data_version": "v"}
    assert [j["id"] for j in admin.get("/api/patterns/jobs").json()] == ["x1"]
    assert other.get("/api/patterns/jobs").json() == []
    assert other.get("/api/patterns/jobs/x1").status_code == 404
