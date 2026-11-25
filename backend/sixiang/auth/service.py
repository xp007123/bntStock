"""账号：注册（待审核）、登录（用户名或手机号）、会话、审核。

- 密码用 scrypt 加盐哈希，不保存明文；会话令牌只保存 SHA-256 哈希。
- 连续登录失败 5 次锁定 15 分钟（按账号 + 按来源 IP）。
- 所有面向用户的错误信息不区分“用户不存在”和“密码错误”。
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass

from sqlalchemy import func, insert, select, update, delete
from sqlalchemy.engine import Engine

from .db import sessions, users

SESSION_DAYS = 30
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
MAX_REGISTRATIONS_PER_IP = 5      # 每个来源 IP 每小时最多注册次数
USERNAME_RE = re.compile(r"^[一-龥A-Za-z0-9_]{2,20}$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
STATUSES = ("pending", "active", "rejected", "disabled")


class AuthError(ValueError):
    """可直接展示给用户的错误。"""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class User:
    id: int
    username: str
    phone: str
    status: str
    is_admin: bool

    def public(self) -> dict:
        return {"id": self.id, "username": self.username, "phone": mask_phone(self.phone), "status": self.status, "is_admin": self.is_admin}


def now() -> dt.datetime:
    """UTC，不带时区（SQLite 比较时保持一致）。"""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def mask_phone(phone: str) -> str:
    return phone[:3] + "****" + phone[-4:]


# ---------------------------------------------------------------- 密码

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def check_password_strength(password: str) -> None:
    """只要求长度 6–64 位（产品决定：不强制字母加数字，降低客户记忆负担）。"""
    if not isinstance(password, str) or not 6 <= len(password) <= 64:
        raise AuthError("密码长度需为 6–64 位", "password")


# ---------------------------------------------------------------- 服务

class AuthService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _user(row) -> User:
        return User(row.id, row.username, row.phone, row.status, bool(row.is_admin))

    # ---- 注册
    def register(self, username: str, phone: str, password: str, confirm: str, *, status: str = "pending",
                 is_admin: bool = False, ip: str | None = None) -> User:
        if ip is not None:
            key = f"reg:{ip}"
            with self._lock:
                recent = [t for t in self._failures.get(key, []) if time.time() - t < 3600]
                if len(recent) >= MAX_REGISTRATIONS_PER_IP:
                    raise AuthError("注册过于频繁，请稍后再试", "locked")
                self._failures[key] = recent + [time.time()]
        username = (username or "").strip()
        phone = (phone or "").strip()
        if not USERNAME_RE.match(username):
            raise AuthError("用户名需为 2–20 位中文、字母、数字或下划线", "username")
        if username.isdigit():
            raise AuthError("用户名不能是纯数字", "username")
        if not PHONE_RE.match(phone):
            raise AuthError("请输入正确的 11 位手机号", "phone")
        check_password_strength(password)
        if password != confirm:
            raise AuthError("两次输入的密码不一致", "confirm")
        with self.engine.begin() as conn:
            if conn.execute(select(users.c.id).where(users.c.username_key == username.lower())).first():
                raise AuthError("该用户名已被注册", "username")
            if conn.execute(select(users.c.id).where(users.c.phone == phone)).first():
                raise AuthError("该手机号已注册", "phone")
            uid = conn.execute(insert(users).values(
                username=username, username_key=username.lower(), phone=phone, password_hash=hash_password(password),
                status=status, is_admin=is_admin, created_at=now())).inserted_primary_key[0]
        return self.get(uid)

    # ---- 登录
    def _locked(self, key: str) -> bool:
        with self._lock:
            recent = [t for t in self._failures.get(key, []) if time.time() - t < LOCK_SECONDS]
            self._failures[key] = recent
            return len(recent) >= MAX_FAILURES

    def _fail(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.setdefault(k, []).append(time.time())

    def authenticate(self, account: str, password: str, ip: str = "") -> tuple[User, str]:
        """用户名或手机号登录。成功返回 (用户, 会话令牌)。"""
        account = (account or "").strip()
        keys = (f"acct:{account.lower()}", f"ip:{ip}")
        if any(self._locked(k) for k in keys):
            raise AuthError("登录失败次数过多，请 15 分钟后再试", "locked")
        column = users.c.phone if PHONE_RE.match(account) else users.c.username_key
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(column == account.lower())).first()
        if row is None or not verify_password(password or "", row.password_hash):
            self._fail(*keys)
            raise AuthError("账号或密码错误", "credentials")
        if row.status == "pending":
            raise AuthError("注册已提交，正在等待管理员审核", "pending")
        if row.status == "rejected":
            raise AuthError("注册未通过审核，如有疑问请联系管理员", "rejected")
        if row.status == "disabled":
            raise AuthError("账号已停用，如有疑问请联系管理员", "disabled")
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            conn.execute(insert(sessions).values(token_hash=_token_hash(token), user_id=row.id, created_at=now(),
                                                 expires_at=now() + dt.timedelta(days=SESSION_DAYS)))
            conn.execute(update(users).where(users.c.id == row.id).values(last_login_at=now()))
            conn.execute(delete(sessions).where(sessions.c.expires_at < now()))
        return self._user(row), token

    def user_for_token(self, token: str | None) -> User | None:
        if not token:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(select(users).join(sessions, sessions.c.user_id == users.c.id)
                               .where(sessions.c.token_hash == _token_hash(token), sessions.c.expires_at > now())).first()
        if row is None or row.status != "active":
            return None
        return self._user(row)

    def logout(self, token: str | None) -> None:
        if token:
            with self.engine.begin() as conn:
                conn.execute(delete(sessions).where(sessions.c.token_hash == _token_hash(token)))

    # ---- 管理
    def get(self, uid: int) -> User:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.id == uid)).first()
        if row is None:
            raise KeyError(uid)
        return self._user(row)

    def list_users(self, status: str | None = None) -> list[dict]:
        q = select(users).order_by(users.c.created_at.desc())
        if status:
            q = q.where(users.c.status == status)
        with self.engine.connect() as conn:
            rows = conn.execute(q).all()
        return [{"id": r.id, "username": r.username, "phone": r.phone, "status": r.status, "is_admin": bool(r.is_admin),
                 "created_at": r.created_at.isoformat() if r.created_at else None,
                 "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None, "review_note": r.review_note,
                 "last_login_at": r.last_login_at.isoformat() if r.last_login_at else None} for r in rows]

    def counts(self) -> dict[str, int]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(users.c.status, func.count()).group_by(users.c.status)).all()
        return {s: 0 for s in STATUSES} | {s: n for s, n in rows}

    def set_status(self, uid: int, status: str, admin: User, note: str | None = None) -> User:
        if status not in STATUSES or status == "pending":
            raise AuthError("无效的状态")
        target = self.get(uid)
        if target.id == admin.id:
            raise AuthError("不能修改自己的账号状态")
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == uid).values(status=status, reviewed_at=now(), reviewed_by=admin.id,
                                                                       review_note=(note or "")[:200] or None))
            if status != "active":
                conn.execute(delete(sessions).where(sessions.c.user_id == uid))
        return self.get(uid)

    def reset_password(self, uid: int, password: str) -> None:
        check_password_strength(password)
        self.get(uid)
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == uid).values(password_hash=hash_password(password)))
            conn.execute(delete(sessions).where(sessions.c.user_id == uid))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
