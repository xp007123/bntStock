import type { SummaryRow, YearRow } from '../../api/client'

/** 小于这个差距（0.2 个百分点）就说“差不多”，避免把噪声说成本事 */
export const SAME_THRESHOLD = 0.002

export type PatternVerdict = {
  horizon: number
  value: string          // 上涨比例，百分数
  dots: number           // 每 100 次里在涨的次数
  plain: string          // 一句大白话结论
  notes: string[]        // 补充说明（平均、对照、年份、样本）
  tone: 'good' | 'bad' | 'same'
}

const pp = (v: number) => `${Math.abs(v * 100).toFixed(1)} 个百分点`
const pct = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v * 100).toFixed(1)}%`

/** 把形态研究的统计翻译成一句人话：先说多常涨，再说比随便买好不好。 */
export function patternVerdict(summary: SummaryRow[], years: YearRow[], preferred = 10): PatternVerdict | null {
  const row = summary.find(r => r.horizon === preferred) ?? summary[Math.floor(summary.length / 2)] ?? summary[0]
  if (!row || row.win_rate == null || row.valid === 0) return null
  const h = row.horizon
  const win = row.win_rate
  const tens = Math.round(win * 10)
  const e = row.excess_mean
  const tone: PatternVerdict['tone'] = e == null || Math.abs(e) < SAME_THRESHOLD ? 'same' : e > 0 ? 'good' : 'bad'

  const versus = e == null ? '' :
    tone === 'same' ? '，和同一天随便买一只股票差不多' :
    tone === 'good' ? `，比同一天随便买一只股票平均多赚 ${pp(e)}` :
    `，比同一天随便买一只股票平均少赚 ${pp(e)}`
  const plain = `出现之后的 ${h} 个交易日里，大约每 10 次有 ${tens} 次在涨${versus}。`

  const notes: string[] = []
  if (row.mean != null) notes.push(`平均${row.mean >= 0 ? '涨' : '跌'} ${pct(row.mean).replace(/^[+−]/, '')}，一半的情况好于 ${pct(row.median ?? 0)}`)
  const ys = years.filter(y => y.horizon === h && y.mean != null && y.valid > 0)
  if (ys.length >= 3) {
    const good = ys.filter(y => (y.mean ?? 0) > 0).length
    notes.push(`${ys.length} 年里有 ${good} 年平均是赚的`)
  }
  if (row.valid < 100) notes.push(`只出现过 ${row.valid} 次，样本太少，参考价值有限`)
  else notes.push(`一共算了 ${row.valid.toLocaleString()} 次`)
  return { horizon: h, value: (win * 100).toFixed(0), dots: win * 100, plain, notes, tone }
}
