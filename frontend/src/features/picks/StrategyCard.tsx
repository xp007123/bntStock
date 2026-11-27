import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { PickStrategyCard } from '../../api/client'
import { fmtPct, trendClass } from '../../lib/format'
import './picks.css'

const pct0 = (v: number) => `${Math.round(v * 100)}%`

/**
 * 一个策略一张卡：今天出了没有、最近一份名单怎么样、它最拿得出手的数。
 * 首页看板和“策略名单”页共用；说什么、拿哪个数说话都由后端按策略给，新增策略不用改这里。
 */
export default function StrategyCard({ s, full = false }: { s: PickStrategyCard; full?: boolean }) {
  const r = s.latest
  const when = !r?.date ? `交易日 ${s.publish_at} 出名单`
    : s.record === 'sim' ? `${r.is_today ? '今天' : r.date.slice(5)} 的名单 ${r.count} 只`
    : `${r.is_today ? '今天' : r.date.slice(5)} · ${r.mode === 'list' ? '名单已出，等收盘' : '已收盘'}`
  return (
    <Link to={`/picks/${s.id}`} className={`card sc ${full ? 'full' : ''}`}>
      <div className="sc-top">
        <b>{s.name}</b><span className="tag plain">{s.alias}</span>
        <span className={`sc-when ${r?.is_today ? 'today' : ''}`}>{when}</span>
      </div>
      {full && <p className="sc-tagline muted">{s.tagline}</p>}

      {r?.date ? (
        <div className="sc-body">
          <div className="sc-title">{r.title}</div>
          <ul className="sc-stars" aria-label={r.value_label}>
            {r.value_label && r.stars.length > 0 && <li className="sc-label">{r.value_label}</li>}
            {r.stars.slice(0, full ? 5 : 3).map(x => (
              <li key={x.code}>
                <span>{x.name}</span>
                <em className={`num ${trendClass(x.value)}`}>{fmtPct(x.value, 1)}</em>
                {x.tag && <i className={x.tag === '封板' ? 'hot' : ''}>{x.tag}</i>}
              </li>
            ))}
          </ul>
        </div>
      ) : <div className="sc-body"><div className="sc-title muted">还没有名单</div></div>}

      <div className="sc-foot">
        {s.highlights.slice(0, full ? 3 : 1).map(h => (
          <span key={h.label} className="sc-num"><b className="num">{pct0(h.value)}</b><span>{s.record === 'sim' && !full ? `仿真模拟盘${h.label}` : h.label}{h.note && <small>{h.note}</small>}</span></span>
        ))}
        <span className="sc-go">看名单<ArrowRight size={14} /></span>
      </div>
    </Link>
  )
}
