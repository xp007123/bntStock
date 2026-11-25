"""角色表（可管理）：出厂设置来自 personas/*.md，管理端的修改存在数据库里，每保存一次多一个版本。

- 现在用哪一版：persona_settings.current_version；为空就用出厂设置。
- 停用、是否默认进群、座次，也在 persona_settings 里。主持人不能停用。
- 改完立刻生效：正在聊的群，下一条发言就用新人设。每条消息记着当时的版本号。
"""
from __future__ import annotations

import datetime as dt
import re
import threading

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Engine

from ..auth.db import persona_settings, persona_versions
from . import personas as builtin
from .personas import Persona, parse


class PersonaError(ValueError):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _with_version(content: str, version: int) -> str:
    """把卡片头部的 version 改成指定的数；没有就加一行。"""
    if re.search(r"(?m)^version:\s*\d+\s*$", content):
        return re.sub(r"(?m)^version:\s*\d+\s*$", f"version: {version}", content, count=1)
    return content.replace("---", f"---\nversion: {version}", 1) if content.startswith("---") else content


def validate(content: str, expect_id: str | None = None) -> Persona:
    """保存前检查：能解析、有名字、正文不空。宽松，只拦明显写坏的。"""
    try:
        p = parse(content)
    except Exception as exc:
        raise PersonaError("角色卡的头部写得不对：开头要有两行 --- ，中间至少有 id 和 name") from exc
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,38}", p.id):
        raise PersonaError("id 只能用小写字母、数字、下划线，字母开头，2 到 39 位")
    if expect_id and p.id != expect_id:
        raise PersonaError(f"卡片里的 id 是 {p.id}，和正在编辑的角色 {expect_id} 对不上。id 定了就不能改")
    if not p.name.strip():
        raise PersonaError("要有名字（name）")
    if len(p.body) < 30:
        raise PersonaError("正文太短了：至少写清楚这个人是谁、怎么说话")
    if p.role not in ("guest", "host"):
        raise PersonaError("role 只能是 guest（嘉宾）或 host（主持人）")
    return p


