"""判断的封存与揭晓。

封存：把当时的结论（概率、平均、最好最坏情况）原样保存，之后不再改动。
揭晓：该股从封存日收盘起走满 N 根日 K 后，按同样口径计算实际涨跌，与当时的判断并排展示。
结算在读取时进行（每次查看“我的判断”会先结算已到期的）。
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine

from .analysis.distribution import load, outcome
from .auth.db import judgments


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def estimate_due(asof: str, horizon: int) -> str:
    """按工作日估算第 N 个交易日（不含法定节假日，实际以交易日历为准）。"""
    d, left = dt.date.fromisoformat(asof), horizon
    while left > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d.isoformat()


def _position(r: float, pred: dict) -> str:
    """实际结果落在当时分布的哪个位置（大白话）。"""
    if r <= pred["p10"]:
        return "落在当时估计的“运气最差的一成”里"
    if r >= pred["p90"]:
        return "落在当时估计的“运气最好的一成”里"
    return "落在当时估计的正常范围内"


class Judgments:
    def __init__(self, engine: Engine):
        self.engine = engine

    def seal(self, user_id: int, answer: dict) -> dict:
        a = answer["analysis"]
        sim = a["similar"]
        base = a["all"]["breakeven_prob"] if answer["kind"] == "option" else a["all"]["up_prob"]
        pred = {"prob": answer["verdict"]["value"] / 100, "base_prob": base, "mean": answer["facts"][0]["value"],
                "p10": sim["p10"], "p90": sim["p90"], "median": sim["median"], "plain": answer["verdict"]["plain"],
                "voice": answer["voice"], "price": answer.get("price"), "close": a["close"], "similar_n": sim["n"], "elapsed": 0}
        with self.engine.begin() as conn:
            jid = conn.execute(insert(judgments).values(
                user_id=user_id, kind=answer["kind"], code=answer["code"], name=answer["name"], horizon=answer["horizon"],
                fee=None if answer["fee"] is None else repr(answer["fee"]), asof=answer["asof"], data_version=answer["data_version"],
                question=answer["question"], prediction_json=json.dumps(pred, ensure_ascii=False), status="sealed",
                due_estimate=estimate_due(answer["asof"], answer["horizon"]), created_at=_now())).inserted_primary_key[0]
        return self.get(user_id, jid)

    @staticmethod
    def _row(r) -> dict:
        return {"id": r.id, "kind": r.kind, "code": r.code, "name": r.name, "horizon": r.horizon,
                "fee": None if r.fee is None else float(r.fee), "asof": r.asof, "data_version": r.data_version, "question": r.question,
                "prediction": json.loads(r.prediction_json), "status": r.status, "due_estimate": r.due_estimate,
                "outcome": json.loads(r.outcome_json) if r.outcome_json else None,
                "created_at": r.created_at.isoformat(), "settled_at": r.settled_at.isoformat() if r.settled_at else None}

    def get(self, user_id: int, jid: int) -> dict:
        with self.engine.connect() as conn:
            r = conn.execute(select(judgments).where(judgments.c.id == jid, judgments.c.user_id == user_id)).first()
        if r is None:
            raise KeyError(jid)
        return self._row(r)

    def list(self, user_id: int) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(judgments).where(judgments.c.user_id == user_id).order_by(judgments.c.created_at.desc())).all()
        return [self._row(r) for r in rows]

    def settle(self, snapshot, user_id: int | None = None) -> int:
        """结算已到期的判断，返回结算数量；未到期的更新已走的交易日数。"""
        q = select(judgments).where(judgments.c.status == "sealed")
        if user_id is not None:
            q = q.where(judgments.c.user_id == user_id)
        with self.engine.connect() as conn:
            rows = conn.execute(q).all()
        settled = 0
        for r in rows:
            try:
                res = outcome(load(snapshot, r.code), r.asof, r.horizon)
            except KeyError:
                continue
            if res is None:
                continue
            pred = json.loads(r.prediction_json)
            if not res["done"]:
                if pred.get("elapsed") != res["elapsed"]:
                    pred["elapsed"] = res["elapsed"]
                    with self.engine.begin() as conn:
                        conn.execute(update(judgments).where(judgments.c.id == r.id).values(prediction_json=json.dumps(pred, ensure_ascii=False)))
                continue
            ret = res["return"]
            fee = float(r.fee) if r.fee else None
            res.update({"hit": bool(ret > (fee if fee is not None else 0)), "payoff": (max(ret, 0) - fee) if fee is not None else None,
                        "position": _position(ret, pred), "data_version": snapshot.version_id})
            with self.engine.begin() as conn:
                conn.execute(update(judgments).where(judgments.c.id == r.id).values(
                    status="settled", outcome_json=json.dumps(res, ensure_ascii=False), settled_at=_now()))
            settled += 1
        return settled

    def record(self, user_id: int) -> dict:
        """判断档案：已揭晓次数、命中次数，以及当时平均给出的概率（对照“说得准不准”）。"""
        items = [j for j in self.list(user_id) if j["status"] == "settled"]
        if not items:
            return {"settled": 0}
        hits = sum(1 for j in items if j["outcome"]["hit"])
        return {"settled": len(items), "hits": hits, "hit_rate": hits / len(items),
                "expected_rate": float(np.mean([j["prediction"]["prob"] for j in items]))}
