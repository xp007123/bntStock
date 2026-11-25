import { describe, expect, it } from 'vitest'
import { dailyChange, sma } from './indicators'
import { displayCode, fmtBig, fmtPct, trendClass } from './format'

describe('sma', () => {
  it('窗口未满为 null', () => {
    expect(sma([1, 2, 3, 4], 3)).toEqual([null, null, 2, 3])
  })
})

describe('dailyChange', () => {
  it('优先使用前收盘价（除权后）', () => {
    expect(dailyChange(5.2, 5.0, 10)).toBeCloseTo(0.04)
    expect(dailyChange(11, undefined, 10)).toBeCloseTo(0.1)
  })
})

describe('format', () => {
  it('百分比带符号', () => {
    expect(fmtPct(0.0123)).toBe('+1.23%')
    expect(fmtPct(-0.05)).toBe('-5.00%')
    expect(fmtPct(null)).toBe('—')
  })
  it('大数用亿/万', () => {
    expect(fmtBig(1.66e9)).toBe('16.60亿')
    expect(fmtBig(52000)).toBe('5.20万')
    expect(fmtBig(1.8251e12)).toBe('1.83万亿')
  })
  it('红涨绿跌', () => {
    expect(trendClass(0.01)).toBe('up')
    expect(trendClass(-0.01)).toBe('down')
    expect(trendClass(0)).toBe('')
  })
  it('代码显示', () => expect(displayCode('sh600519')).toBe('600519.SH'))
})
