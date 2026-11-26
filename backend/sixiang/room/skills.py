"""深聊包：一位角色“完整版”的思维方式，一对一深聊时用。群聊不用它（群聊用精简的角色卡）。

一个深聊包就是 skills/<角色 id>/ 下的一组文件，原样取自社区的 Agent Skill：
  SOURCE.md          我们自己写的：出处、版本、许可、是哪一种（头部 --- 之间给程序读），不进提示词
  SKILL.md           正文。头部的 --- 元数据是给别的工具看的，这里丢掉
  invest.md          有这个文件 = “方法型”的包（见下）
  references/*.md    参考资料。不每次都带上，模型需要时用 read_reference 去读
  examples/*.md      示范对话，同上

两种包，装配方式不同：
- 人物型（persona）：SKILL.md 写的就是“这个人怎么想、怎么说话”。正文直接当他的完整人设。
- 方法型（framework）：invest.md 是一套结构化的方法（信号、过滤条件、仓位、风控、经典案例），没有口吻。
  装配时“他是谁、怎么说话”用我们自己的角色卡，“他的方法”用 invest.md；链接清单和“给出买卖结论”的输出模板去掉。

“装配”不是原样运行：回答的规矩以 prompts.DEEP_RULES 为准——数字只来自工具、不替用户做买卖决定、反问有上限。
上游文件不改，方便以后跟着上游更新。哪位角色的深聊暂时不想开放，在管理端关掉（见 set_disabled）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent / "skills"
_DROP = ("Podcasts", "YouTube", "Reading List", "Playbooks")       # 方法型里用不上的小节：链接清单、买卖结论的输出模板


@dataclass
class Skill:
    persona_id: str
    body: str
    style: str = "persona"                                        # persona 人物型 / framework 方法型
    references: dict[str, str] = field(default_factory=dict)     # 文件名（不带扩展名）→ 内容
    source: dict[str, str] = field(default_factory=dict)         # repo / path / version / license / fetched

    def info(self) -> dict:
        """给管理端看的概况。"""
        return {"style": self.style, "chars": len(self.body), "source": self.source,
                "sections": re.findall(r"^## (.+)$", self.body, flags=re.M),
                "references": [{"name": k, "chars": len(v)} for k, v in self.references.items()]}


_cache: dict[str, Skill | None] = {}
_disabled: set[str] = set()


def _front(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    _, head, body = text.split("---", 2)
    meta = {}
    for line in head.strip().splitlines():
        if ":" in line and not line.startswith((" ", "-", "#")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, body


def _persona_body(text: str) -> str:
    """人物型：去掉头部元数据和“按需资源”那一节（那是告诉别的工具去哪读文件的，我们用 read_reference 代替）。"""
    _, body = _front(text)
    return re.sub(r"^## 按需资源\n.*?(?=^## |\Z)", "", body, flags=re.S | re.M).strip()


def _framework_body(text: str) -> str:
    """方法型：去掉头部的结构化元数据（正文里都有），以及链接清单和输出模板。"""
    _, body = _front(text)
    for name in _DROP:
        body = re.sub(rf"^## {re.escape(name)}\n.*?(?=^## |\Z)", "", body, flags=re.S | re.M)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def load(persona_id: str, reload: bool = False) -> Skill | None:
    """这位角色的深聊包（不管开没开）。没装就是 None。"""
    if reload or persona_id not in _cache:
        folder = ROOT / (persona_id or "_")
        skill = None
        if re.fullmatch(r"[a-z][a-z0-9_]{1,38}", persona_id or "") and (folder / "SKILL.md").is_file():
            refs = {p.stem: p.read_text(encoding="utf-8").strip()
                    for sub in ("references", "examples") for p in sorted((folder / sub).glob("*.md"))}
            source = _front((folder / "SOURCE.md").read_text(encoding="utf-8"))[0] if (folder / "SOURCE.md").is_file() else {}
            method = folder / "invest.md"
            if method.is_file():
                skill = Skill(persona_id, _framework_body(method.read_text(encoding="utf-8")), "framework", refs, source)
            else:
                skill = Skill(persona_id, _persona_body((folder / "SKILL.md").read_text(encoding="utf-8")), "persona", refs, source)
        _cache[persona_id] = skill
    return _cache[persona_id]


def installed() -> list[str]:
    return sorted(p.name for p in ROOT.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()) if ROOT.is_dir() else []


def set_disabled(ids) -> None:
    """管理端关掉了哪几位的深聊。由角色登记处从数据库读出来后告诉这里。"""
    global _disabled
    _disabled = set(ids)


def has(persona_id: str) -> bool:
    """现在能不能和他深聊：装了，而且没被关掉。"""
    return persona_id not in _disabled and load(persona_id) is not None


def reference_tool(skill: Skill) -> dict | None:
    """给模型的“翻资料”工具。只在深聊里提供，且只在这位角色的深聊包带了资料时提供。"""
    if not skill.references:
        return None
    return {"type": "function", "function": {
        "name": "read_reference", "description": "翻你自己的背景资料（生平、言论出处、案例、示范对话）。只在需要核对一件往事或一句原话时用，平时不用。",
        "parameters": {"type": "object", "required": ["name"],
                       "properties": {"name": {"type": "string", "enum": sorted(skill.references), "description": "资料名"}}}}}


def read_reference(skill: Skill, name: str, limit: int = 6000) -> str:
    text = skill.references.get(str(name or ""))
    return text[:limit] if text else "没有这份资料。"
