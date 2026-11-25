"""形态测试接口：模板、校验、提交任务、进度、结果、事件、个股解释。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from ...auth.deps import current_user
from ...auth.service import User
from ...data.store import NoDataVersion
from ...patterns.rules import DEFAULTS, FIELDS, FUNCS, OPS, TEMPLATES, RuleError, validate_rule
from ...patterns.library import CATEGORIES, LIBRARY
from ...patterns.study import explain_stock
from ...research.jobs import JobError, JobManager, rule_hash
from ...research.views import compare as compare_jobs, sort_events, variant_rule

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def _job(request: Request, jid: str, user: User) -> dict:
    """只能访问自己的研究（管理员可访问全部）。"""
    try:
        meta = _jobs(request).get(jid)
    except KeyError as exc:
        raise HTTPException(404, "任务不存在") from exc
    if meta.get("owner") != user.id and not user.is_admin and not meta.get("system"):
        raise HTTPException(404, "任务不存在")
    return meta


@router.get("/methods")
def methods(request: Request):
    """方法库：每个内置模板按默认参数由系统算一次，所有人共用，点开就有结论。

    没算过（或行情更新后）在第一次有人查看时自动排队；算完之前返回进度。
    """
    jobs = _jobs(request)
    try:
        snap = request.app.state.market.snapshot()
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    system = [m for m in jobs.list() if m.get("system") and snap.same_market(m["data_version"])]
    out = []
    for index, tpl in enumerate(TEMPLATES):
        item = {"index": index, "name": tpl["name"], "description": tpl.get("description", ""), "conditions": len(tpl["conditions"])}
        try:
            digest = rule_hash(validate_rule(tpl, snap.data_end))
            latest = next((m for m in system if m["rule_hash"] == digest), None)
            if latest and latest["status"] == "failed":   # 算失败过：如实显示，不在每次查看时反复重排
                out.append(item | {"job": latest["id"], "status": "failed", "message": latest.get("message", "")})
                continue
            meta = jobs.submit(tpl, owner=None, context={"system": True})
        except (RuleError, NoDataVersion) as exc:
            out.append(item | {"status": "unavailable", "message": str(exc)})
            continue
        item |= {"job": meta["id"], "status": meta["status"], "progress": meta["progress"], "data_end": meta["data_end"]}
        if meta["status"] == "completed":
            r = jobs.result(meta["id"])
            item |= {"summary": r["summary"], "years": r["years"], "events": r["deduplicated_events"], "selected": len(r["selected"])}
        out.append(item)
    return {"methods": out}


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
def submit(request: Request, rule: dict = Body(..., embed=True), user: User = Depends(current_user)):
    return _submit(request, rule, user)


def _submit(request: Request, rule: dict, user: User, context: dict | None = None) -> dict:
    """提交并把用过的条件、整套规则保存到“我的条件 / 我的形态”。"""
    try:
        meta = _jobs(request).submit(rule, owner=user.id, context=context)
    except RuleError as exc:
        raise HTTPException(422, str(exc)) from exc
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    if not meta.get("reused"):
        try:
            meta["library_save"] = request.app.state.library.harvest(user.id, meta["rule"], meta["id"])
        except Exception as exc:  # 保存失败如实返回，不影响研究本身
            meta["library_save"] = {"conditions_added": 0, "warnings": [f"保存到我的条件失败：{exc}"]}
    return meta


@router.post("/jobs/{jid}/variant")
def variant(request: Request, jid: str, change: dict = Body(...), user: User = Depends(current_user)):
    """在已完成研究上去掉或增加一条条件，作为新研究运行，原研究保留。"""
    base = _job(request, jid, user)
    if base["status"] != "completed":
        raise HTTPException(409, "原研究尚未完成")
    snap = request.app.state.market.snapshot()
    if not snap.same_market(base["data_version"]):
        raise HTTPException(409, "原研究来自旧数据，请先用最新数据重跑，再增减条件对比")
    try:
        rule, detail = variant_rule(base, change, snap.data_end)
    except RuleError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _submit(request, rule, user, {"comparison_base": jid, "comparison_change": detail})


@router.post("/jobs/{jid}/rerun")
def rerun(request: Request, jid: str, user: User = Depends(current_user)):
    """用当前数据版本重新运行同一规则（旧研究保留原结果）。"""
    base = _job(request, jid, user)
    return _submit(request, base["rule"], user, {"rerun_of": jid})


@router.get("/compare")
def compare(request: Request, left: str, right: str, user: User = Depends(current_user)):
    if left == right:
        raise HTTPException(422, "请选择两条不同的研究")
    metas = [_job(request, j, user) for j in (left, right)]
    if any(m["status"] != "completed" for m in metas):
        raise HTTPException(409, "两条研究都完成后才能对比")
    snap = request.app.state.market.snapshot()
    dv = [m["data_version"] for m in metas]
    same = dv[0] == dv[1] or (snap.same_market(dv[0]) and snap.same_market(dv[1]))
    return compare_jobs(metas[0], metas[1], _jobs(request).result(left), _jobs(request).result(right), same_data=same)


@router.get("/library")
def library(request: Request, user: User = Depends(current_user)):
    """内置条件库 + 我的条件 / 我的形态。"""
    return {"categories": CATEGORIES, "modules": LIBRARY, **request.app.state.library.items(user.id)}


@router.post("/library/{kind}/{item_id}/remove")
def remove_library_item(request: Request, kind: Literal["conditions", "patterns"], item_id: int, user: User = Depends(current_user)):
    if not request.app.state.library.remove(user.id, kind, item_id):
        raise HTTPException(404, "条目不存在")
    return request.app.state.library.items(user.id)


@router.get("/jobs")
def list_jobs(request: Request, user: User = Depends(current_user)):
    return _jobs(request).list(owner=user.id)


@router.get("/jobs/{jid}")
def job(request: Request, jid: str, user: User = Depends(current_user)):
    return _job(request, jid, user)


@router.post("/jobs/{jid}/cancel")
def cancel(request: Request, jid: str, user: User = Depends(current_user)):
    _job(request, jid, user)
    return _jobs(request).cancel(jid)


def _result(request: Request, jid: str, user: User) -> dict:
    _job(request, jid, user)
    try:
        return _jobs(request).result(jid)
    except JobError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/jobs/{jid}/result")
def result(request: Request, jid: str, user: User = Depends(current_user)):
    """报告主体：统计、年度、今日符合名单。事件明细分页读取。"""
    r = _result(request, jid, user)
    return {k: v for k, v in r.items() if k != "events"} | {"event_total": len(r["events"])}


@router.get("/jobs/{jid}/events")
def events(request: Request, jid: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
           sort: Literal["date", "return", "best", "worst", "typical"] = "date", horizon: int | None = None, code: str | None = None,
           user: User = Depends(current_user)):
    items = _result(request, jid, user)["events"]
    if code:
        items = [e for e in items if e["code"] == code.lower()]
    items = sort_events(items, "best" if sort == "return" else sort, horizon)
    return {"total": len(items), "offset": offset, "items": items[offset:offset + limit]}


@router.get("/jobs/{jid}/explain/{code}")
def explain(request: Request, jid: str, code: str, date: str | None = None, user: User = Depends(current_user)):
    meta = _job(request, jid, user)
    snap = request.app.state.market.snapshot()
    if not snap.same_market(meta["data_version"]):
        raise HTTPException(409, "该研究使用旧数据版本；可查看原报告，重新运行后可在 K 线上查看入选原因")
    try:
        return explain_stock(snap, meta["rule"], code.lower(), date)
    except KeyError as exc:
        raise HTTPException(404, f"未找到 {code}") from exc
