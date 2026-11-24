/** 数字格式化。涨跌颜色由调用方根据符号决定。 */

export const fmtPrice = (v: number | null | undefined, digits = 2) =>
  v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits)

export const fmtPct = (v: number | null | undefined, digits = 2, sign = true) => {
  if (v == null || !Number.isFinite(v)) return '—'
  const s = (v * 100).toFixed(digits)
  return `${sign && v > 0 ? '+' : ''}${s}%`
}

/** 成交额、成交量等大数：亿 / 万 */
export const fmtBig = (v: number | null | undefined, unit = '') => {
  if (v == null || !Number.isFinite(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e8) return `${(v / 1e8).toFixed(2)}亿${unit}`
  if (a >= 1e4) return `${(v / 1e4).toFixed(2)}万${unit}`
  return `${v.toFixed(0)}${unit}`
}

export const trendClass = (v: number | null | undefined) => (v == null || v === 0 ? '' : v > 0 ? 'up' : 'down')

/** sz000001 → 000001.SZ */
export const displayCode = (code: string) => `${code.slice(2)}.${code.slice(0, 2).toUpperCase()}`
