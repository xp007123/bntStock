"""条件库：可复用的单条条件模块（从 PatternLab condition_library 迁移，去掉模板向导依赖）。

模块只是规则 DSL 的一条条件，不含可执行代码。前端会自动提取其中的数字作为可调参数。
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from .rules import TEMPLATES, cond, field, fn

CATEGORIES = ["趋势与均线", "突破与涨跌", "量能与规模", "K线结构", "技术指标"]


def canonical(value):
    """忽略 label、统一数字类型后的规范形式，用于判断两条条件是否相同。"""
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k != "label"}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def _shape(value):
    """结构签名：数字与比较方向都视为可调参数，只比较计算结构。"""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items() if k not in ("label", "op")}
    if isinstance(value, list):
        return [_shape(v) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return 0
    return value


LIBRARY: list[dict] = []


def _add(key: str, name: str, category: str, condition: dict, note: str = "", aliases: list[str] | None = None) -> None:
    LIBRARY.append({"key": key, "name": name, "category": category, "condition": deepcopy(condition),
                    "note": note, "aliases": aliases or []})


# 1. 内置模板中的条件（相同计算只保留一条，模板措辞作为别名）
_NEUTRAL = {"突破前期高点": "收盘价与此前高点", "成交量达到放量要求": "成交量与此前均量倍数", "收阳线": "收盘价与开盘价",
            "短期均线上穿长期均线": "两条简单均线比较", "成交量高于均量": "成交量与此前均量", "此前已经下跌": "前期 N 日涨跌幅（截至昨日）",
            "下影线足够长": "下影线占开盘价", "实体较小": "实体占开盘价", "收盘靠近当日高位": "收盘在当日振幅的位置",
            "整理区间足够窄": "区间高低价幅度", "成交量满足缩量要求": "成交量与此前均量倍数", "保持中期趋势": "收盘价与均线",
            "均线仍向上": "当前均线与前期均线", "昨日收盘在均线上方": "前期收盘价与同期均线", "当日最低价低于昨日": "当日最低价与前期最低价",
            "最低价相对均线下界": "最低价相对均线位置", "最低价相对均线上界": "最低价相对均线位置", "收盘不低于均线": "收盘价与均线",
            "当日成交量低于此前均量的指定比例": "成交量与此前均量倍数", "截至昨日跌幅达到阈值": "前期 N 日涨跌幅（截至昨日）",
            "收盘重新上穿短期均线": "收盘价与均线", "当日收阳": "收盘价与开盘价"}
_NOTES = {
    "收盘价与此前高点": "收盘价与前期最高价比较；高点窗口默认截至昨日，不包含当天。",
    "成交量与此前均量倍数": "成交量与此前均量乘指定倍数比较；小于可定义缩量，大于可定义放量。",
    "收盘价与开盘价": "收盘高于开盘为阳线，低于开盘为阴线。",
    "两条简单均线比较": "上穿/下穿按相邻两日收盘后的指标值判断，只在交叉当天触发。",
    "前期 N 日涨跌幅（截至昨日）": "先计算 N 日涨跌幅，再向前偏移；负数表示下跌。",
    "下影线占开盘价": "下影 = 较低的开盘/收盘 − 最低价；再除以开盘价。",
    "实体占开盘价": "实体 = 收盘与开盘之差的绝对值；再除以开盘价。",
    "收盘在当日振幅的位置": "位置 =（收盘 − 最低）/（最高 − 最低）；1 为收在最高价。",
    "区间高低价幅度": "窗口内最高价 / 最低价；包含当天。数值越小，区间越窄。",
    "最低价相对均线位置": "日线最低价 / 收盘后计算的当日均线；只比较数值，不代表盘中触及均线。",
    "当日最低价与前期最低价": "只能判断最低价是否降低，不能还原当天价格运行过程。",
}
_CATEGORY = {"收盘价与此前高点": "突破与涨跌", "成交量与此前均量倍数": "量能与规模", "成交量与此前均量": "量能与规模",
             "收盘价与开盘价": "K线结构", "下影线占开盘价": "K线结构", "实体占开盘价": "K线结构", "收盘在当日振幅的位置": "K线结构",
             "区间高低价幅度": "突破与涨跌", "前期 N 日涨跌幅（截至昨日）": "突破与涨跌", "当日最低价与前期最低价": "突破与涨跌"}
_seen: dict[str, dict] = {}
for _i, _t in enumerate(TEMPLATES):
    for _j, _c in enumerate(_t["conditions"]):
        _fp = json.dumps(_shape(_c), sort_keys=True)
        if _fp in _seen:
            _seen[_fp]["aliases"] += [_c["label"], _t["name"]]
            continue
        _name = _NEUTRAL.get(_c["label"], _c["label"])
        _add(f"template_{_i}_{_j}", _name, _CATEGORY.get(_name, "趋势与均线"), _c, _NOTES.get(_name, ""), [_c["label"], _t["name"]])
        _seen[_fp] = LIBRARY[-1]

# 2. 常用指标与数值条件
_close = field("close")
for _key, _name, _cat, _expr, _value, _note in [
    ("rsi", "RSI 强弱", "技术指标", fn("rsi", _close, 14), 50, "RSI 取值 0–100；可改为小于判断超卖。"),
    ("atr_pct", "ATR / 收盘价", "技术指标", fn("ratio", fn("atr", n=14), y=_close), .03, "日均真实波幅占收盘价的比例。"),
    ("change", "截至今日 N 日涨跌幅", "突破与涨跌", fn("change", _close, 20), .1, "0.1 表示上涨 10%；负数表示下跌。"),
    ("volume_ratio", "成交量 / 此前均量", "量能与规模", fn("ratio", field("volume"), y=fn("lag", fn("sma", field("volume"), 20), 1)), 1.5, "均量不含当天，可用小于定义缩量。"),
    ("amount", "成交额（元）", "量能与规模", field("amount"), 1e8, "1e8 即 1 亿元。"),
    ("market_cap", "流通市值（元）", "量能与规模", field("market_cap"), 1e10, "这里是流通市值，不是总市值；1e10 即 100 亿元。"),
    ("price_ma_ratio", "收盘价 / 均线", "趋势与均线", fn("ratio", _close, y=fn("sma", _close, 20)), 1, "1 表示收盘恰好位于均线；0.98 表示低于均线 2%。"),
    ("macd", "MACD DIF 数值", "技术指标", fn("macd"), 0, "固定 12/26；0 表示零轴。"),
    ("upper_shadow", "上影线占开盘价", "K线结构", fn("ratio", fn("sub", field("high"), y=fn("max", field("open"), y=_close)), y=field("open")), .03, "上影 = 最高价 − 较高的开盘/收盘。"),
]:
    _add(_key, _name, _cat, cond(_name, _expr, ">", _value), _note)
_add("ema_compare", "两条 EMA 比较", "趋势与均线", cond("EMA 金叉", fn("ema", _close, 5), "cross_up", fn("ema", _close, 20)),
     "上穿/下穿按相邻两日收盘后的指标值判断，只在交叉当天触发。")
_add("macd_cross", "MACD DIF 与 DEA", "技术指标", cond("MACD 金叉", fn("macd"), "cross_up", fn("macd_signal")),
     "DIF 固定 12/26，DEA 固定 9；可改下穿或持续高于。")
_add("boll_upper", "收盘价与布林上轨", "技术指标", cond("收盘上穿布林上轨", _close, "cross_up", fn("boll_upper", _close, 20, k=2)), "轨道包含当天数据。")
_add("boll_lower", "收盘价与布林下轨", "技术指标", cond("收盘下穿布林下轨", _close, "cross_down", fn("boll_lower", _close, 20, k=2)), "轨道包含当天数据。")
_add("break_low", "跌破此前低点", "突破与涨跌", cond("跌破此前低点", _close, "<", fn("lag", fn("min", field("low"), 20), 1)), "前期低点不包含当天。")

LIBRARY_FINGERPRINTS = {fingerprint(m["condition"]) for m in LIBRARY}
