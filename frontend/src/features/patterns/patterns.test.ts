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
