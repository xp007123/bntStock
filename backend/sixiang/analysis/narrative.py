"""把引擎结果翻译成大白话（规则生成，不调用大模型；所有数字都来自引擎）。"""
from __future__ import annotations

SAME = 0.03          # 相似时候与平时的上涨概率差小于 3 个百分点：说“差不多”
PRICE_BAND = 0.01    # 期权平均净结果在 ±1% 以内：说“大致合理”


def horizon_text(h: int) -> str:
    return {5: "1 周", 10: "2 周", 21: "1 个月", 42: "2 个月", 63: "3 个月", 126: "6 个月", 250: "1 年"}.get(h, f"{h} 个交易日")


def pct(v: float, digits: int = 1, sign: bool = True) -> str:
    s = f"{abs(v) * 100:.{digits}f}%"
    return (("+" if v > 0 else "−" if v < 0 else "") if sign else "") + s


def tens(p: float) -> int:
    return max(0, min(10, round(p * 10)))


def state_text(st: dict, subject: str = "股价") -> str:
    r20, pos, vp = st["r20"], st["pos60"], st["vol_percentile"]
    move = f"最近 20 个交易日{'涨' if r20 >= 0 else '跌'}了 {pct(r20, sign=False)}"
    where = f"{subject}在 60 日均线{'上方' if pos >= 0 else '下方'} {pct(pos, sign=False)}"
    calm = "波动比历史上多数时候都小" if vp < .3 else "波动比历史上多数时候都大" if vp > .7 else "波动处在历史中间水平"
    return f"{move}，{where}，{calm}"


def stock_answer(a: dict, valuation: dict | None, subject: str = "股价") -> dict:
    h, sim, all_ = a["horizon"], a["similar"], a["all"]
    p, base = sim["up_prob"], all_["up_prob"]
    diff = p - base
    tilt = ("现在这种走势对结果影响不大" if abs(diff) < SAME else
            "和现在相似的时候，之后更常涨" if diff > 0 else "和现在相似的时候，之后更常跌")
    voice = [f"{a['name']}{state_text(a['state'], subject)}。", f"按历史看，{tilt}。"]
    if a["state"]["vol_percentile"] > .7:
        voice.append("眼下波动偏大，最好和最坏的情况都会比平时更极端。")
    elif a["state"]["vol_percentile"] < .3:
        voice.append("眼下波动偏小，结果通常不会太极端。")
    if valuation:
        if valuation.get("ttm_loss"):
            voice.append("最近四个季度合计是亏损的，估值没法用市盈率衡量。")
        elif valuation.get("pe_ttm"):
            voice.append(f"按最新已披露的财报，市盈率 TTM 约 {valuation['pe_ttm']:.1f} 倍。")
    if sim["n"] < 300:
        voice.append(f"相似的历史时候只有 {sim['n']} 个，结论要打个折扣看。")
    return {
        "question": f"{a['name']}接下来{horizon_text(h)}，涨的可能大吗？",
        "verdict": {"label": f"{horizon_text(h)}后在涨的比例", "value": round(p * 100), "dots": p * 100,
                    "plain": f"和现在走势相似的历史时候里，大约每 10 次有 {tens(p)} 次在 {horizon_text(h)}后是涨的。",
                    "note": f"不挑时候、随便哪天买，这个比例是 {round(base * 100)}%。"},
        "facts": [
            {"label": "平均下来", "value": sim["mean"], "note": f"{horizon_text(h)}后的平均涨跌"},
            {"label": "运气最差的十分之一", "value": sim["p10"], "note": "跌得比这还多的情况占一成"},
            {"label": "运气最好的十分之一", "value": sim["p90"], "note": "涨得比这还多的情况占一成"},
        ],
        "voice": "".join(voice),
        "tone": "same" if abs(diff) < SAME else "good" if diff > 0 else "bad",
    }


