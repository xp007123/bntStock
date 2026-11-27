"""文哥选股：口径照搬旧交易程序 bnt-qmt-trace-service（WengePrescreenService / WengeBullishTargetLoadTask）。

具体条件是平台自己的东西：只写在这个文件和内部文档里，不进接口、不上页面。

两步：
1. 每周一次基本面初筛（每周最后一个交易日收盘后，算下一周用的池子）。
   归母净利润同比 > 40%；每股未分配利润、每股资本公积在申万一级行业里都排前 30%（PERCENT_RANK ≤ 0.3）；
   每股收益为空或不为负；剔北交所（ST 由同花顺的全 A 板块成份那一侧剔掉）。
2. 每个交易日 09:26 多头判定：当天开盘价同时高于第 5、10、20 个交易日前的收盘价（前复权）。
   名单按每股未分配利润从高到低排。
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from ..data.ifind import IFindClient, from_ths, to_ths

log = logging.getLogger("sixiang.picks.wenge")

BACKTRACK_MONTHS = (3, 6, 9, 12)          # 月频财务数往回找的窗口：季报出来前当月常是空的
BATCH = 50
PERIODS = (5, 10, 20)
FIELDS = ("np_yoy", "undistri", "capital")
_IND = {"ths_np_atsopc_yoy_stock": "np_yoy", "ths_undistri_profit_ps_stock": "undistri", "ths_capital_reserve_ps_stock": "capital"}


def _is_bse(code: str) -> bool:
    n = code[2:]
    return code.startswith("bj") or n.startswith(("920", "43", "83", "87"))


def _last(values) -> float | None:
    for v in reversed(values or []):
        if v is not None and v != "":
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _months_before(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    m += 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


def _sequence(client: IFindClient, codes: list[str], start: dt.date, end: dt.date, indipara: list[dict]) -> dict[str, dict]:
    """date_sequence 按月取，一批 50 只，每个指标取窗口里最后一个非空值。"""
    out: dict[str, dict] = {}
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i + BATCH]
        body = {"codes": ",".join(to_ths(c) for c in batch), "startdate": start.isoformat(), "enddate": end.isoformat(),
                "functionpara": {"Interval": "M"}, "indipara": indipara}
        try:
            data = client.call("date_sequence", body)
        except Exception:  # noqa: BLE001  一批失败不影响别的批，和旧程序一样按空数据继续
            log.exception("date_sequence 批失败（%d 只）", len(batch))
            continue
        for t in data.get("tables") or []:
            table = t.get("table") or {}
            out[from_ths(t["thscode"])] = {k: _last(v) for k, v in table.items()}
    return out


def fundamentals(client: IFindClient, codes: list[str], week_start: dt.date, week_end: dt.date) -> dict[str, dict]:
    """np_yoy / undistri / capital / eps。窗口从 3 个月往回放到 12 个月，先拿到的（离得近的）为准。"""
    acc: dict[str, dict] = {c: {} for c in codes}
    para = [{"indicator": k, "indiparams": [""]} for k in _IND]
    remaining = list(codes)
    for depth in BACKTRACK_MONTHS:
        if not remaining:
            break
        got = _sequence(client, remaining, _months_before(week_start, depth) - dt.timedelta(days=1), week_end, para)
        for c in remaining:
            for k, field in _IND.items():
                if acc[c].get(field) is None and got.get(c, {}).get(k) is not None:
                    acc[c][field] = got[c][k]
        remaining = [c for c in remaining if any(acc[c].get(f) is None for f in FIELDS)]
    remaining = list(codes)
    for depth in BACKTRACK_MONTHS:
        if not remaining:
            break
        got = _sequence(client, remaining, _months_before(week_start, depth) - dt.timedelta(days=1), week_end,
                        [{"indicator": "ths_basic_eps_stock", "indiparams": ["", "100"]}])
        for c in remaining:
            v = got.get(c, {}).get("ths_basic_eps_stock")
            if v is not None:
                acc[c]["eps"] = v
        remaining = [c for c in remaining if acc[c].get("eps") is None]
    return acc


def industries(client: IFindClient, codes: list[str], date: dt.date) -> dict[str, str]:
    out = {}
    for i in range(0, len(codes), BATCH):
        try:
            data = client.call("basic_data_service", {"codes": ",".join(to_ths(c) for c in codes[i:i + BATCH]),
                                                      "indipara": [{"indicator": "ths_the_sw_industry_stock", "indiparams": ["100", date.strftime("%Y%m%d")]}]})
        except Exception:  # noqa: BLE001
            log.exception("行业批失败")
            continue
        for t in data.get("tables") or []:
            v = ((t.get("table") or {}).get("ths_the_sw_industry_stock") or [None])[0]
            if v:
                out[from_ths(t["thscode"])] = v
    return out


def universe(client: IFindClient, date: dt.date) -> dict[str, str]:
    """全 A 板块成份（同花顺那一侧已剔 ST），去掉北交所。code → 名称。"""
    data = client.call("data_pool", {"reportname": "p03291", "functionpara": {"date": date.strftime("%Y%m%d"), "blockname": "001005010",
                                                                              "iv_type": "allcontract"}, "outputpara": "p03291_f002,p03291_f004"})
    table = (data.get("tables") or [{}])[0].get("table", {})
    codes, names = table.get("p03291_f002", []), table.get("p03291_f004", [])
    out = {}
    for c, n in zip(codes, names):
        if c.endswith((".SH", ".SZ", ".BJ")):
            code = from_ths(c)
            if not _is_bse(code):
                out[code] = n
    return out


def screen(rows: pd.DataFrame) -> pd.DataFrame:
    """初筛：行业内 PERCENT_RANK（降序，空值排最后）≤ 0.3，净利润同比 > 40，EPS 为空或 ≥ 0。"""
    x = rows[rows.sw.notna() & (rows.eps.isna() | (rows.eps >= 0))].copy()
    if x.empty:
        return x

    def prank(col: str) -> pd.Series:
        # MySQL 的 PERCENT_RANK() OVER (PARTITION BY sw ORDER BY col DESC)：(名次-1)/(组内行数-1)，并列取最小名次，NULL 排在最后
        r = x.groupby("sw")[col].rank(method="min", ascending=False, na_option="bottom")
        n = x.groupby("sw")[col].transform("size")
        return ((r - 1) / (n - 1)).where(n > 1, 0.0)

    x["undistri_pct"], x["capital_pct"] = prank("undistri"), prank("capital")
    return x[(x.np_yoy > 40) & (x.undistri_pct <= 0.3) & (x.capital_pct <= 0.3)]


def prescreen(client: IFindClient, week_start: dt.date, week_end: dt.date, pool_date: dt.date) -> list[dict]:
    """算出某一周用的初筛池子：[{code, name, undistri}]。"""
    names = universe(client, pool_date)
    codes = sorted(names)
    fund = fundamentals(client, codes, week_start, week_end)
    sw = industries(client, codes, pool_date)
    rows = pd.DataFrame([{"code": c, "name": names[c], "sw": sw.get(c), **{k: fund[c].get(k) for k in (*FIELDS, "eps")}} for c in codes])
    for k in (*FIELDS, "eps"):
        rows[k] = pd.to_numeric(rows[k], errors="coerce")
    passed = screen(rows)
    log.info("文哥初筛 %s~%s：全 A %d 只，有行业 %d，通过 %d", week_start, week_end, len(rows), int(rows.sw.notna().sum()), len(passed))
    return [{"code": r.code, "name": r.name, "undistri": None if pd.isna(r.undistri) else float(r.undistri)} for r in passed.itertuples()]


def past_closes(cur, codes: list[str], day: dt.date) -> pd.DataFrame:
    """每只票第 5/10/20 个交易日前的收盘价，前复权到 day 前一个交易日的口径。列：code, c5, c10, c20, prev_close。"""
    cur.register("wenge_codes", pd.DataFrame({"code": codes}))
    d = cur.execute("""SELECT code, date, close, adj_factor FROM daily JOIN wenge_codes USING (code)
                       WHERE date < ? AND date >= ? AND close IS NOT NULL ORDER BY code, date""",
                    [day, day - dt.timedelta(days=60)]).df()
    out = []
    for code, g in d.groupby("code"):
        g = g.tail(max(PERIODS))
        if len(g) < max(PERIODS):
            continue
        base = g.adj_factor.iloc[-1]
        adj = g.close * g.adj_factor / base
        out.append({"code": code, **{f"c{p}": float(adj.iloc[-p]) for p in PERIODS}, "prev_close": float(g.close.iloc[-1])})
    return pd.DataFrame(out, columns=["code", *[f"c{p}" for p in PERIODS], "prev_close"])


def bullish(pool: list[dict], closes: pd.DataFrame, opens: dict[str, float]) -> list[dict]:
    """多头判定：当天开盘价同时高于第 5、10、20 个交易日前的收盘价。按每股未分配利润从高到低排。"""
    by = closes.set_index("code").to_dict("index") if len(closes) else {}
    hit = []
    for p in pool:
        o, c = opens.get(p["code"]), by.get(p["code"])
        if not o or o <= 0 or c is None:          # 集合竞价零成交、停牌、上市不满 20 天
            continue
        if all(o > c[f"c{n}"] for n in PERIODS):
            hit.append({**p, "open": o, "prev_close": c["prev_close"]})
    hit.sort(key=lambda r: (-(r["undistri"] or 0), r["code"]))
    return [{"rank": i + 1, "code": r["code"], "name": r["name"], "undistri": r["undistri"], "open": r["open"],
             "open_pct": r["open"] / r["prev_close"] - 1 if r["prev_close"] else None} for i, r in enumerate(hit)]


def realtime_open(client: IFindClient, codes: list[str]) -> dict[str, float]:
    """iFinD 实时行情里的今日开盘价（行情 MCP 取不到时的备用）。"""
    out = {}
    for i in range(0, len(codes), BATCH):
        try:
            data = client.call("real_time_quotation", {"codes": ",".join(to_ths(c) for c in codes[i:i + BATCH]), "indicators": "open"})
        except Exception:  # noqa: BLE001
            log.exception("iFinD 实时开盘价失败")
            continue
        for t in data.get("tables") or []:
            v = _last((t.get("table") or {}).get("open"))
            if v:
                out[from_ths(t["thscode"])] = v
    return out


def week_of(day: dt.date, trade_days: list[dt.date]) -> tuple[dt.date, dt.date]:
    """day 所在那一周（周一到周日）里的第一个和最后一个交易日。"""
    mon = day - dt.timedelta(days=day.weekday())
    days = [d for d in trade_days if mon <= d <= mon + dt.timedelta(days=6)]
    return (days[0], days[-1]) if days else (day, day)


# ---------------------------------------------------------------- 入选之后：今天开不开仓
# 口径照搬实盘程序最后的线上版（WengeEntryStrategy 的过滤闸门，只取和股票有关的那几道）。
# 和账户有关的（满仓、已持有、止盈后的冷却期）这里判断不了。原因只存库里备查，不进接口、不上页面。
GAIN_LOW_5D_MAX = 0.17        # 从近 5 日最低点到昨收，涨幅超过这个不开
SURGE_MAX = 0.045             # 昨天冲高回落超过这个不开
GAP_MAX = 0.049               # 今天高开超过这个不开
AMPLITUDE_MIN = 0.008         # 近 6 日平均振幅低于这个不开
AMOUNT_MIN = 3e8              # 近 5 日平均成交额低于 3 亿不开
BOARD_INDEX = {"main": "sz399303", "gem": "sz399006", "star": "sh000680"}     # 国证 2000 / 创业板指 / 科创 50


def board(code: str) -> str:
    n = code[2:]
    return "gem" if n.startswith("30") else "star" if n.startswith("68") else "main"


def _limit_up(code: str, prev_close: float) -> float:
    pct = 1.2 if board(code) in ("gem", "star") else 1.1
    return int(prev_close * pct * 100 + 0.5 + 1e-6) / 100


def prior_bars(cur, codes: list[str], day: dt.date, n: int = 25) -> pd.DataFrame:
    """每只票 day 之前最近 n 根有成交的日线。"""
    cur.register("wenge_gate_codes", pd.DataFrame({"code": codes}))
    d = cur.execute("""SELECT code, date, open, high, low, close, amount, adj_factor FROM daily JOIN wenge_gate_codes USING (code)
                       WHERE date < ? AND date >= ? AND open > 0 AND volume > 0 ORDER BY code, date""",
                    [day, day - dt.timedelta(days=n * 3)]).df()
    return d.groupby("code").tail(n)


def index_declining(cur, day: dt.date, now: dict[str, float]) -> dict[str, bool]:
    """每个板块的指数是不是“双下拐”：现在的点位同时低于第 5、第 10 个交易日前的收盘。now：指数代码 → 现在的点位。"""
    out = {}
    for b, code in BOARD_INDEX.items():
        closes = [r[0] for r in cur.execute("SELECT close FROM indices WHERE code = ? AND date < ? ORDER BY date DESC LIMIT 10", [code, day]).fetchall()]
        v = now.get(code)
        out[b] = bool(v and len(closes) >= 10 and v < closes[4] and v < closes[9])
    return out


def skip_reasons(bars: pd.DataFrame, opens: dict[str, float], declining: dict[str, bool]) -> dict[str, str]:
    """哪些票今天不开仓：code → 原因（内部代号）。没出现在结果里的就是可以开。"""
    out: dict[str, str] = {}
    groups = {c: g for c, g in bars.groupby("code")}
    for code, o in opens.items():
        g = groups.get(code)
        if g is None or len(g) < 5:
            out[code] = "history"
            continue
        adj = g.adj_factor / g.adj_factor.iloc[-1]
        closes, lows = (g.close * adj).to_numpy(), (g.low * adj).to_numpy()
        t1 = g.iloc[-1]
        low5 = lows[-5:].min()
        top = max(t1.open, t1.close)
        amp = ((g.high - g.low) / g.close.shift(1)).iloc[-6:].dropna()
        if (closes[-1] - low5) / low5 > GAIN_LOW_5D_MAX:
            out[code] = "gain"
        elif (t1.high - top) / top > SURGE_MAX:
            out[code] = "surge"
        elif (o - t1.close) / t1.close > GAP_MAX:
            out[code] = "gap"
        elif (amp.mean() if len(amp) else 0) < AMPLITUDE_MIN:
            out[code] = "amplitude"
        elif g.amount.iloc[-5:].mean() < AMOUNT_MIN:
            out[code] = "amount"
        elif o >= _limit_up(code, t1.close) - 1e-6:
            out[code] = "limit"
        elif declining.get(board(code)):
            out[code] = "index"
        elif len(closes) >= 19 and o < closes[-19:].mean():
            out[code] = "ma20"
    return out
