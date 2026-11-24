/** 简单移动平均。窗口未满的位置为 null，不用部分数据冒充。 */
export function sma(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= window) sum -= values[i - window]
    if (i >= window - 1) out[i] = sum / window
  }
  return out
}

/** 当日涨跌幅：优先用前收盘价（已考虑除权），否则用上一根收盘价。 */
export function dailyChange(close: number, prevClose: number | undefined, lastClose: number | undefined): number | null {
  const base = prevClose ?? lastClose
  return base ? close / base - 1 : null
}
