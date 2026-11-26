"""MCP 数据服务的客户端：日线里没有的数据，从旧四象留下的几个 MCP 服务取。

一共五个服务，各配各的地址，哪个没配哪类数据就没有：
  SIXIANG_MCP_MARKET_URL  实时行情、资金流、概念、历史估值（Java，背后是 iFinD）      线上 http://127.0.0.1:9070/mcp
  SIXIANG_MCP_NEWS_URL    个股新闻、市场快讯                                          线上 http://127.0.0.1:8066/mcp
  SIXIANG_MCP_FUND_URL    盈利预测                                                    线上 http://127.0.0.1:8077/mcp
  SIXIANG_MCP_LOCKUP_URL  限售解禁                                                    线上 http://127.0.0.1:8078/mcp
  SIXIANG_MCP_HOT_URL     龙虎榜、人气股                                              线上 http://127.0.0.1:8079/mcp

只做一件事：调一个只读工具，拿回它的 data。协议是 MCP 的 Streamable HTTP（一次握手，之后每次 tools/call）。
没配地址（SIXIANG_MCP_MARKET_URL）就是“没有这项数据”：用到它的工具回一句取不到，别的功能照常。
调用方只会拿到两种结果：data（字典），或者 McpError。绝不把半截数据当成功。
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

OPEN = "2025-03-26"


class McpError(RuntimeError):
    pass


class McpClient:
    def __init__(self, url: str, timeout: float = 12.0):
        self.url, self.timeout = url, timeout
        self._session: str | None = None
        self._ready = False
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict]] = {}

    def _post(self, body: dict) -> dict | None:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        req = urllib.request.Request(self.url, json.dumps(body).encode("utf-8"), headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:      # noqa: S310  地址来自我们自己的配置
            self._session = r.headers.get("Mcp-Session-Id") or self._session
            raw = r.read().decode("utf-8", "replace")
        if not raw.strip():
            return None
        if raw.lstrip().startswith("{"):
            return json.loads(raw)
        events = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]      # 服务端也可能用事件流回
        return json.loads(events[-1]) if events else None

    def _handshake(self) -> None:
        self._session = None
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": OPEN, "capabilities": {}, "clientInfo": {"name": "sixiang", "version": "1"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self._ready = True

    def call(self, tool: str, args: dict, ttl: float = 0) -> dict:
        """调一个工具，返回它的 data。ttl > 0 时同样的调用在这么多秒内只取一次（实时行情也不必每秒都打上游）。"""
        key = tool + json.dumps(args, sort_keys=True, ensure_ascii=False)
        hit = self._cache.get(key)
        if hit and ttl and time.monotonic() - hit[0] < ttl:
            return hit[1]
        with self._lock:
            reply = None
            for attempt in range(2):          # 服务重启过的话会话就没了：重新握手再试一次
                try:
                    if not self._ready:
                        self._handshake()
                    reply = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}})
                    break
                except Exception as exc:  # noqa: BLE001
                    self._ready = False
                    if attempt:
                        raise McpError(f"{tool}: {type(exc).__name__}") from exc
        result = (reply or {}).get("result")
        if not result:
            raise McpError(f"{tool}: {json.dumps((reply or {}).get('error'), ensure_ascii=False)[:200]}")
        text = next((c.get("text") for c in result.get("content") or [] if c.get("type") == "text"), None)
        try:
            payload = json.loads(text) if text else {}
        except ValueError as exc:
            raise McpError(f"{tool}: 返回的不是 JSON") from exc
        if result.get("isError") or not isinstance(payload, dict) or payload.get("errorCode"):
            raise McpError(f"{tool}: {payload.get('errorCode') if isinstance(payload, dict) else ''} {str(text)[:160]}")
        # Java 那个服务把结果包在 data 里（外面是出处、质量等信息）；Python 的几个直接就是结果
        data = payload["data"] if "toolName" in payload and "data" in payload else payload
        if ttl:
            self._cache[key] = (time.monotonic(), data)
            if len(self._cache) > 500:
                self._cache = dict(list(self._cache.items())[-200:])
        return data


_client: McpClient | None = None
_loaded = False
_others: dict[str, McpClient | None] = {}


def market() -> McpClient | None:
    """行情类 MCP。没配就是 None。"""
    global _client, _loaded
    if not _loaded:
        url = os.environ.get("SIXIANG_MCP_MARKET_URL", "").strip()
        _client, _loaded = (McpClient(url) if url else None), True
    return _client


def server(name: str) -> McpClient | None:
    """news / fund / lockup / hot 这几个服务。没配就是 None。"""
    if name not in _others:
        url = os.environ.get(f"SIXIANG_MCP_{name.upper()}_URL", "").strip()
        _others[name] = McpClient(url, timeout=20) if url else None
    return _others[name]


def symbol(code: str) -> str:
    """sz002145 → 002145.SZ"""
    return f"{code[2:]}.{code[:2].upper()}"


def code(sym: str) -> str:
    """002145.SZ → sz002145"""
    num, _, ex = sym.partition(".")
    return f"{ex.lower()}{num}"


def quotes(codes: list[str], ttl: float = 8) -> dict[str, dict]:
    """一批股票的实时报价：{code: {latest, change(小数), amount, high, low, open, time}}。取不到的股票不在结果里。"""
    client = market()
    if client is None or not codes:
        return {}
    out: dict[str, dict] = {}
    for i in range(0, len(codes), 20):          # 服务端一次最多 20 只
        data = client.call("get_realtime_quotes", {"symbols": [symbol(c) for c in codes[i:i + 20]],
                                                   "fields": ["latest", "changeRatio", "amount", "high", "low", "open"]}, ttl=ttl)
        for s in data.get("snapshots") or []:
            if s.get("latest") is None:
                continue
            out[code(s["symbol"])] = {"latest": s["latest"], "change": (s["changeRatio"] / 100) if s.get("changeRatio") is not None else None,
                                      "amount": s.get("amount"), "high": s.get("high"), "low": s.get("low"), "open": s.get("open"),
                                      "time": s.get("quoteTime")}
    return out
