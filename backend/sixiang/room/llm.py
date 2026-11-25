"""模型接入：一个很薄的接口，后面是 DeepSeek（与 OpenAI 兼容的 chat/completions）。

约定：chat() 永远不抛异常。出了任何问题都返回带 error 的 Reply，由上层按“失败即台词”处理。
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

import httpx

OnText = Callable[[str], Awaitable[None] | None]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""

    def args(self) -> dict:
        """模型给的参数；不是合法 JSON 就当没给。"""
        try:
            v = json.loads(self.arguments or "{}")
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}


@dataclass
class Reply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str = ""
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0
    error: str | None = None

    def as_message(self, with_reasoning: bool = True) -> dict:
        """放回对话里的 assistant 消息（工具调用那一轮要原样带回去）。"""
        m: dict[str, Any] = {"role": "assistant", "content": self.text or ""}
        if self.tool_calls:
            m["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments or "{}"}}
                               for c in self.tool_calls]
        if with_reasoning and self.reasoning:
            m["reasoning_content"] = self.reasoning
        return m


class ChatModel(Protocol):
    name: str

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, *, temperature: float | None = None,
                   max_tokens: int | None = None, on_text: OnText | None = None) -> Reply: ...


async def _emit(on_text: OnText | None, piece: str) -> None:
    if on_text and piece:
        r = on_text(piece)
        if inspect.isawaitable(r):
            await r


class DeepSeek:
    """流式调用。没出过字之前失败会重试一次；已经出了字就把出来的部分当作说完。"""

    def __init__(self, api_key: str, model: str = "deepseek-flash", base_url: str = "https://api.deepseek.com",
                 timeout: float = 60.0, effort: str | None = None):
        self.name = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout
        self.effort = effort
        self._send_reasoning = True     # 工具那一轮是否把思考内容带回去；接口不接受时自动关掉

    async def chat(self, messages, tools=None, *, temperature=None, max_tokens=None, on_text=None) -> Reply:
        t0 = time.monotonic()
        reply = Reply()
        for attempt in range(2):
            reply = await self._once(messages, tools, temperature, max_tokens, on_text)
            reply.seconds = round(time.monotonic() - t0, 2)
            if not reply.error or reply.text or reply.tool_calls:
                break
            if "reasoning_content" in (reply.error or "") and self._send_reasoning:
                self._send_reasoning = False
            await asyncio.sleep(0.6 * (attempt + 1))
        return reply

    async def _once(self, messages, tools, temperature, max_tokens, on_text) -> Reply:
        body: dict[str, Any] = {"model": self.name, "stream": True, "stream_options": {"include_usage": True},
                                "messages": messages if self._send_reasoning else
                                [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]}
        if tools:
            body["tools"] = tools
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens:
            body["max_tokens"] = max_tokens
        if self.effort:
            body["reasoning_effort"] = self.effort
        reply = Reply()
        calls: dict[int, ToolCall] = {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.url, headers=self.headers, json=body) as r:
                    if r.status_code != 200:
                        detail = (await r.aread()).decode("utf-8", "replace")[:300]
                        reply.error = f"HTTP {r.status_code}: {detail}"
                        return reply
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            ev = json.loads(data)
                        except ValueError:
                            continue
                        if ev.get("usage"):
                            reply.usage = ev["usage"]
                        for choice in ev.get("choices") or []:
                            delta = choice.get("delta") or {}
                            if delta.get("reasoning_content"):
                                reply.reasoning += delta["reasoning_content"]
                            if delta.get("content"):
                                reply.text += delta["content"]
                                await _emit(on_text, delta["content"])
                            for tc in delta.get("tool_calls") or []:
                                slot = calls.setdefault(tc.get("index", 0), ToolCall(id="", name=""))
                                slot.id = tc.get("id") or slot.id
                                fn = tc.get("function") or {}
                                slot.name += fn.get("name") or ""
                                slot.arguments += fn.get("arguments") or ""
        except Exception as exc:  # 超时、断线、任何意外：都只是“这次没说成”
            reply.error = f"{type(exc).__name__}: {exc}"
        reply.tool_calls = [c for _, c in sorted(calls.items()) if c.name]
        return reply


class FakeModel:
    """测试用：按剧本说话，不联网。剧本的每一项是一句话、一个 Reply、一个异常，或者一个函数(messages) → 前三者之一。"""

    name = "fake"

    def __init__(self, script: list | None = None, default: str = "嗯。"):
        self.script = list(script or [])
        self.default = default
        self.calls: list[dict] = []

    async def chat(self, messages, tools=None, *, temperature=None, max_tokens=None, on_text=None) -> Reply:
        self.calls.append({"messages": messages, "tools": tools})
        item = self.script.pop(0) if self.script else self.default
        if callable(item):
            item = item(messages)
        if isinstance(item, Exception):
            return Reply(error=f"{type(item).__name__}: {item}")
        if isinstance(item, Reply):
            await _emit(on_text, item.text)
            return item
        await _emit(on_text, str(item))
        return Reply(text=str(item))


def from_env() -> DeepSeek | None:
    """没配密钥就返回 None：群聊入口不显示，其他功能不受影响。"""
    key = os.environ.get("SIXIANG_LLM_API_KEY", "").strip()
    if not key:
        return None
    return DeepSeek(key, model=os.environ.get("SIXIANG_LLM_MODEL", "deepseek-flash"),
                    base_url=os.environ.get("SIXIANG_LLM_BASE_URL", "https://api.deepseek.com"),
                    # 群聊要快：模型说话前的“思考”调到最低档。思考的字数也算在输出上限里。
                    effort=os.environ.get("SIXIANG_LLM_EFFORT", "low") or None)
