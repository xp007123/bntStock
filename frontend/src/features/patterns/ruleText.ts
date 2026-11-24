import type { Condition, Expr } from '../../api/client'

const FIELD: Record<string, string> = {
  open: '开盘价', high: '最高价', low: '最低价', close: '收盘价', volume: '成交量', amount: '成交额', market_cap: '流通市值',
}
const OP: Record<string, string> = { '>': '>', '>=': '≥', '<': '<', '<=': '≤', cross_up: '上穿', cross_down: '下穿' }

const isField = (e: Expr, name?: string): e is { field: string } =>
  typeof e === 'object' && 'field' in e && (!name || e.field === name)

/** 把规则表达式翻译成中文短语，用于展示“实际条件”。 */
export function exprText(e: Expr | undefined): string {
  if (e === undefined) return ''
  if (typeof e === 'number') return String(+e.toFixed(6))
  if ('field' in e) return FIELD[e.field] ?? e.field
  const { fn, x, y, n, k } = e
  const X = exprText(x)
  switch (fn) {
    case 'sma':
      if (x && isField(x, 'close')) return `MA${n ?? 20}`
      if (x && isField(x, 'volume')) return `${n ?? 20} 日均量`
      return `${X} 的 ${n ?? 20} 日均值`
    case 'ema': return x && isField(x, 'close') ? `EMA${n ?? 20}` : `${X} 的 ${n ?? 20} 日 EMA`
    case 'max': case 'min': {
      const word = fn === 'max' ? '较大值' : '较小值'
      if (y !== undefined) return `${X} 与 ${exprText(y)} 的${word}`
      return `${n ?? 20} 根内${fn === 'max' ? '最高' : '最低'}的${X}`
    }
    case 'lag': return n === 1 ? `昨日${/^[0-9]/.test(X) ? ' ' : ''}${X}` : `${n ?? 20} 根前的 ${X}`
    case 'change': return `${X} 的 ${n ?? 20} 根涨跌幅`
    case 'ratio': return `(${X} ÷ ${exprText(y)})`
    case 'add': return `(${X} + ${exprText(y)})`
    case 'sub': return `(${X} − ${exprText(y)})`
    case 'mul': return `${X} × ${exprText(y)}`
    case 'abs': return `|${X}|`
    case 'rsi': return `RSI${n ?? 14}`
    case 'atr': return `ATR${n ?? 14}`
    case 'macd': return 'MACD 的 DIF'
    case 'macd_signal': return 'MACD 的 DEA'
    case 'boll_upper': return `布林上轨(${n ?? 20}, ${k ?? 2})`
    case 'boll_lower': return `布林下轨(${n ?? 20}, ${k ?? 2})`
    default: return fn
  }
}

export const conditionText = (c: Condition) => `${exprText(c.left)} ${OP[c.op] ?? c.op} ${exprText(c.right)}`
export const opText = (op: string) => OP[op] ?? op
