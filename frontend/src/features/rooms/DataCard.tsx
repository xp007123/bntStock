import { Link } from 'react-router-dom'
import type { RoomCard } from '../../api/client'
import { fmtBig, fmtPct, fmtPrice, trendClass } from '../../lib/format'
import { horizonText } from '../ask/horizons'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`)

/** 概率条：橙色是“相似的时候”，竖线是平时。和自选卡同一种画法。 */
function ProbBar({ prob, base }: { prob: number; base?: number | null }) {
  return (
    <div className="watch-bar" aria-hidden="true">
      <i style={{ width: `${Math.max(0, Math.min(1, prob)) * 100}%` }} />
      {base != null && <u style={{ left: `${base * 100}%` }} />}
    </div>
  )
}

/**
 * 数据卡：角色说“我查了”的时候挂在消息下面。
 * 上面的数字全部来自引擎，不是模型写的；模型嘴上说什么，不影响这张卡。
 */
export default function DataCard({ card }: { card: RoomCard }) {
  const c = card
  if (c.type === 'outlook' || c.type === 'option') {
    const option = c.type === 'option'
    return (
      <div className="data-card">
        <span className="data-title">{c.name} · {horizonText(c.horizon)}{option ? `平值看涨（期权费 ${(c.fee * 100).toFixed(1)}%）能回本的比例` : '后在涨的比例'}</span>
        <div className="data-main"><b className="num">{pct(c.prob)}</b><ProbBar prob={c.prob} base={c.base_prob} /></div>
        <span className="data-foot">和现在相似的 {c.n} 个时候 · 平时 {pct(c.base_prob)}
          {!option && c.mean != null && <> · 平均 <em className={`num ${trendClass(c.mean)}`}>{fmtPct(c.mean, 1)}</em></>}
          {option && c.payoff_mean != null && <> · 扣费后平均 <em className={`num ${trendClass(c.payoff_mean)}`}>{fmtPct(c.payoff_mean, 1)}</em></>}
        </span>
      </div>
    )
  }
  if (c.type === 'recent') {
    return (
      <div className="data-card">
        <span className="data-title">{c.name} · 最近走势 · {c.date}</span>
        <div className="data-row">
          <span>收盘 <b className="num">{fmtPrice(c.close)}</b></span>
          {[['1 周', c.r5], ['1 个月', c.r20], ['3 个月', c.r60]].map(([label, v]) => v != null && (
            <span key={label as string}>{label} <em className={`num ${trendClass(v as number)}`}>{fmtPct(v as number, 1)}</em></span>
          ))}
        </div>
        <span className="data-foot">比一年高点低 {pct(Math.abs(c.off_high))}{c.vol_ratio != null && <> · 近 5 天成交量是前 60 天的 {c.vol_ratio.toFixed(1)} 倍</>}</span>
      </div>
    )
  }
  if (c.type === 'financials') {
    return (
      <div className="data-card">
        <span className="data-title">{c.name} · 基本面和估值</span>
        <div className="data-row">
          <span>市盈率 <b className="num">{c.ttm_loss ? '亏损' : c.pe_ttm != null ? c.pe_ttm.toFixed(1) : '—'}</b></span>
          <span>市净率 <b className="num">{c.pb != null ? c.pb.toFixed(2) : '—'}</b></span>
          <span>负债率 <b className="num">{pct(c.debt_ratio)}</b></span>
          <span>总市值 <b className="num">{fmtBig(c.total_mcap)}</b></span>
        </div>
        <span className="data-foot">最新一期{c.report ? `（${c.report}）` : ''}：营收同比 <em className={`num ${trendClass(c.revenue_yoy)}`}>{fmtPct(c.revenue_yoy, 0)}</em>
          ，净利润同比 <em className={`num ${trendClass(c.profit_yoy)}`}>{fmtPct(c.profit_yoy, 0)}</em></span>
      </div>
    )
  }
  if (c.type === 'compare') {
    return (
      <div className="data-card">
        <span className="data-title">两只对着看 · {horizonText(c.horizon)}后在涨的比例</span>
        {(c.items as any[]).map(x => (
          <div key={x.code} className="data-main compact"><span>{x.name}</span><b className="num">{pct(x.prob)}</b><ProbBar prob={x.prob} base={x.base_prob} /></div>
        ))}
      </div>
    )
  }
  if (c.type === 'picks') {
    const hit = c.hit as any
    const h = hit?.headline
    return (
      <div className="data-card">
        <span className="data-title">{c.name} · 在不在选股名单里</span>
        {!hit ? <span className="data-foot">不在最近一次的名单里</span> : (
          <>
            <div className="data-row">
              <span><Link to={`/picks/${hit.strategy ?? 'sjm'}?date=${hit.date}`}>{hit.name}</Link> <b className="num">第 {hit.rank} 名</b></span>
              <span>{hit.date}</span>
              {hit.auction_pct != null && <span>竞价 <em className={`num ${trendClass(hit.auction_pct)}`}>{fmtPct(hit.auction_pct, 1)}</em></span>}
            </div>
            {h && <span className="data-foot">名单过去 {h.days} 个交易日：当天封板 {(h.sealed_rate * 100).toFixed(1)}%{h.market_sealed_rate != null && <>（全市场 {(h.market_sealed_rate * 100).toFixed(1)}%）</>}</span>}
          </>
        )}
      </div>
    )
  }
  if (c.type === 'methods') {
    const hits = c.hits as any[]
    return (
      <div className="data-card">
        <span className="data-title">{c.name} · 今天符合哪些常见买法</span>
        {hits.length === 0 ? <span className="data-foot">{c.checked} 种常见买法，今天一种都不符合。</span> : hits.map(h => (
          <div key={h.method} className="data-row"><span><b>{h.method}</b></span>
            <span>历史上之后 {h.horizon} 天在涨 <b className="num">{pct(h.win_rate)}</b></span></div>
        ))}
        <Link to="/patterns" className="data-link">去方法库看</Link>
      </div>
    )
  }
  if (c.type === 'limitup') {
    return (
      <div className="data-card">
        <span className="data-title">{c.name} · 历史上涨停之后</span>
        {c.n === 0 ? <span className="data-foot">最近 {c.days} 个交易日里没有涨停过。</span> : (
          <>
            <div className="data-row">
              <span>涨停过 <b className="num">{c.n}</b> 次</span>
              {c.next_up != null && <span>第二天还在涨 <b className="num">{pct(c.next_up)}</b></span>}
              {c.next_mean != null && <span>第二天平均 <em className={`num ${trendClass(c.next_mean)}`}>{fmtPct(c.next_mean, 1)}</em></span>}
              {c.week_mean != null && <span>一周后平均 <em className={`num ${trendClass(c.week_mean)}`}>{fmtPct(c.week_mean, 1)}</em></span>}
            </div>
            <span className="data-foot">最近 {c.days} 个交易日{c.streak > 0 ? ` · 现在连着 ${c.streak} 天涨停` : ''}{c.next_n < 10 ? ' · 次数不多，只能当参考' : ''}</span>
          </>
        )}
      </div>
    )
  }
  if (c.type === 'sector') {
    const top = c.top as { code: string; name: string; pct: number }[]
    return (
      <div className="data-card">
        <span className="data-title">{c.name} · 在{c.sector}里的位置</span>
        <div className="data-row">
          <span>当天 <em className={`num ${trendClass(c.pct)}`}>{fmtPct(c.pct, 1)}</em></span>
          <span>行业里排第 <b className="num">{c.rank}</b> / {c.n}</span>
          <span>上涨 <b className="num">{c.up}</b> 只</span>
          <span>涨停 <b className="num">{c.limit}</b> 只</span>
        </div>
        <span className="data-foot">涨得最多的：{top.map(t => `${t.name} ${fmtPct(t.pct, 1)}`).join('、')}</span>
      </div>
    )
  }
  return null
}