def option_answer(a: dict, valuation: dict | None) -> dict:
    """问期权：用户最想知道的是“能涨多少”。先讲上涨预期，期权费只是标在上面的一条线。"""
    h, fee, sim, all_ = a["horizon"], a["fee"], a["similar"], a["all"]
    p, base, mean = sim["breakeven_prob"], all_["breakeven_prob"], sim["payoff_mean"]
    price = "偏贵" if mean < -PRICE_BAND else "偏便宜" if mean > PRICE_BAND else "大致合理"
    up, up_all = a["upside"]["similar"], a["upside"]["all"]
    lock, ht = a["upside"]["lock"], horizon_text(h)
    end, peak = up["end"], up["peak"]
    lead = peak or end                       # 能提前平仓就讲“中途最高”，否则讲到期
    where = f"持有满 {lock} 天之后、到期之前，中途最高" if peak else "到期时"
    voice = [f"按历史看，和现在相似的时候买这个 {ht}的看涨：一半情况下{where}涨到过 {pct(lead['median'])} 以上，最好的两成到过 {pct(lead['p80'])} 以上。"]
    if peak:
        voice.append((f"一直拿到到期的话，一半情况涨幅在 {pct(end['median'])} 以上" if end["median"] > 0 else "一直拿到到期的话，有一半情况到期那天是没涨的")
                     + f"，最好的两成在 {pct(end['p80'])} 以上。")
    voice.append(f"期权费 {fee * 100:.1f}% 是一条线：" + (f"中途涨过这条线的占 {round(peak['over_fee'] * 100)}%，" if peak else "")
                 + f"到期时还在线上的占 {round(end['over_fee'] * 100)}%。")
    voice.append(f"{a['name']}{state_text(a['state'])}。")
    gap = lead["median"] - (up_all["peak"] or up_all["end"])["median"]
    if abs(gap) >= 0.01:
        voice.append(f"比起不挑时候，现在这种走势之后的上涨空间{'更大' if gap > 0 else '更小'}一些。")
    voice.append("最坏的情况就是期权费全部损失。")
    if valuation and valuation.get("pe_ttm") and not valuation.get("ttm_loss"):
        voice.append(f"最新市盈率 TTM 约 {valuation['pe_ttm']:.1f} 倍。")
    facts = [{"label": "到期时，一半情况涨幅超过", "value": end["median"], "note": f"一直拿满 {ht}"},
             {"label": "到期时，最好的两成超过", "value": end["p80"], "note": f"一直拿满 {ht}"}]
    if peak:
        facts.append({"label": "中途最高，最好的两成到过", "value": peak["p80"], "note": f"持有满 {lock} 天后可以平仓"})
    else:
        facts.append({"label": "到期时，最好的一成超过", "value": end["p90"], "note": f"一直拿满 {ht}"})
    return {
        "question": f"{a['name']} {ht}平值看涨，期权费 {fee * 100:.1f}%，能涨多少？",
        # verdict 是“到期回本”的口径：封存和揭晓按它结算，不能改。页面主结论用下面的 upside_verdict。
        "verdict": {"label": "到期回本的概率", "value": round(p * 100), "dots": p * 100,
                    "plain": f"和现在相似的历史时候里，大约每 10 次有 {tens(p)} 次到期时能回本。",
                    "note": f"回本：{ht}后涨幅超过期权费 {fee * 100:.1f}%。不挑时候、随便哪天买，回本概率是 {round(base * 100)}%。"},
        "upside_verdict": {
            "label": f"{'中途最高涨到过' if peak else '到期涨幅'}（一半情况在这之上）", "value": round(lead["median"] * 100, 1),
            "dots": (peak or end)["over_fee"] * 100,
            "dots_caption": f"{'中途涨过' if peak else '到期涨过'}期权费 {fee * 100:.1f}%",
            "plain": f"和现在走势相似的历史时候里，有一半{where}涨到过 {pct(lead['median'])} 以上；最好的两成到过 {pct(lead['p80'])} 以上。",
            "note": f"期权费 {fee * 100:.1f}%。" + (f"持有满 {lock} 个交易日后才能平仓，所以“中途”从第 {lock} 天算起，按收盘价。" if peak else "")
                    + f"到期时涨幅还在期权费之上的占 {round(end['over_fee'] * 100)}%（封存的判断按这个揭晓）。"},
        "facts": facts,
        "voice": "".join(voice),
        "tone": "bad" if price == "偏贵" else "good" if price == "偏便宜" else "same",
        "price": price,
    }


def compare_answer(a: dict, b: dict) -> dict:
    """两只股票同一个问题并排：只比引擎给出的数，不替用户选。"""
    h = a["horizon"]
    pa, pb = a["similar"]["up_prob"], b["similar"]["up_prob"]
    gap = pa - pb
    lead, lag = (a, b) if gap >= 0 else (b, a)
    if abs(gap) < SAME:
        head = f"两只差不多：和现在相似的时候里，{horizon_text(h)}后在涨的比例都在 {round(min(pa, pb) * 100)}%–{round(max(pa, pb) * 100)}% 之间。"
    else:
        head = f"按历史看，{lead['name']}在涨的比例高 {abs(gap) * 100:.0f} 个百分点（{round(max(pa, pb) * 100)}% 对 {round(min(pa, pb) * 100)}%）。"
    spread = lambda x: x["similar"]["p90"] - x["similar"]["p10"]
    wild = a if spread(a) > spread(b) else b
    calm = b if wild is a else a
    lines = [head]
    if abs(spread(a) - spread(b)) < 0.03:
        lines.append(f"两只结果的分散程度差不多：最差一成和最好一成都相差约 {(spread(a) + spread(b)) / 2 * 100:.0f} 个百分点。")
    else:
        lines.append(f"{wild['name']}的结果更分散：最差一成和最好一成相差 {spread(wild) * 100:.0f} 个百分点，{calm['name']}是 {spread(calm) * 100:.0f} 个。")
    for x in (a, b):
        d = x["similar"]["up_prob"] - x["all"]["up_prob"]
        if abs(d) >= SAME:
            lines.append(f"{x['name']}现在的走势比它平时{'更容易' if d > 0 else '更难'}涨（平时 {round(x['all']['up_prob'] * 100)}%）。")
    lines.append("概率高不等于一定涨，两只都只是历史统计。")
    return {"question": f"{a['name']}和{b['name']}，接下来{horizon_text(h)}哪个涨的可能大？", "voice": "".join(lines),
            "lead": None if abs(gap) < SAME else lead["code"]}
