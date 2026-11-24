"""与 PatternLab 对数：同一批规则分别用 PatternLab 原代码和本项目引擎运行，逐项比较结果。

用法：
    python tools/parity_patternlab.py --patternlab <PatternLab>/app [--limit 0] [--out parity.json]

PatternLab 侧直接调用其 engine.load_stock / rules.signals / eligible / forward_returns / summarize，
只读其随包 CSV，不创建任务、不写入 PatternLab 的 runtime 目录。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from sixiang.config import load_settings
from sixiang.data.store import MarketStore
from sixiang.patterns.rules import TEMPLATES, validate_rule
from sixiang.patterns.study import run_study

TOL = 1e-9


def _pl_worker(args):
    """在 PatternLab 代码下处理一批股票，对每条规则返回与其 Workbench.run 相同的中间结果。"""
    app_dir, paths, rules, calendar = args
    sys.path.insert(0, app_dir)
    import engine as pl  # noqa: E402  PatternLab
    from rules import signals  # noqa: E402
    calendar = pd.DatetimeIndex(calendar)
    out = [{"selected": [], "events": [], "raw": 0, "base": {}, "errors": []} for _ in rules]
    for code, path in paths:
        try:
            full = pl.load_stock(path)
        except Exception as exc:
            for o in out:
                o["errors"].append({"code": code, "error": str(exc)})
            continue
        for k, rule in enumerate(rules):
            o = out[k]
            df = full[full.date <= rule["asof"]].copy()
            if len(df) < rule["min_bars"]:
                continue
            ok = pl.eligible(df, rule)
            mask, details = signals(df, rule)
            mask &= ok
            in_period = df.date >= rule["start"]
            returns = pl.forward_returns(df, calendar, rule["horizons"], code)
            if df.date.iloc[-1].strftime("%Y-%m-%d") == rule["asof"] and mask.iloc[-1]:
                o["selected"].append(code)
            positions = np.flatnonzero((mask & in_period).to_numpy())
            prev = -100000
            for i in positions:
                if i - prev > rule["cooldown"]:
                    prev = i
                    o["events"].append({"code": code, "name": df.iloc[i]["name"], "date": df.date.iloc[i].strftime("%Y-%m-%d"),
                                        "returns": {str(h): float(returns[h][i]) for h in rule["horizons"]}})
            o["raw"] += len(positions)
            ix = np.flatnonzero((ok & in_period).to_numpy())
            dates = df.date.iloc[ix].dt.strftime("%Y-%m-%d").tolist()
            for h in rule["horizons"]:
                for d, v in zip(dates, returns[h][ix]):
                    if np.isfinite(v):
                        b = o["base"].setdefault(d, {}).setdefault(str(h), [0.0, 0])
                        b[0] += float(v); b[1] += 1
    return out


def run_patternlab(app_dir: Path, daily_dir: Path, rules: list[dict], limit: int, workers: int):
    sys.path.insert(0, str(app_dir))
    import engine as pl  # noqa: E402
    files = sorted(p for p in daily_dir.glob("*.csv") if len(p.stem) == 8 and p.stem[:2] in ("sh", "sz", "bj") and p.stem[2:].isdigit())
    if limit:
        files = files[:limit]
    cal = []
    for code in ("sh600000", "sz000001", "sh600519"):
        p = daily_dir / f"{code}.csv"
        cal.extend(pd.read_csv(p, encoding="gbk", skiprows=1, usecols=["交易日期"])["交易日期"].tolist())
    calendar = pd.DatetimeIndex(sorted(set(pd.to_datetime(cal))))
    calendar = calendar[calendar <= pd.Timestamp(rules[0]["asof"])]
    batches = [(str(app_dir), [(p.stem, str(p)) for p in files[i:i + 48]], rules, calendar.to_numpy()) for i in range(0, len(files), 48)]
    merged = [{"selected": [], "events": [], "raw": 0, "base": {}, "errors": []} for _ in rules]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(_pl_worker, batches):
            for m, o in zip(merged, part):
                m["selected"] += o["selected"]; m["events"] += o["events"]; m["raw"] += o["raw"]; m["errors"] += o["errors"]
                for d, hs in o["base"].items():
                    for h, (s, n) in hs.items():
                        b = m["base"].setdefault(d, {}).setdefault(h, [0.0, 0]); b[0] += s; b[1] += n
    results = []
    for m, rule in zip(merged, rules):
        baseline = {d: {h: s / n for h, (s, n) in hs.items() if n} for d, hs in m["base"].items()}
        summary, years = pl.summarize(m["events"], rule["horizons"], baseline)
        results.append({"summary": summary, "years": years, "selected": sorted(m["selected"]), "events": m["events"],
                        "raw_signals": m["raw"], "errors": m["errors"]})
    return results


def _close(a, b) -> bool:
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)) or (isinstance(b, float) and math.isnan(b)):
        return (a is None or (isinstance(a, float) and math.isnan(a))) and (b is None or (isinstance(b, float) and math.isnan(b)))
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def compare(name: str, ours: dict, theirs: dict) -> dict:
    diffs = []
    if ours["raw_signals"] != theirs["raw_signals"]:
        diffs.append(f"原始信号数 {ours['raw_signals']} vs {theirs['raw_signals']}")
    if len(ours["events"]) != len(theirs["events"]):
        diffs.append(f"事件数 {len(ours['events'])} vs {len(theirs['events'])}")
    ours_sel = sorted(s["code"] for s in ours["selected"])
    if ours_sel != theirs["selected"]:
        diffs.append(f"今日符合 {len(ours_sel)} vs {len(theirs['selected'])}")
    te = {(e["code"], e["date"]): e for e in theirs["events"]}
    mismatched = 0
    for e in ours["events"]:
        t = te.get((e["code"], e["date"]))
        if t is None or any(not _close(e["returns"][h], t["returns"][h] if np.isfinite(t["returns"][h]) else None) for h in e["returns"]):
            mismatched += 1
    if mismatched:
        diffs.append(f"{mismatched} 个事件的日期或收益不一致")
    for a, b in zip(ours["summary"], theirs["summary"]):
        for key in ("valid", "unavailable", "win_rate", "mean", "median", "p10", "p90", "excess_mean", "excess_n"):
            if not _close(a[key], b[key]):
                diffs.append(f"{a['horizon']} 日 {key}: {a[key]} vs {b[key]}")
    for a, b in zip(ours["years"], theirs["years"]):
        if a["year"] != b["year"] or a["valid"] != b["valid"] or not _close(a["mean"], b["mean"]):
            diffs.append(f"年度 {a['year']}/{a['horizon']} 不一致"); break
    return {"name": name, "match": not diffs, "diffs": diffs, "events": len(ours["events"]), "selected": len(ours_sel),
            "summary": [{k: r[k] for k in ("horizon", "valid", "win_rate", "mean", "excess_mean")} for r in ours["summary"]]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patternlab", required=True, type=Path, help="PatternLab 的 app 目录")
    ap.add_argument("--limit", type=int, default=0, help="只比较前 N 只股票（调试用；0 为全市场）")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path, default=Path("parity-result.json"))
    args = ap.parse_args()
    app = args.patternlab.resolve()
    settings = json.loads((app / "settings.json").read_text(encoding="utf-8"))
    daily_dir = (app / settings["data"]).resolve()

    store = MarketStore(load_settings().market_dir)
    snap = store.snapshot()
    rules = [validate_rule(dict(t), snap.data_end) for t in TEMPLATES]
    if args.limit:
        keep = sorted(snap.row_groups)[:args.limit]
        snap = snap.__class__(snap.version_id, snap.path, snap.manifest, snap.daily_meta, {c: snap.row_groups[c] for c in keep}, snap.calendar)

    t = time.time()
    theirs = run_patternlab(app, daily_dir, rules, args.limit, args.workers)
    t_pl = time.time() - t
    report = []
    t = time.time()
    for rule, th in zip(rules, theirs):
        ours = run_study(snap, rule, workers=args.workers)
        report.append(compare(rule["name"], ours, th))
    t_ours = time.time() - t
    result = {"data_version": snap.version_id, "stocks": len(snap.row_groups), "patternlab_seconds": round(t_pl, 1),
              "ours_seconds": round(t_ours, 1), "all_match": all(r["match"] for r in report), "templates": report}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in report:
        print(("一致  " if r["match"] else "不一致"), r["name"], f"事件 {r['events']}", f"今日 {r['selected']}", *r["diffs"][:5])
    print(f"PatternLab {t_pl:.0f}s（6 条规则一次读取）/ 本项目 {t_ours:.0f}s（6 条规则分别运行）")


if __name__ == "__main__":
    main()
