"""名单的历史表现。全部用日线现算，没有任何手填的数字。

口径（页面上要原样告诉用户）：
- 买入价按当天开盘价（名单 09:25 才出，用户最早只能买在开盘）。
- “封板”= 当天收盘价等于涨停价；“摸板”= 当天最高价到过涨停价。
- 对照组一：同期全市场（不含 ST、科创板、北交所，和名单的选股范围一致）。
- 对照组二：同一天里，高开幅度不低于名单里最低那只、开盘没有直接涨停的其他股票。
  这一组用来回答“名单比随便挑一只同样高开的票强不强”。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 0.001


def _limit(code: pd.Series, prev_close: pd.Series) -> pd.Series:
    """按规则算涨停价：创业板 20%，其余 10%。四舍五入到分。"""
    pct = np.where(code.str.startswith("sz30"), 1.2, 1.1)
    return np.floor(prev_close * pct * 100 + 0.5 + 1e-6) / 100


def enrich(cur, picks: list[dict]) -> pd.DataFrame:
    """给每一条名单配上当天和下一个交易日的行情。还没有行情的（比如今天刚出的名单）结果列为空。"""
    p = pd.DataFrame(picks)
    if p.empty:
        return p
    cur.register("pick_codes", pd.DataFrame({"code": p.code.unique()}))
    d = cur.execute("""SELECT d.code, CAST(d.date AS VARCHAR) AS date, open, high, low, close, prev_close AS pc, adj_factor
                       FROM daily d JOIN pick_codes USING (code) WHERE d.date >= ? ORDER BY d.code, d.date""", [p.date.min()]).df()
    g = d.groupby("code")
    for col in ("open", "close"):
        d[f"next_{col}"] = g[col].shift(-1) * g.adj_factor.shift(-1) / d.adj_factor   # 复权到当天口径，跨除权日也可比
    d["next_date"] = g.date.shift(-1)
    m = p.merge(d, on=["code", "date"], how="left")
    if "limit_price" not in m:                 # 有的策略出名单时不记涨停价：按规则现算
        m["limit_price"] = np.nan
    limit = m.limit_price.fillna(pd.Series(_limit(m.code, m.pc), index=m.index))
    has = m.open.notna()
    m["open_pct"] = m.open / m.pc - 1
    m["day_pct"] = m.close / m.pc - 1
    m["intraday"] = m.close / m.open - 1
    m["sealed"] = np.where(has, m.close >= limit - EPS, None)
    m["touched"] = np.where(has, m.high >= limit - EPS, None)
    m["next_open_ret"] = m.next_open / m.open - 1
    m["next_close_ret"] = m.next_close / m.open - 1
    return m


def _block(x: pd.DataFrame) -> dict | None:
    x = x[x.open.notna()]
    if x.empty:
        return None
    nxt = x.next_open_ret.dropna()
    return {"n": int(len(x)), "sealed_rate": float(x.sealed.astype(bool).mean()), "touched_rate": float(x.touched.astype(bool).mean()),
            "open_pct_median": float(x.open_pct.median()),
            "intraday_mean": float(x.intraday.mean()), "intraday_median": float(x.intraday.median()), "intraday_win": float((x.intraday > 0).mean()),
            "day_up_rate": float((x.day_pct > 0).mean()),
            "next_open_mean": float(nxt.mean()) if len(nxt) else None, "next_open_win": float((nxt > 0).mean()) if len(nxt) else None}


def _baselines(cur, m: pd.DataFrame) -> dict:
    start, end = m.date.min(), m.date.max()
    b = cur.execute("""SELECT code, CAST(date AS VARCHAR) AS date, open, high, close, prev_close AS pc FROM daily
                       WHERE date >= ? AND date <= ? AND code NOT LIKE 'bj%' AND code NOT LIKE 'sh68%'
                         AND name NOT LIKE '%ST%' AND open > 0 AND prev_close > 0""", [start, end]).df()
    limit = _limit(b.code, b.pc)
    b["sealed"], b["touched"] = b.close >= limit - EPS, b.high >= limit - EPS
    b["open_limit"] = b.open >= limit - EPS
    b["intraday"], b["open_pct"] = b.close / b.open - 1, b.open / b.pc - 1

    def block(x: pd.DataFrame) -> dict | None:
        if x.empty:
            return None
        return {"n": int(len(x)), "sealed_rate": float(x.sealed.mean()), "touched_rate": float(x.touched.mean()),
                "intraday_mean": float(x.intraday.mean()), "intraday_win": float((x.intraday > 0).mean())}

    floor = m.groupby("date").open_pct.min().rename("floor")
    same = b.merge(floor, on="date")
    picked = set(zip(m.date, m.code))
    same = same[(same.open_pct >= same.floor) & ~same.open_limit]
    same = same[[k not in picked for k in zip(same.date, same.code)]]
    return {"market": block(b), "same_gap": block(same)}


def summarize(cur, m: pd.DataFrame, recent_days: int = 60) -> dict:
    """整体、最近、分名次、分板块、分月份，以及两组对照。"""
    done = m[m.open.notna()]
    if done.empty:
        return {"range": None}
    days = sorted(done.date.unique())
    per_day = done.groupby("date").agg(sealed=("sealed", lambda s: int(s.astype(bool).sum())), intraday=("intraday", "mean"))
    recent = done[done.date >= days[-recent_days]] if len(days) > recent_days else None
    month = done.assign(month=done.date.str[:7])
    return {
        "range": {"start": days[0], "end": days[-1], "days": len(days), "n": int(len(done))},
        "overall": _block(done),
        "recent": ({"days": recent_days, "start": days[-recent_days], **_block(recent)} if recent is not None else None),
        "per_day": {"any_sealed_rate": float((per_day.sealed > 0).mean()), "sealed_mean": float(per_day.sealed.mean()),
                    "up_day_rate": float((per_day.intraday > 0).mean())},
        "by_rank": [{"label": label, **b} for label, b in (
            ("第 1 名", _block(done[done["rank"] == 1])), ("第 2–3 名", _block(done[done["rank"].between(2, 3)])),
            ("第 4–10 名", _block(done[done["rank"] >= 4]))) if b],
        "by_board": [{"label": str(k), **_block(x)} for k, x in done.groupby("board") if len(x) >= 30],
        "by_month": [{"label": k, **_block(x)} for k, x in month.groupby("month")],
        "baseline": _baselines(cur, done),
    }


def follow(cur, m: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    """趋势类名单：入选之后怎么样。入选价按当天开盘价（前复权口径，跨除权可比），最多看 horizon 个交易日。

    加三列：since_days 已经过了几个交易日（0 = 只有当天）、since_ret 到那天收盘的涨跌、since_max 期间最高价比入选价高多少。
    行情还没到入选那天的（今天刚出的名单）三列为空。
    另带两列给盘中用：base 入选价（复权后）、adj_last 最近一根日线的复权因子（实时价 × adj_last / base 就是盘中涨了多少）。
    """
    m = m.copy()
    for c in ("since_days", "since_ret", "since_max", "base", "adj_last"):
        m[c] = np.nan
    if m.empty:
        return m
    cur.register("follow_codes", pd.DataFrame({"code": m.code.unique()}))
    d = cur.execute("""SELECT code, CAST(date AS VARCHAR) AS date, open, high, close, adj_factor
                       FROM daily JOIN follow_codes USING (code) WHERE date >= ? AND open > 0 ORDER BY code, date""", [m.date.min()]).df()
    groups = {c: (g.date.to_numpy(), (g.open * g.adj_factor).to_numpy(), (g.high * g.adj_factor).to_numpy(), (g.close * g.adj_factor).to_numpy(),
                  float(g.adj_factor.iloc[-1]))
              for c, g in d.groupby("code")}
    days, rets, maxs, bases, adjs = [], [], [], [], []
    for code, date in zip(m.code, m.date):
        g = groups.get(code)
        i = np.searchsorted(g[0], date) if g is not None else 0
        if g is None or i >= len(g[0]) or g[0][i] != date:
            days.append(np.nan); rets.append(np.nan); maxs.append(np.nan); bases.append(np.nan); adjs.append(np.nan)
            continue
        j = min(i + horizon, len(g[0]) - 1)
        base = g[1][i]
        days.append(j - i); rets.append(g[3][j] / base - 1); maxs.append(g[2][i:j + 1].max() / base - 1)
        bases.append(base); adjs.append(g[4])
    m["since_days"], m["since_ret"], m["since_max"], m["base"], m["adj_last"] = days, rets, maxs, bases, adjs
    return m
