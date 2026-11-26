import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useSignals } from '../../api/client'
import { fmtPct, trendClass } from '../../lib/format'
import './signals.css'

/**
 * 自选 × 方法库：你的自选里，今天有哪只符合哪种方法，这个方法过去出现之后 20 天大多怎么样。
 * 方法库由系统按默认参数统一计算，每天收盘数据更新后重算。
 * compact：首页右栏用，没有命中时不显示。
 */
export default function SignalsCard({ compact = false }: { compact?: boolean }) {
  const q = useSignals()
  const d = q.data
  if (compact && (!d || d.items.length === 0)) return null
  const hits = d?.items.reduce((n, i) => n + i.hits.length, 0) ?? 0

  return (
    <section className={`card signals ${compact ? 'compact' : ''}`}>
      <div className="card-title">
        <span>今天你的自选里</span>
        {compact ? <Link to="/watch" className="more">全部<ArrowRight size={14} /></Link>
          : d && <span className="muted">对照方法库里的 {d.methods_total} 个方法</span>}
      </div>
      {q.isLoading ? <p className="muted">读取中…</p>
        : q.isError ? <p className="muted">读取失败：{q.error.message}</p>
        : !d ? null
        : d.watch_count === 0 ? <p className="muted">还没有自选。加几只进来，小四每天收盘后帮你看看有没有哪只符合方法库里的方法。</p>
        : (
          <>
            {d.methods_ready < d.methods_total && <p className="muted signals-wait">方法库还在用最新数据重算（{d.methods_ready} / {d.methods_total}），算完自动更新。</p>}
            {hits === 0 ? (
              d.methods_ready > 0 && <p className="muted">今天你的 {d.watch_count} 只自选，都没有符合方法库里的方法。这很正常，大部分日子都是这样。</p>
            ) : (
              <ul className="signals-list">
                {d.items.flatMap(i => i.hits.map(h => ({ ...h, code: i.code, name: i.name }))).slice(0, compact ? 3 : undefined).map(h => (
                  <li key={`${h.code}-${h.index}`}>
                    <Link to={`/patterns/jobs/${h.job}`}>
                      <div className="sig-head"><b>{h.name}</b><span className="tag">{h.method}</span></div>
                      {h.history ? (
                        <p>这个方法过去出现 {h.history.valid.toLocaleString()} 次，之后 {h.history.horizon} 个交易日
                          {h.history.win_rate != null && <> 涨的占 <b>{Math.round(h.history.win_rate * 100)}%</b></>}
                          {h.history.mean != null && <>，平均 <b className={trendClass(h.history.mean)}>{fmtPct(h.history.mean, 1)}</b></>}。</p>
                      ) : <p className="muted">{h.description}</p>}
                      {!compact && h.reasons.length > 0 && (
                        <ul className="sig-reasons">{h.reasons.slice(0, 4).map((r, k) => <li key={k}>{r.label}</li>)}</ul>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {!compact && hits > 0 && <p className="muted signals-note">符合不等于会涨：表里是这个方法在全市场的历史平均，不是这只股票的保证。点开能看方法的完整报告。</p>}
          </>
        )}
    </section>
  )
}
