"""我的条件、我的形态：提交研究时自动保存，按用户隔离（对应 PatternLab research_library）。

- 我的条件：研究中用过、且不在内置条件库里的条件，增减条件时可直接选用；最多 200 条。
- 我的形态：整套规则（条件顺序与名称不影响去重），可一键重新运行；最多 100 套。
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine

from ..auth.db import user_conditions, user_patterns
from ..patterns.library import LIBRARY_FINGERPRINTS, canonical, fingerprint

MAX_CONDITIONS = 200
MAX_PATTERNS = 100
SETTING_KEYS = ("cooldown", "min_bars", "exclude_st", "markets", "horizons")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def pattern_key(rule: dict) -> str:
    conditions = sorted((canonical(c) for c in rule["conditions"]), key=lambda x: json.dumps(x, sort_keys=True))
    return fingerprint({"conditions": conditions, **{k: rule.get(k) for k in SETTING_KEYS}})


class UserLibrary:
    def __init__(self, engine: Engine):
        self.engine = engine

    def harvest(self, user_id: int, rule: dict, job_id: str) -> dict:
        added, warnings = 0, []
        with self.engine.begin() as conn:
            have = {r for (r,) in conn.execute(select(user_conditions.c.fingerprint).where(user_conditions.c.user_id == user_id))}
            count = len(have)
            for c in rule["conditions"]:
                fp = fingerprint(c)
                if fp in LIBRARY_FINGERPRINTS or fp in have:
                    continue
                if count >= MAX_CONDITIONS:
                    warnings.append("我的条件已满，部分条件未保存")
                    break
                conn.execute(insert(user_conditions).values(user_id=user_id, fingerprint=fp, name=c["label"][:120],
                                                            condition_json=json.dumps(c, ensure_ascii=False), source_job=job_id, created_at=_now()))
                have.add(fp); count += 1; added += 1
            key = pattern_key(rule)
            row = conn.execute(select(user_patterns.c.id).where(user_patterns.c.user_id == user_id, user_patterns.c.fingerprint == key)).first()
            if row:
                conn.execute(update(user_patterns).where(user_patterns.c.id == row.id).values(last_job=job_id, updated_at=_now()))
            elif conn.execute(select(func.count()).select_from(user_patterns).where(user_patterns.c.user_id == user_id)).scalar_one() < MAX_PATTERNS:
                conn.execute(insert(user_patterns).values(user_id=user_id, fingerprint=key, name=rule["name"][:120],
                                                          rule_json=json.dumps(rule, ensure_ascii=False), last_job=job_id, updated_at=_now()))
            else:
                warnings.append("我的形态已满，整套规则未保存")
        return {"conditions_added": added, "warnings": warnings}

    def items(self, user_id: int) -> dict:
        with self.engine.connect() as conn:
            conds = conn.execute(select(user_conditions).where(user_conditions.c.user_id == user_id).order_by(user_conditions.c.created_at.desc())).all()
            pats = conn.execute(select(user_patterns).where(user_patterns.c.user_id == user_id).order_by(user_patterns.c.updated_at.desc())).all()
        return {
            "conditions": [{"id": r.id, "name": r.name, "condition": json.loads(r.condition_json), "source_job": r.source_job} for r in conds],
            "patterns": [{"id": r.id, "name": r.name, "rule": json.loads(r.rule_json), "last_job": r.last_job,
                          "updated_at": r.updated_at.isoformat()} for r in pats],
        }

    def remove(self, user_id: int, kind: str, item_id: int) -> bool:
        table = user_conditions if kind == "conditions" else user_patterns
        with self.engine.begin() as conn:
            return conn.execute(delete(table).where(table.c.id == item_id, table.c.user_id == user_id)).rowcount > 0
