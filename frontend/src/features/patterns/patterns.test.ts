import { describe, expect, it } from 'vitest'
import type { Rule } from '../../api/client'
import { conditionText, exprText } from './ruleText'
import { extractParams, setParam } from './params'

const breakout: Rule = {
  name: '放量突破',
  conditions: [
    { label: '突破前期高点', left: { field: 'close' }, op: '>', right: { fn: 'lag', x: { fn: 'max', x: { field: 'high' }, n: 20 }, n: 1 } },
    { label: '放量', left: { field: 'volume' }, op: '>', right: { fn: 'mul', x: { fn: 'lag', x: { fn: 'sma', x: { field: 'volume' }, n: 20 }, n: 1 }, y: 1.5 } },
    { label: '跌幅', left: { fn: 'lag', x: { fn: 'change', x: { field: 'close' }, n: 20 }, n: 1 }, op: '<=', right: -0.1 },
  ],
}

describe('ruleText', () => {
  it('翻译常见表达式', () => {
    expect(conditionText(breakout.conditions[0])).toBe('收盘价 > 昨日 20 根内最高的最高价')
    expect(conditionText(breakout.conditions[1])).toBe('成交量 > 昨日 20 日均量 × 1.5')
    expect(exprText({ fn: 'sma', x: { field: 'close' }, n: 5 })).toBe('MA5')
  })
})

describe('params', () => {
  it('提取窗口、倍数与阈值并写回', () => {
    const params = extractParams(breakout)
    expect(params.map(p => [p.kind, p.value])).toEqual([
      ['window', 20], ['window', 20], ['factor', 1.5], ['window', 20], ['threshold', -0.1],
    ])
    const factor = params.find(p => p.kind === 'factor')!
    const next = setParam(breakout, factor.path, 2)
    expect((next.conditions[1].right as { y: number }).y).toBe(2)
    expect((breakout.conditions[1].right as { y: number }).y).toBe(1.5)
  })
})

import { patternVerdict } from './verdict'

describe('patternVerdict', () => {
  const row = (h: number, win: number, mean: number, excess: number, valid = 5000) =>
    ({ horizon: h, valid, unavailable: 0, win_rate: win, mean, median: mean / 2, p10: -0.1, p90: 0.1, excess_mean: excess, excess_n: valid })
  it('差距很小时说“差不多”', () => {
    const v = patternVerdict([row(5, 0.5, 0.004, 0.0005), row(10, 0.479, 0.0033, 0.0005)], [])!
    expect(v.horizon).toBe(10)
    expect(v.plain).toBe('出现之后的 10 个交易日里，大约每 10 次有 5 次在涨，和同一天随便买一只股票差不多。')
    expect(v.tone).toBe('same')
    expect(v.value).toBe('48')
  })
  it('明显更好或更差时说出差距', () => {
    expect(patternVerdict([row(10, 0.54, 0.0148, 0.0032)], [])!.plain).toContain('平均多赚 0.3 个百分点')
    expect(patternVerdict([row(10, 0.45, -0.01, -0.012)], [])!.plain).toContain('平均少赚 1.2 个百分点')
  })
  it('统计赚钱年份与提示样本太少', () => {
    const years = [2019, 2020, 2021, 2022].map((y, i) => ({ year: String(y), horizon: 10, valid: 10, mean: i < 3 ? 0.01 : -0.02, win_rate: 0.5 }))
    const v = patternVerdict([row(10, 0.5, 0.01, 0.005, 40)], years)!
    expect(v.notes).toContain('4 年里有 3 年平均是赚的')
    expect(v.notes).toContain('只出现过 40 次，样本太少，参考价值有限')
  })
})
