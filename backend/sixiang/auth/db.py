"""业务数据库（账号与会话）。默认 SQLite，SIXIANG_DATABASE_URL 可切换到 PostgreSQL / MySQL。"""
from __future__ import annotations

from sqlalchemy import (Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Engine

metadata = MetaData()

# 长 JSON 字段：MySQL 的 VARCHAR 受行宽 65535 字节限制，用 MEDIUMTEXT；SQLite 里就是 TEXT
LongText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")

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
    if url.startswith("sqlite"):
        engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    else:
        # MySQL 等服务端数据库：连接前探活，定期回收，避免 wait_timeout 断开后报错
        engine = create_engine(url, future=True, pool_pre_ping=True, pool_recycle=1800)
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
    Column("condition_json", LongText, nullable=False),
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
    Column("rule_json", LongText, nullable=False),
    Column("last_job", String(20)),
    Column("updated_at", DateTime(), nullable=False),
    UniqueConstraint("user_id", "fingerprint"),
)


# ---------------------------------------------------------------- 判断：封存与揭晓

judgments = Table(
    "judgments", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("kind", String(16), nullable=False),            # stock / option
    Column("code", String(12), nullable=False),
    Column("name", String(40), nullable=False),
    Column("horizon", Integer, nullable=False),
    Column("fee", String(16)),                              # 期权费（小数）
    Column("asof", String(10), nullable=False),             # 封存时的行情日期（以该日收盘为起点）
    Column("data_version", String(60), nullable=False),
    Column("question", String(200), nullable=False),
    Column("prediction_json", LongText, nullable=False),
    Column("status", String(12), nullable=False),           # sealed / settled
    Column("due_estimate", String(10), nullable=False),     # 按工作日估算的揭晓日（不含节假日）
    Column("outcome_json", LongText),
    Column("created_at", DateTime(), nullable=False),
    Column("settled_at", DateTime()),
)

# ---------------------------------------------------------------- 自选股（按用户）

watchlist = Table(
    "watchlist", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("code", String(12), nullable=False),
    Column("created_at", DateTime(), nullable=False),
    UniqueConstraint("user_id", "code"),
)

# ---------------------------------------------------------------- 群聊（见 docs/群聊-需求与架构.md）

rooms = Table(
    "rooms", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("title", String(80), nullable=False),
    Column("topic_json", LongText, nullable=False),          # {"kind": "stock", "code": ..., "name": ..., "brief": ...}
    Column("members_json", LongText, nullable=False),        # 现在群里的嘉宾 id，按座次
    Column("status", String(16), nullable=False),            # idle 空闲 / playing 演出中 / interrupted 被打断
    Column("summary", LongText),                             # 更早聊天记录的摘要
    Column("created_at", DateTime(), nullable=False),
    Column("updated_at", DateTime(), nullable=False),
)

room_messages = Table(
    "room_messages", metadata,
    Column("id", Integer, primary_key=True),
    Column("room_id", Integer, nullable=False, index=True),
    Column("seq", Integer, nullable=False),                  # 群内序号，断线续传用
    Column("role", String(12), nullable=False),              # host / guest / user / system
    Column("persona_id", String(40)),
    Column("name", String(40), nullable=False),
    Column("text", LongText, nullable=False),
    Column("reply_to", Integer),
    Column("cards_json", LongText),
    Column("data_json", LongText),
    Column("meta_json", LongText),
    Column("created_at", DateTime(), nullable=False, index=True),
    UniqueConstraint("room_id", "seq"),
)

# 角色卡的历史版本。仓库里 room/personas/*.md 是出厂设置；管理端每保存一次，这里多一行。
persona_versions = Table(
    "persona_versions", metadata,
    Column("id", Integer, primary_key=True),
    Column("persona_id", String(40), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("content", LongText, nullable=False),             # 整张角色卡（Markdown，带头部）
    Column("note", String(200)),                             # 这一版改了什么
    Column("created_by", Integer),
    Column("created_at", DateTime(), nullable=False),
    UniqueConstraint("persona_id", "version"),
)

persona_settings = Table(
    "persona_settings", metadata,
    Column("persona_id", String(40), primary_key=True),
    Column("current_version", Integer),                      # 空 = 用出厂设置
    Column("enabled", Boolean, nullable=False, default=True),      # 停用后不能再被拉进群
    Column("in_default", Boolean, nullable=False, default=False),  # 开群时默认拉进来
    Column("sort", Integer, nullable=False, default=0),            # 座次
    Column("updated_at", DateTime(), nullable=False),
)

# 深聊的开关。没有记录 = 开着（装了深聊包就能聊）；管理端关掉后在这里记一行。
persona_deep = Table(
    "persona_deep", metadata,
    Column("persona_id", String(40), primary_key=True),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("updated_at", DateTime(), nullable=False),
)

# 量化选股名单。pick_days 记“这一天取过没有、取到几只”（取到 0 只也要记，免得反复去取）。
pick_days = Table(
    "pick_days", metadata,
    Column("strategy", String(40), primary_key=True),
    Column("date", String(10), primary_key=True),
    Column("count", Integer, nullable=False),
    Column("fetched_at", DateTime(), nullable=False),
)

picks = Table(
    "picks", metadata,
    Column("id", Integer, primary_key=True),
    Column("strategy", String(40), nullable=False),
    Column("date", String(10), nullable=False, index=True),
    Column("code", String(12), nullable=False),
    Column("name", String(40), nullable=False),
    Column("rank", Integer, nullable=False),                 # 名单里的顺序，1 是竞价涨幅最高
    Column("detail_json", LongText),                         # 出名单时的原始数字（竞价涨幅、涨停价等）
    UniqueConstraint("strategy", "date", "code"),
)

pick_pools = Table(
    "pick_pools", metadata,                                   # 选股用的候选池（文哥：每周一次的基本面初筛结果）
    Column("strategy", String(40), primary_key=True),
    Column("week", String(10), primary_key=True),             # 这一周的周一
    Column("pool_json", LongText, nullable=False),            # [{code, name, undistri}]
    Column("created_at", DateTime(), nullable=False),
)
