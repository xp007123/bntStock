"""业务数据库（账号与会话）。默认 SQLite，SIXIANG_DATABASE_URL 可切换到 PostgreSQL / MySQL。"""
from __future__ import annotations

from sqlalchemy import (Boolean, Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint, create_engine, event)
from sqlalchemy.engine import Engine

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(40), nullable=False),
    Column("username_key", String(40), nullable=False, unique=True),   # 小写，用于唯一与登录匹配
    Column("phone", String(20), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("status", String(16), nullable=False),                      # pending / active / rejected / disabled
    Column("is_admin", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(), nullable=False),
    Column("reviewed_at", DateTime()),
    Column("reviewed_by", Integer),
    Column("review_note", String(200)),
    Column("last_login_at", DateTime()),
)

sessions = Table(
    "sessions", metadata,
    Column("token_hash", String(64), primary_key=True),                # 只存会话令牌的哈希
    Column("user_id", Integer, nullable=False, index=True),
    Column("created_at", DateTime(), nullable=False),
    Column("expires_at", DateTime(), nullable=False),
)


def make_engine(url: str) -> Engine:
    engine = create_engine(url, future=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragma(conn, _record):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
    metadata.create_all(engine)
    return engine


# ---------------------------------------------------------------- 我的条件 / 我的形态（按用户）

user_conditions = Table(
    "user_conditions", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("fingerprint", String(40), nullable=False),
    Column("name", String(120), nullable=False),
    Column("condition_json", String(8000), nullable=False),
    Column("source_job", String(20)),
    Column("created_at", DateTime(), nullable=False),
    UniqueConstraint("user_id", "fingerprint"),
)

user_patterns = Table(
    "user_patterns", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("fingerprint", String(40), nullable=False),
    Column("name", String(120), nullable=False),
    Column("rule_json", String(64000), nullable=False),
    Column("last_job", String(20)),
    Column("updated_at", DateTime(), nullable=False),
    UniqueConstraint("user_id", "fingerprint"),
)
