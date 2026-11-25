import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft } from 'lucide-react'
import { type CompareSide, type SummaryRow, useCompare } from '../../api/client'
import { fmtPct, trendClass } from '../../lib/format'
import { conditionText } from './ruleText'
import './patterns.css'

const DIFF: Record<string, string> = {
  start: '统计起点', asof: '截止日', markets: '市场范围', min_bars: '最少 K 线数', exclude_st: 'ST 过滤', cooldown: '冷却期',
  horizons: '观察周期', data_version: '数据版本', coverage_errors: '部分股票读取异常',
}

/** 两个研究并排对比：条件差异、事件重叠、各周期统计。 */
export default function ComparePage() {
  const [params] = useSearchParams()
  const left = params.get('left') ?? ''
  const right = params.get('right') ?? ''
  const cmp = useCompare(left, right)

  if (cmp.isError) return <div className="card state error">{cmp.error.message}。<Link to="/patterns">返回形态测试</Link></div>
  if (!cmp.data) return <div className="state">读取对比…</div>
  const c = cmp.data
  const horizons = c.left.summary.map(r => r.horizon).filter(h => c.right.summary.some(r => r.horizon === h))

  return (
    <div className="pt-report">
      <Link to={`/patterns/jobs/${right}`} className="back muted"><ArrowLeft size={15} />返回研究</Link>
      <header className="pt-head"><h1>条件对比</h1><p className="muted">{c.note}</p></header>

      {!c.comparable && (
        <p className="warn"><AlertTriangle size={15} />两条研究的{c.differences.map(d => DIFF[d] ?? d).join('、')}不同，数字不能直接比较。</p>
      )}

      <section className="cmp-heads">
        <Side side={c.left} tag="A" />
        <Side side={c.right} tag="B" />
      </section>

      <section className="card">
        <div className="card-title">条件差异</div>
        <div className="cond-diff">
          {c.only_left.length > 0 && <div><span className="tag">仅 A</span>{c.only_left.map((x, i) => <p key={i}><b>{x.label}</b><code>{conditionText(x)}</code></p>)}</div>}
          {c.only_right.length > 0 && <div><span className="tag">仅 B</span>{c.only_right.map((x, i) => <p key={i}><b>{x.label}</b><code>{conditionText(x)}</code></p>)}</div>}
          {c.common_conditions.length > 0 && <div><span className="tag muted-tag">共同</span>{c.common_conditions.map((x, i) => <p key={i}><b>{x.label}</b><code>{conditionText(x)}</code></p>)}</div>}
        </div>
        <p className="muted footnote">
          历史事件：两边都有 {c.overlap.common.toLocaleString()} 个，仅 A {c.overlap.only_left.toLocaleString()} 个，仅 B {c.overlap.only_right.toLocaleString()} 个。
          同一只股票在冷却期内只保留第一次信号，所以增减条件后保留的信号日可能前后移动，“去掉条件”的一方也可能缺少部分原事件。
        </p>
      </section>

      <section className="card">
        <div className="card-title">各周期统计 <span className="muted">Δ = B − A</span></div>
        <div className="table-wrap">
          <table className="sum-table cmp-table">
            <thead>
              <tr><th rowSpan={2}>持有期</th><th colSpan={2}>有效样本</th><th colSpan={3}>上涨比例</th><th colSpan={3}>平均收益</th><th colSpan={3}>相对同期平均</th></tr>
              <tr><th>A</th><th>B</th><th>A</th><th>B</th><th>Δ</th><th>A</th><th>B</th><th>Δ</th><th>A</th><th>B</th><th>Δ</th></tr>
            </thead>
            <tbody>
              {horizons.map(h => {
                const a = c.left.summary.find(r => r.horizon === h)!
                const b = c.right.summary.find(r => r.horizon === h)!
                return (
                  <tr key={h}>
                    <td>{h} 日</td>
                    <td className="num">{a.valid.toLocaleString()}</td><td className="num">{b.valid.toLocaleString()}</td>
                    {cells(a, b, 'win_rate', false)}{cells(a, b, 'mean', true)}{cells(a, b, 'excess_mean', true)}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="muted footnote">样本少的一方数字波动更大；条件越多样本越少，收益看起来更高不代表方法更好。</p>
      </section>
    </div>
  )
}

function cells(a: SummaryRow, b: SummaryRow, key: 'win_rate' | 'mean' | 'excess_mean', colored: boolean) {
  const va = a[key], vb = b[key]
  const d = va != null && vb != null ? vb - va : null
  const cls = (v: number | null) => (colored ? trendClass(v) : '')
  return <>
    <td className={`num ${cls(va)}`}>{fmtPct(va, key === 'win_rate' ? 1 : 2, key !== 'win_rate')}</td>
    <td className={`num ${cls(vb)}`}>{fmtPct(vb, key === 'win_rate' ? 1 : 2, key !== 'win_rate')}</td>
    <td className="num delta">{d == null ? '—' : `${d > 0 ? '+' : ''}${(d * 100).toFixed(key === 'win_rate' ? 1 : 2)}${key === 'win_rate' ? ' 点' : '%'}`}</td>
  </>
}

function Side({ side, tag }: { side: CompareSide; tag: string }) {
  return (
    <Link to={`/patterns/jobs/${side.id}`} className="card cmp-side">
      <span className="tag">{tag}</span>
      <b>{side.name}</b>
      <span className="muted">{side.rule.conditions.length} 个条件 · {side.events.toLocaleString()} 个事件 · {side.stocks.toLocaleString()} 只股票 · 数据截至 {side.data_end}</span>
    </Link>
  )
}
