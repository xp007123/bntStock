import type { Expr, Rule } from '../../api/client'

/** 规则里可以调整的数字：比较阈值、倍数、窗口长度。路径用于写回。 */
export type Param = { path: (string | number)[]; condition: number; label: string; kind: 'threshold' | 'factor' | 'window'; value: number }

function walk(e: Expr, path: (string | number)[], out: Omit<Param, 'condition' | 'label'>[], role: 'threshold' | 'factor') {
  if (typeof e === 'number') { out.push({ path, kind: role, value: e }); return }
  if ('field' in e) return
  // “昨日”（lag 1）是结构而不是参数，不提供调整
  if (e.n !== undefined && !(e.fn === 'lag' && e.n === 1)) out.push({ path: [...path, 'n'], kind: 'window', value: e.n })
  if (e.x !== undefined) walk(e.x, [...path, 'x'], out, 'factor')
  if (e.y !== undefined) walk(e.y, [...path, 'y'], out, 'factor')
}

export function extractParams(rule: Rule): Param[] {
  const params: Param[] = []
  rule.conditions.forEach((c, i) => {
    const found: Omit<Param, 'condition' | 'label'>[] = []
    walk(c.left, ['conditions', i, 'left'], found, 'threshold')
    walk(c.right, ['conditions', i, 'right'], found, 'threshold')
    for (const f of found) {
      const what = f.kind === 'window' ? '窗口（根）' : f.kind === 'threshold' ? '阈值' : '倍数'
      params.push({ ...f, condition: i, label: `${c.label} · ${what}` })
    }
  })
  return params
}

export function setParam(rule: Rule, path: (string | number)[], value: number): Rule {
  const copy: Rule = JSON.parse(JSON.stringify(rule))
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let node: any = copy
  for (const key of path.slice(0, -1)) node = node[key]
  node[path[path.length - 1]] = value
  return copy
}
