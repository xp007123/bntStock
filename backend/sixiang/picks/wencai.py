"""同花顺问财选股（iFinD 的 smart_stock_picking 接口）。口径照搬旧服务 bnt_stock_service 的 WenCaiService。"""
from __future__ import annotations

import datetime as dt
import re
import time

from ..data.ifind import IFindClient, IFindError, from_ths

URL = "https://ft.10jqka.com.cn/api/v1/smart_stock_picking"


def _cn(d: dt.date) -> str:
    return f"{d.year}年{d.month:02d}月{d.day:02d}日"


def sjm_query(day: dt.date, prev: dt.date, prev2: dt.date) -> str:
    """三角猫的选股问句。day 是出名单的交易日，prev / prev2 是它前面两个交易日。"""
    d, p, pp = _cn(day), _cn(prev), _cn(prev2)
    return (f"非ST股票，非科创板，非新股次新股，非北交所，{p}未涨停，{p}换手率小于5%，总市值低于500亿，流通市值大于10亿，"
            f"{p}成交量不大于{pp}成交量两倍，{d}涨幅,{d}09:23分未涨停，{d}09:25分未涨停且涨幅最高")


def ask(client: IFindClient, question: str, attempts: int = 3) -> dict:
    """问一句，返回第一张表（列名 → 一列值）。没有结果返回空表。"""
    last = ""
    for i in range(attempts):
        status, body = client._http(URL, {"access_token": client._access_token(force=i > 0)},
                                    {"searchstring": question, "searchtype": "stock"})
        if status == 200 and body.get("errorcode") in (0, None):
            tables = body.get("tables") or []
            return (tables[0].get("table") or {}) if tables else {}
        last = f"{status} {body.get('errorcode')} {body.get('errmsg')}"
        time.sleep(1.5 * (i + 1))
    raise IFindError(f"问财选股失败：{last}")


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _col(table: dict, pattern: str) -> list:
    for key, values in table.items():
        if re.fullmatch(pattern, key):
            return values
    return []


def parse_sjm(table: dict, day: dt.date, prev: dt.date) -> list[dict]:
    """把问财的表变成名单。顺序按 09:25 的涨幅从高到低。"""
    d, p = day.strftime("%Y%m%d"), prev.strftime("%Y%m%d")
    codes, names = table.get("股票代码") or [], table.get("股票简称") or []
    cols = {
        "auction_pct": _col(table, rf"分时涨跌幅:前复权\[{d} 09:25\]"),
        "limit_price": _col(table, rf"涨停价\[{d}\]"),
        "prev_close": _col(table, rf"收盘价:不复权\[{p}\]"),
        "prev_turnover": _col(table, rf"换手率\[{p}\]"),
        "total_mcap": _col(table, rf"总市值\[{p}\]"),
    }
    boards = table.get("上市板块") or []
    rows = []
    for i, raw in enumerate(codes):
        try:
            code = from_ths(raw)
        except ValueError:
            continue
        row = {"code": code, "name": names[i] if i < len(names) else code, "board": boards[i] if i < len(boards) else None}
        for k, values in cols.items():
            row[k] = _num(values[i]) if i < len(values) else None
        rows.append(row)
    rows.sort(key=lambda r: -(r["auction_pct"] if r["auction_pct"] is not None else -1e9))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
