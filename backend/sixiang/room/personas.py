"""角色表：一个角色就是 personas/ 下的一个 Markdown 文件。

文件头部（两行 --- 之间）是给程序读的；正文按 “## 小节” 分段，是给模型读的人设。
角色页用的介绍也从同一个文件里取，不另存一份。
以 “## 主页：” 开头的小节只给个人主页用（他干过的事、什么问题找他、一段对话），不进提示词。
加一个角色 = 加一个文件。以后用户自建角色，只要再提供一个能返回 Persona 的来源即可。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import skills
from pathlib import Path

DIR = Path(__file__).parent / "personas"
DISCLAIMER = "角色由 AI 按公开资料演绎，不代表本人。"
HOME = "主页："          # 这个前缀的小节只给个人主页看，模型看不到


@dataclass
class Persona:
    id: str
    name: str
    title: str = ""
    lens: str = ""                 # 看什么：公司 / 产业链 / 情绪 / 宏观和预期
    tagline: str = ""
    bio: str = ""                  # 概要简介：这个人是谁、凭什么值得听（给不认识他的用户看）
    hold: str = ""                 # 个人主页上的三行短介绍：一般拿多久 / 开口先问 / 打死不碰
    ask: str = ""
    never: str = ""
    role: str = "guest"            # guest 嘉宾 / host 主持人
    color: str = "#190300"
    tools: list[str] = field(default_factory=list)     # 爱用的数据，不是限制
    rivals: list[str] = field(default_factory=list)    # 天然的对手，导演拱火时参考
    temperature: float = 0.9
    version: int = 1
    body: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    home: dict[str, str] = field(default_factory=dict)  # “## 主页：xxx” 这几节的原文，键是 xxx

    def home_public(self) -> dict | None:
        """个人主页的内容：他干过的事、哪些问题找他/别找他、一段对话。一条一行，字段用 | 隔开。没写就是 None。"""
        def rows(key: str) -> list[list[str]]:
            return [[c.strip() for c in x.strip()[1:].split("|")] for x in self.home.get(key, "").splitlines() if x.strip().startswith("-")]
        deeds = [dict(zip(("when", "title", "story", "lesson"), r + [""] * 4)) for r in rows("他干过的事") if len(r) >= 2]
        yes = [{"q": r[0], "a": r[1] if len(r) > 1 else ""} for r in rows("这些问题找他") if r[0]]
        no = [{"q": r[0], "a": r[1] if len(r) > 1 else "", "to": r[2] if len(r) > 2 else ""} for r in rows("这些问题别找他") if r[0]]
        where, turns, notes = "", [], []
        for x in self.home.get("聊一段", "").splitlines():
            x = x.strip()
            if not x.startswith("-") or "：" not in x:
                continue
            who, text = (s.strip() for s in x[1:].split("：", 1))
            if who == "场合":
                where = text
            elif who == "看点":
                a, _, b = text.partition("|")
                notes.append({"title": a.strip(), "text": b.strip()})
            elif text:
                turns.append({"who": "user" if who == "用户" else "me" if who == "他" else who.lstrip("@"), "text": text})
        if not (deeds or yes or no or turns):
            return None
        return {"deeds": deeds[:3], "yes": yes[:5], "no": no[:5], "talk": {"where": where, "turns": turns[:8], "notes": notes[:3]}}

    def public(self) -> dict:
        """给角色页和头像用的介绍。"""
        lines = lambda key: [x.lstrip("-0123456789. ").strip() for x in self.sections.get(key, "").splitlines() if x.strip()]  # noqa: E731
        return {"id": self.id, "name": self.name, "title": self.title, "lens": self.lens, "tagline": self.tagline, "role": self.role,
                "color": self.color, "deep": skills.has(self.id), "bio": self.bio, "hold": self.hold, "ask": self.ask, "never": self.never, "rivals": self.rivals,
                "beliefs": lines("信条")[:5], "asks": lines("看一只股票的顺序")[:6], "avoids": lines("不碰什么")[:4],
                "lines": lines("示例发言")[:4], "home": self.home_public(), "version": self.version, "disclaimer": DISCLAIMER}


def _value(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return [x.strip() for x in raw[1:-1].split(",") if x.strip()]
    return raw


def parse(text: str) -> Persona:
    head, body = {}, text
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        for line in front.strip().splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, v = line.split(":", 1)
                head[k.strip()] = _value(v)
    sections, home, keep, current, bucket = {}, {}, [], None, None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            bucket = home if current.startswith(HOME) else sections
            if bucket is home:
                current = current[len(HOME):].strip()
            bucket[current] = ""
        elif current:
            bucket[current] += line + "\n"
        if bucket is not home:                # 主页那几节不进 body：body 是要交给模型的
            keep.append(line)
    p = Persona(id=head["id"], name=head["name"], body="\n".join(keep).strip(), sections={k: v.strip() for k, v in sections.items()},
                home={k: v.strip() for k, v in home.items()})
    for k in ("title", "lens", "tagline", "bio", "hold", "ask", "never", "role", "color"):
        if k in head:
            setattr(p, k, head[k])
    for k in ("tools", "rivals"):
        if isinstance(head.get(k), list):
            setattr(p, k, head[k])
    p.temperature = float(head.get("temperature", p.temperature))
    p.version = int(head.get("version", p.version))
    return p


_cache: dict[str, Persona] | None = None


def all_personas(reload: bool = False) -> dict[str, Persona]:
    global _cache
    if _cache is None or reload:
        _cache = {}
        for path in sorted(DIR.glob("*.md")):
            try:
                p = parse(path.read_text(encoding="utf-8"))
                _cache[p.id] = p
            except Exception:      # 一张卡写坏了，不影响其他人
                continue
    return _cache


def get(pid: str) -> Persona | None:
    return all_personas().get(pid)


def host() -> Persona:
    return next(p for p in all_personas().values() if p.role == "host")


def guests() -> list[Persona]:
    return [p for p in all_personas().values() if p.role == "guest"]


DEFAULT_GUESTS = ["buffett", "yangjia", "soros", "serenity"]    # 默认拉进群的四位，也是开场的座次：对手挨着坐
