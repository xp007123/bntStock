"""研究之间的对比、增减一条条件（从 PatternLab research_views 迁移）。"""
from __future__ import annotations

import statistics
from copy import deepcopy

from ..patterns.library import fingerprint
from ..patterns.rules import RuleError, validate_rule

COMPARE_KEYS = ("start", "asof", "markets", "min_bars", "exclude_st", "cooldown", "horizons")
NOTE = "同区间历史事件对照，不是独立样本外验证；更多条件通常减少样本，不能仅凭最高收益选择参数。"


def compare(left: dict, right: dict, left_result: dict, right_result: dict, same_data: bool | None = None) -> dict:
    """left/right 为任务元数据，*_result 为完整结果（含 events）。same_data：两边是否用同一份日线行情。"""
    differences = [k for k in COMPARE_KEYS if left["rule"].get(k) != right["rule"].get(k)]
    if not (same_data if same_data is not None else left["data_version"] == right["data_version"]):
        differences.append("data_version")
    if left_result["errors"] or right_result["errors"]:
        differences.append("coverage_errors")
    lf = {fingerprint(c) for c in left["rule"]["conditions"]}
    rf = {fingerprint(c) for c in right["rule"]["conditions"]}
    le = {(e["code"], e["date"]) for e in left_result["events"]}
    re_ = {(e["code"], e["date"]) for e in right_result["events"]}
    side = lambda m, r: {"id": m["id"], "name": m["name"], "rule": m["rule"], "data_version": m["data_version"], "data_end": m["data_end"],
                         "summary": r["summary"], "years": r["years"], "events": len(r["events"]), "stocks": r["stocks"],
                         "selected": len(r["selected"]), "change": m.get("comparison_change")}
    return {
        "left": side(left, left_result), "right": side(right, right_result),
        "comparable": not differences, "differences": differences,
        "common_conditions": [c for c in left["rule"]["conditions"] if fingerprint(c) in rf],
        "only_left": [c for c in left["rule"]["conditions"] if fingerprint(c) not in rf],
        "only_right": [c for c in right["rule"]["conditions"] if fingerprint(c) not in lf],
        "overlap": {"common": len(le & re_), "only_left": len(le - re_), "only_right": len(re_ - le)},
        "note": NOTE,
    }


def variant_rule(base: dict, raw: dict, data_end: str) -> tuple[dict, dict]:
    """在原研究上去掉或增加一条条件，返回 (新规则, 变更说明)。"""
    if not isinstance(raw, dict) or set(raw) - {"action", "index", "condition"}:
        raise RuleError("增减条件请求格式错误")
    rule = deepcopy(base["rule"])
    action = raw.get("action")
    if action == "remove":
        index = raw.get("index")
        if type(index) is not int or not 0 <= index < len(rule["conditions"]):
            raise RuleError("请选择要去掉的条件")
        if len(rule["conditions"]) <= 1:
            raise RuleError("至少保留一条条件；单条件研究可先增加条件")
        removed = rule["conditions"].pop(index)
        change, verb = {"action": "remove", "index": index, "condition": removed}, "去掉"
    elif action == "add":
        if len(rule["conditions"]) >= 16:
            raise RuleError("已有 16 条条件，可先去掉一条")
        candidate = validate_rule({**rule, "conditions": [raw.get("condition")]}, data_end)["conditions"][0]
        if fingerprint(candidate) in {fingerprint(c) for c in rule["conditions"]}:
            raise RuleError("这条条件已在原研究中，请选择另一条或修改参数")
        rule["conditions"].append(candidate)
        change, verb = {"action": "add", "condition": candidate}, "增加"
    else:
        raise RuleError("action 只能为 add 或 remove")
    rule["name"] = (base["name"][:32] + f" · {verb}「" + change["condition"]["label"][:35] + "」")[:80]
    rule["description"] = f"在原研究基础上{verb}一条条件；所有保留条件同时满足时触发。"
    return rule, change


def sort_events(events: list[dict], mode: str, horizon: int | None) -> list[dict]:
    """date：最近；best / worst：该周期收益最高 / 最低；typical：最接近中位数（最能代表一般情况）。"""
    if mode == "date" or horizon is None:
        return events
    key = str(horizon)
    valid = [e for e in events if e["returns"].get(key) is not None]
    if mode == "best":
        return sorted(valid, key=lambda e: (-e["returns"][key], e["date"], e["code"]))
    if mode == "worst":
        return sorted(valid, key=lambda e: (e["returns"][key], e["date"], e["code"]))
    if mode == "typical" and valid:
        median = statistics.median(e["returns"][key] for e in valid)
        return sorted(valid, key=lambda e: (abs(e["returns"][key] - median), e["date"], e["code"]))
    return valid
