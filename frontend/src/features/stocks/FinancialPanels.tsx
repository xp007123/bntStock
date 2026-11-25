import { useState } from 'react'
import type { FinancialReport, Financials } from '../../api/client'
import { fmtBig, fmtPct, trendClass } from '../../lib/format'

const pick = (r: FinancialReport, ...keys: string[]) => {
  for (const k of keys) if (r.values[k] != null) return { v: r.values[k], y: r.yoy[k] }
  return { v: null, y: null }
}
const period = (d: string) => {
  const [y, m] = d.split('-')
  return `${y} ${{ '03': '一季报', '06': '中报', '09': '三季报', '12': '年报' }[m] ?? m}`
}

/** 侧栏：估值。市盈率用总市值 ÷ TTM 归母净利润，亏损时不计算。 */
export function ValuationCard({ fin }: { fin: Financials | undefined }) {
  if (!fin) return null
  const v = fin.valuation
  if (!fin.available || !v) return <div className="card"><div className="card-title">估值</div><p className="muted">暂无财务数据</p></div>
  return (
    <div className="card">
      <div className="card-title">估值 <span className="muted">{fin.price_date}</span></div>
      <dl className="kv">
        <dt>市盈率 TTM</dt><dd className="num">{v.ttm_loss ? <span className="down">亏损</span> : v.pe_ttm?.toFixed(2) ?? '—'}</dd>
        <dt>市净率</dt><dd className="num">{v.pb?.toFixed(2) ?? '—'}</dd>
        <dt>总市值</dt><dd className="num">{fmtBig(v.total_mcap)}</dd>
        <dt>流通市值</dt><dd className="num">{fmtBig(v.float_mcap)}</dd>
        <dt>资产负债率</dt><dd className="num">{fmtPct(v.debt_ratio, 1, false)}</dd>
        <dt>TTM 归母净利润</dt><dd className={`num ${trendClass(fin.ttm_profit)}`}>{fmtBig(fin.ttm_profit)}</dd>
      </dl>
      <p className="muted footnote">只用 {fin.asof} 前已披露的报告。</p>
    </div>
  )
}

/** 主区：最近若干期财务摘要，可展开三张报表的全部字段。数值为报告期累计值。 */
export function FinancialCard({ fin }: { fin: Financials | undefined }) {
  const [tab, setTab] = useState<'summary' | 'income' | 'balance' | 'cashflow'>('summary')
  if (!fin) return <section className="card"><div className="state">读取财务…</div></section>
  if (!fin.available || !fin.reports.length) return null
  const reports = fin.reports.slice(0, 8)
  const TABS = [{ id: 'summary', label: '摘要' }, { id: 'income', label: '利润表' }, { id: 'balance', label: '资产负债表' }, { id: 'cashflow', label: '现金流量表' }] as const
  return (
    <section className="card fin-card">
      <div className="card-title">
        财务 <span className="muted">{reports[0].format ?? ''} · 累计值 · 同比</span>
        <div className="seg" role="tablist">
          {TABS.map(t => <button key={t.id} aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>)}
        </div>
      </div>
      <div className="table-wrap">
        {tab === 'summary' ? (
          <table className="fin-table">
            <thead><tr><th>报告期</th><th>披露日</th><th>营业总收入</th><th>同比</th><th>归母净利润</th><th>同比</th><th>经营现金流净额</th><th>资产负债率</th></tr></thead>
            <tbody>
              {reports.map(r => {
                const rev = pick(r, 'R_operating_total_revenue', 'R_revenue')
                const np = pick(r, 'R_np_atoopc')
                const cf = pick(r, 'C_ncf_from_oa')
                const debt = r.values.B_total_liab != null && r.values.B_total_assets ? r.values.B_total_liab / r.values.B_total_assets : null
                return (
                  <tr key={r.date}>
                    <td>{period(r.date)}</td><td className="muted num">{r.published}</td>
                    <td className="num">{fmtBig(rev.v)}</td><td className={`num ${trendClass(rev.y)}`}>{fmtPct(rev.y, 1)}</td>
                    <td className={`num ${trendClass(np.v)}`}>{fmtBig(np.v)}</td><td className={`num ${trendClass(np.y)}`}>{fmtPct(np.y, 1)}</td>
                    <td className={`num ${trendClass(cf.v)}`}>{fmtBig(cf.v)}</td><td className="num">{fmtPct(debt, 1, false)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <table className="fin-table full">
            <thead><tr><th>项目</th>{reports.map(r => <th key={r.date}>{period(r.date)}</th>)}</tr></thead>
            <tbody>
              {fin.fields[tab].filter(f => reports.some(r => r.values[f.key] != null)).map(f => (
                <tr key={f.key}>
                  <td>{f.label}</td>
                  {reports.map(r => {
                    const v = r.values[f.key]
                    return <td key={r.date} className="num">{v == null ? '—' : f.unit === '元/股' ? v.toFixed(3) : fmtBig(v)}</td>
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="muted footnote">按披露日取数：每个报告期只用截至 {fin.asof} 已公开的最后一次修订。银行、券商、保险的报表科目不同，缺失项显示“—”。</p>
    </section>
  )
}
