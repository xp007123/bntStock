---
repo: https://github.com/nuwa-skills/buffett-skill
path: 
version: 0e901eddc5b3
license: MIT
fetched: 2026-11-26
style: persona
---
# 来源

取自 https://github.com/nuwa-skills/buffett-skill，版本 `0e901eddc5b3`，MIT 许可（见同目录 LICENSE）。文件原样保存，没有改动内容。

取了哪些文件：SKILL.md、references/research.md、examples/demo-conversation.md。

人物型：SKILL.md 正文直接当他的完整人设。

## 我们覆盖了什么

只在“一对一深聊”里用，见 `sixiang/room/skills.py`。以下几处以我们的规则（`prompts.DEEP_RULES`）为准：

- 上游让它给出可操作的建议或买卖结论 → 不替用户做买卖决定；可以说他自己在什么条件下才会感兴趣。
- 上游也聊别的话题（人生、职业、宏观） → 只聊眼前这只股票，除非用户主动问。
- 上游有自己的追问流程 → 可以反问，一次最多两个问题。
- 上游让它先说一句免责声明 → 不说，页面上已经写了。
- 数字和案例上游可以自由引用 → 关于这只股票的数字只能来自我们的数据工具。

更新上游：把新文件原样覆盖进来，改上面的 version 和 fetched，在管理端“试聊”一遍再上线。
