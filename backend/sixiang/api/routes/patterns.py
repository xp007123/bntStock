"""形态测试接口：模板、校验、提交任务、进度、结果、事件、个股解释。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, HTTPException, Query, Request

from ...data.store import NoDataVersion
from ...patterns.rules import DEFAULTS, FIELDS, FUNCS, OPS, TEMPLATES, RuleError, validate_rule
from ...patterns.study import explain_stock
from ...research.jobs import JobError, JobManager

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def _job(request: Request, jid: str) -> dict:
    try:
        return _jobs(request).get(jid)
    except KeyError as exc:
        raise HTTPException(404, "任务不存在") from exc


@router.get("/templates")
def templates():
    return {"templates": TEMPLATES, "defaults": DEFAULTS, "fields": FIELDS, "functions": FUNCS, "operators": OPS}


@router.post("/validate")
def validate(request: Request, rule: dict = Body(..., embed=True)):
    try:
        return validate_rule(rule, request.app.state.market.snapshot().data_end)
    except RuleError as exc:
        raise HTTPException(422, str(exc)) from exc
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/jobs")
def submit(request: Request, rule: dict = Body(..., embed=True)):
    try:
        return _jobs(request).submit(rule)
    except RuleError as exc:
        raise HTTPException(422, str(exc)) from exc
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/jobs")
def list_jobs(request: Request):
    return _jobs(request).list()


@router.get("/jobs/{jid}")
def job(request: Request, jid: str):
    return _job(request, jid)


@router.post("/jobs/{jid}/cancel")
def cancel(request: Request, jid: str):
    _job(request, jid)
    return _jobs(request).cancel(jid)


def _result(request: Request, jid: str) -> dict:
    _job(request, jid)
    try:
        return _jobs(request).result(jid)
    except JobError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/jobs/{jid}/result")
def result(request: Request, jid: str):
    """报告主体：统计、年度、今日符合名单。事件明细分页读取。"""
    r = _result(request, jid)
    return {k: v for k, v in r.items() if k != "events"} | {"event_total": len(r["events"])}


@router.get("/jobs/{jid}/events")
def events(request: Request, jid: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
           sort: Literal["date", "return"] = "date", horizon: int | None = None, code: str | None = None):
    items = _result(request, jid)["events"]
    if code:
        items = [e for e in items if e["code"] == code.lower()]
    if sort == "return" and horizon is not None:
        key = str(horizon)
        items = sorted(items, key=lambda e: (e["returns"].get(key) is None, -(e["returns"].get(key) or 0)))
    return {"total": len(items), "offset": offset, "items": items[offset:offset + limit]}


@router.get("/jobs/{jid}/explain/{code}")
def explain(request: Request, jid: str, code: str, date: str | None = None):
    meta = _job(request, jid)
    snap = request.app.state.market.snapshot()
    if snap.version_id != meta["data_version"]:
        raise HTTPException(409, "该研究使用旧数据版本；可查看原报告，重新运行后可在 K 线上查看入选原因")
    try:
        return explain_stock(snap, meta["rule"], code.lower(), date)
    except KeyError as exc:
        raise HTTPException(404, f"未找到 {code}") from exc