class PersonaRegistry:
    def __init__(self, engine: Engine | None = None):
        self.engine = engine
        self._lock = threading.RLock()
        self._cache: dict | None = None

    # ---------------------------------------------------------- 读
    def _load(self) -> dict:
        with self._lock:
            if self._cache is not None:
                return self._cache
            files = {p.id: p for p in builtin.all_personas(reload=True).values()}
            settings, current = {}, {}
            if self.engine is not None:
                with self.engine.connect() as conn:
                    settings = {r.persona_id: r for r in conn.execute(select(persona_settings))}
                    for pid, s in settings.items():
                        if s.current_version is not None:
                            row = conn.execute(select(persona_versions).where(persona_versions.c.persona_id == pid,
                                                                             persona_versions.c.version == s.current_version)).first()
                            if row:
                                try:
                                    current[pid] = parse(row.content)
                                except Exception:
                                    pass          # 库里这一版坏了：退回出厂设置
            items = {}
            for pid in sorted(set(files) | set(current)):
                p = current.get(pid) or files.get(pid)
                if p is None:
                    continue
                s = settings.get(pid)
                default_order = (builtin.DEFAULT_GUESTS.index(pid) + 1) * 10 if pid in builtin.DEFAULT_GUESTS else 99   # 留出空位好插人
                items[pid] = {"persona": p, "builtin": pid in files, "custom": pid in current,
                              "enabled": True if p.role == "host" else (s.enabled if s else True),
                              "in_default": s.in_default if s else pid in builtin.DEFAULT_GUESTS,
                              "sort": s.sort if s else default_order}
            self._cache = items
            return items

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None

    def cast(self) -> dict[str, Persona]:
        """现在能用的角色（含主持人）。"""
        return {pid: x["persona"] for pid, x in self._load().items() if x["enabled"]}

    def host(self) -> Persona:
        return next(x["persona"] for x in self._load().values() if x["persona"].role == "host")

    def guests(self) -> list[Persona]:
        rows = [x for x in self._load().values() if x["enabled"] and x["persona"].role == "guest"]
        return [x["persona"] for x in sorted(rows, key=lambda x: (x["sort"], x["persona"].id))]

    def default_members(self) -> list[str]:
        rows = [x for x in self._load().values() if x["enabled"] and x["in_default"] and x["persona"].role == "guest"]
        ids = [x["persona"].id for x in sorted(rows, key=lambda x: (x["sort"], x["persona"].id))]
        return ids or [p.id for p in self.guests()[:4]]

    # ---------------------------------------------------------- 管理端
    def admin_list(self) -> list[dict]:
        counts = {}
        if self.engine is not None:
            with self.engine.connect() as conn:
                counts = dict(conn.execute(select(persona_versions.c.persona_id, func.count()).group_by(persona_versions.c.persona_id)).all())
        rows = sorted(self._load().items(), key=lambda kv: (kv[1]["persona"].role != "host", kv[1]["sort"], kv[0]))
        return [x["persona"].public() | {"enabled": x["enabled"], "in_default": x["in_default"], "sort": x["sort"], "builtin": x["builtin"],
                                         "custom": x["custom"], "saved_versions": counts.get(pid, 0)} for pid, x in rows]

    def detail(self, pid: str) -> dict:
        x = self._load().get(pid)
        if x is None:
            raise KeyError(pid)
        versions = []
        with self.engine.connect() as conn:
            for r in conn.execute(select(persona_versions).where(persona_versions.c.persona_id == pid).order_by(persona_versions.c.version.desc())):
                versions.append({"version": r.version, "note": r.note, "created_at": r.created_at.isoformat(), "created_by": r.created_by})
        files = builtin.all_personas()
        p = x["persona"]
        return (p.public() | {"enabled": x["enabled"], "in_default": x["in_default"], "sort": x["sort"], "builtin": x["builtin"], "custom": x["custom"],
                              "content": self._content(pid, p.version if x["custom"] else None), "versions": versions,
                              "builtin_version": files[pid].version if pid in files else None})

    def _content(self, pid: str, version: int | None) -> str:
        if version is None:
            path = builtin.DIR / f"{pid}.md"
            return path.read_text(encoding="utf-8") if path.exists() else ""
        with self.engine.connect() as conn:
            row = conn.execute(select(persona_versions.c.content).where(persona_versions.c.persona_id == pid, persona_versions.c.version == version)).first()
        if row is None:
            raise KeyError(version)
        return row.content

    def version_content(self, pid: str, version: int | None) -> str:
        return self._content(pid, version)

    def _setting(self, conn, pid: str, **fields) -> None:
        exists = conn.execute(select(persona_settings.c.persona_id).where(persona_settings.c.persona_id == pid)).first()
        if exists:
            conn.execute(update(persona_settings).where(persona_settings.c.persona_id == pid).values(updated_at=_now(), **fields))
        else:
            x = (self._cache or {}).get(pid)
            base = {"enabled": x["enabled"] if x else True, "in_default": x["in_default"] if x else False, "sort": x["sort"] if x else 99,
                    "current_version": None}
            conn.execute(insert(persona_settings).values(persona_id=pid, updated_at=_now(), **(base | fields)))

    def save(self, pid: str | None, content: str, note: str, user_id: int | None) -> dict:
        """保存为新的一版并立刻启用。pid 为空表示新建角色。"""
        p = validate(content, pid)
        known = self._load()
        if pid is None and p.id in known:
            raise PersonaError(f"已经有 id 为 {p.id} 的角色了，换一个 id")
        if p.role == "host" and any(x["persona"].role == "host" and k != p.id for k, x in known.items()):
            raise PersonaError("主持人只能有一个")
        files = builtin.all_personas()
        with self.engine.begin() as conn:
            top = conn.execute(select(func.max(persona_versions.c.version)).where(persona_versions.c.persona_id == p.id)).scalar() or 0
            version = max(top, files[p.id].version if p.id in files else 0) + 1
            conn.execute(insert(persona_versions).values(persona_id=p.id, version=version, content=_with_version(content, version),
                                                         note=(note or "")[:200], created_by=user_id, created_at=_now()))
            self._setting(conn, p.id, current_version=version)
        self.invalidate()
        return self.detail(p.id)

    def use_version(self, pid: str, version: int | None) -> dict:
        """切到某一版；version 为空 = 回到出厂设置（只有内置角色可以）。"""
        if pid not in self._load():
            raise KeyError(pid)
        if version is None and pid not in builtin.all_personas():
            raise PersonaError("这个角色不是内置的，没有出厂设置可以回")
        if version is not None:
            validate(self._content(pid, version), pid)
        with self.engine.begin() as conn:
            self._setting(conn, pid, current_version=version)
        self.invalidate()
        return self.detail(pid)

    def configure(self, pid: str, enabled: bool | None = None, in_default: bool | None = None, sort: int | None = None) -> dict:
        x = self._load().get(pid)
        if x is None:
            raise KeyError(pid)
        if x["persona"].role == "host" and enabled is False:
            raise PersonaError("主持人不能停用")
        fields = {k: v for k, v in (("enabled", enabled), ("in_default", in_default), ("sort", sort)) if v is not None}
        if fields:
            with self.engine.begin() as conn:
                self._setting(conn, pid, **fields)
            self.invalidate()
        return self.detail(pid)
