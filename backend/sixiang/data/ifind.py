"""同花顺 iFinD HTTP 接口客户端（口径参考旧版四象 THSDataSource / ThsTokenManager）。

- 鉴权：长期有效的 refresh_token 换取 access_token（约 7 天有效），缓存在内存；收到 401 时刷新一次后重试。
- 限流：请求之间至少间隔 min_interval 秒；网络错误与 5xx 有界重试。
- 只读取数据，不写入任何外部系统。凭证只从环境变量读取，不写入日志。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import pandas as pd

TOKEN_URL = "https://ft.10jqka.com.cn/api/v1/get_access_token"
QUANT_URL = "https://quantapi.51ifind.com/api/v1/"
ALL_A_SHARES_BLOCK = "001005010"
STOCK_DAILY = "open,high,low,close,preClose,volume,amount,floatCapitalOfAShares,totalCapital"
INDEX_DAILY = "open,high,low,close,volume,amount"


class IFindError(RuntimeError):
    pass


class QuotaExceeded(IFindError):
    pass


def to_ths(code: str) -> str:
    """sh600519 → 600519.SH"""
    return f"{code[2:]}.{code[:2].upper()}"


def from_ths(code: str) -> str:
    """600519.SH → sh600519"""
    num, ex = code.split(".")
    return ex.lower() + num


@dataclass
class _Token:
    value: str
    fetched: float


class IFindClient:
    def __init__(self, refresh_token: str | None = None, access_token: str | None = None,
                 min_interval: float = 0.25, max_attempts: int = 4, timeout: float = 60):
        if not refresh_token and not access_token:
            raise IFindError("未配置 iFinD 凭证（SIXIANG_IFIND_REFRESH_TOKEN）")
        self._refresh = refresh_token
        self._token = _Token(access_token, time.time()) if access_token else None
        self._lock = threading.Lock()
        self._last = 0.0
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.calls = 0

    # ---------------------------------------------------------- 底层
    def _http(self, url: str, headers: dict, body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except ValueError:
                return e.code, {"errorcode": -1, "errmsg": f"HTTP {e.code}"}

    def _access_token(self, force: bool = False) -> str:
        with self._lock:
            # access_token 有效期约 7 天；保守地每 6 小时换一次
            if not force and self._token and time.time() - self._token.fetched < 6 * 3600:
                return self._token.value
            if not self._refresh:
                if self._token and not force:
                    return self._token.value
                raise IFindError("access_token 已失效，且未配置 refresh_token")
            status, body = self._http(TOKEN_URL, {"refresh_token": self._refresh}, {})
            token = (body.get("data") or {}).get("access_token")
            if status != 200 or body.get("errorcode") != 0 or not token:
                raise IFindError(f"换取 access_token 失败：{body.get('errmsg') or status}")
            self._token = _Token(token, time.time())
            return token

    def call(self, endpoint: str, body: dict) -> dict:
        refreshed = False
        for attempt in range(1, self.max_attempts + 1):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.calls += 1
            try:
                status, data = self._http(QUANT_URL + endpoint, {"access_token": self._access_token(), "ifindlang": "cn"}, body)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if attempt == self.max_attempts:
                    raise IFindError(f"{endpoint} 网络错误：{exc}") from exc
                time.sleep(2 ** attempt)
                continue
            code = data.get("errorcode")
            if status == 401 or code in (-1302, -1301):
                if refreshed:
                    raise IFindError("iFinD 鉴权失败（refresh_token 可能已过期）")
                self._access_token(force=True)
                refreshed = True
                continue
            if code == -4302:
                raise QuotaExceeded("iFinD 配额不足（-4302）")
            if status >= 500 and attempt < self.max_attempts:
                time.sleep(2 ** attempt)
                continue
            if code != 0:
                raise IFindError(f"{endpoint} 返回错误 {code}：{data.get('errmsg')}")
            return data
        raise IFindError(f"{endpoint} 多次重试失败")

    # ---------------------------------------------------------- 业务
    def universe(self, date: str) -> list[str]:
        """某日全部 A 股（含停牌），返回 sh600519 形式。"""
        data = self.call("data_pool", {
            "reportname": "p03291",
            "functionpara": {"date": date.replace("-", ""), "blockname": ALL_A_SHARES_BLOCK, "iv_type": "allcontract"},
            "outputpara": "p03291_f001,p03291_f002,p03291_f003,p03291_f004"})
        table = (data.get("tables") or [{}])[0].get("table", {})
        return sorted(from_ths(c) for c in table.get("p03291_f002", []) if c.endswith((".SH", ".SZ", ".BJ")))

    def history(self, codes: list[str], start: str, end: str, indicators: str, adjusted: bool = False) -> dict[str, pd.DataFrame]:
        """日线历史。codes 为 sh600519 形式；默认不复权（CPS=1）。无数据的代码不出现在结果中。"""
        body = {"codes": ",".join(to_ths(c) for c in codes), "indicators": indicators, "startdate": start, "enddate": end}
        if not adjusted:
            body["functionpara"] = {"CPS": "1"}
        data = self.call("cmd_history_quotation", body)
        out: dict[str, pd.DataFrame] = {}
        for t in data.get("tables") or []:
            dates = t.get("time") or []
            if not dates:
                continue
            frame = pd.DataFrame({k: v for k, v in (t.get("table") or {}).items()})
            frame.insert(0, "date", pd.to_datetime(dates).date)
            out[from_ths(t["thscode"])] = frame
        return out

    def names(self, codes: list[str], date: str) -> dict[str, tuple[str | None, str | None]]:
        """指定日期的证券简称（含 ST/退）与申万一级行业。"""
        data = self.call("basic_data_service", {"codes": ",".join(to_ths(c) for c in codes), "indipara": [
            {"indicator": "ths_stock_short_name_stock", "indiparams": [date]},
            {"indicator": "ths_the_sw_industry_stock", "indiparams": ["100", date]}]})
        out = {}
        for t in data.get("tables") or []:
            table = t.get("table") or {}
            name = (table.get("ths_stock_short_name_stock") or [None])[0]
            sector = (table.get("ths_the_sw_industry_stock") or [None])[0]
            out[from_ths(t["thscode"])] = (name or None, sector or None)
        return out
