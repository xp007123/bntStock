import { useState } from 'react'
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowRight, CalendarDays, CandlestickChart, ChevronLeft, ChevronRight, MessagesSquare, Share2 } from 'lucide-react'
import { type PickItem, usePersonas, usePickDay, usePickStrategies } from '../../api/client'
import LineupPicker from '../rooms/LineupPicker'
import SubNav, { PICK_TABS } from '../../components/SubNav'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import PickShareCard from './PickShareCard'
import StrategyHead from './StrategyHead'
import './picks.css'

const pct0 = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`)

/** 某个策略的名单：每个交易日出的那几只，以及它们当天后来怎么样。页面上所有数字都来自接口。 */
export default function PicksPage() {
  const { strategy: STRATEGY = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const date = params.get('date') ?? undefined
  const day = usePickDay(STRATEGY, date)
  const strategies = usePickStrategies()
  const personas = usePersonas()
  const [chatting, setChatting] = useState<PickItem | null>(null)
  const [sharing, setSharing] = useState(false)

  const d = day.data
  const meta = strategies.data?.items.find(s => s.id === STRATEGY)
  const head = meta?.highlights ?? []
  const idx = d?.date ? d.days.indexOf(d.date) : -1
  const go = (to: string | undefined) => to && setParams(to === d?.days[d.days.length - 1] ? {} : { date: to })
  // 选了一个没有名单的日子（周末、节假日）：跳到它之前最近的一份
  const pickDate = (v: string) => { if (d && v) go([...d.days].reverse().find(x => x <= v) ?? d.days[0]) }
  const sim = meta?.record === 'sim'           // 趋势之王这类中线名单：不讲当天，讲入选之后
  const sealed = d?.items.filter(i => i.sealed).length ?? 0
  // 入选以来：收盘行情到了用日线算的；今天刚出的用实时价
  const since = (it: PickItem) => it.since_ret ?? (it.live && it.pick_price ? it.live.latest / it.pick_price - 1 : null)
  const followed = Math.max(0, ...(d?.items.map(i => i.since_days ?? 0) ?? [0]))
  const over10 = d?.items.filter(i => (i.since_max ?? 0) >= 0.1).length ?? 0
  const live = !!d && !d.settled && d.items.some(i => i.live)
  const sealedNow = d?.items.filter(i => i.live?.sealed).length ?? 0
  const waiting = d && d.today !== d.date && d.days[d.days.length - 1] === d.date && !date   // 今天的还没出，看到的是上一次的

  if (strategies.data && !meta) return <Navigate to="/picks" replace />

  return (
    <div className="picks">
      <SubNav items={PICK_TABS} />
      <StrategyHead id={STRATEGY} s={meta ?? d?.strategy} />

      {head.length > 0 && (
        <section className="pk-head card fade-in">
          {sim && <p className="pk-head-tag">仿真模拟盘的成绩</p>}
          {head.map(h => <div key={h.label}><span>{h.label}</span><b className="num">{pct0(h.value)}</b><small>{h.note}</small></div>)}
          <Link to={`/picks/${STRATEGY}/record`} className="pk-more">看{sim ? '仿真模拟盘' : '完整的历史表现'}<ArrowRight size={14} /></Link>
        </section>
      )}

      {sim && d?.best && d.best.length > 0 && (
        <section className="card pk-best fade-in">
          <h2 className="card-title">近一个月入选的票，涨得最好的</h2>
          <ol>
            {d.best.map(b => (
              <li key={b.code}>
                <Link to={`/picks/${STRATEGY}?date=${b.date}`}>
                  <b>{b.name}</b><small className="num">{b.date.slice(5)} 入选 · {b.days} 个交易日</small>
                  <em className={`num ${trendClass(b.ret)}`}>{fmtPct(b.ret, 1)}</em>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="card pk-list fade-in">
        <div className="pk-bar">
          <div className="pk-date">
            <button className="btn" disabled={idx <= 0} onClick={() => go(d?.days[idx - 1])} aria-label="前一个交易日"><ChevronLeft size={16} /></button>
            <label className="pk-pick" title="选日期">
              <b className="num">{d?.date ?? '—'}</b><CalendarDays size={15} />
              <input type="date" aria-label="选日期" value={d?.date ?? ''} min={d?.days[0]} max={d?.days[d.days.length - 1]}
                     onClick={e => { try { e.currentTarget.showPicker() } catch { /* 老浏览器：用它自带的方式 */ } }} onChange={e => pickDate(e.target.value)} />
            </label>
            <button className="btn" disabled={!d || idx < 0 || idx >= d.days.length - 1} onClick={() => go(d?.days[idx + 1])} aria-label="后一个交易日"><ChevronRight size={16} /></button>
            {d?.is_today && <span className="tag night">今天</span>}
          </div>
          {d && d.items.length > 0 && sim ? (
            followed > 0 ? <span className="muted">入选后 {followed} 个交易日，{over10} 只最高涨过 10%{followed >= (d.follow_days ?? 20) ? '' : '（还在跟踪）'}</span>
              : live ? <span className="pk-live"><i />实时 {d.live_time?.slice(11, 16)}</span>
              : <span className="muted">今天入选，明天起看入选后的表现</span>
          ) : d && d.items.length > 0 && (d.settled
            ? <span className="muted">这一天 {d.items.length} 只里，{sealed} 只收盘封住涨停</span>
            : live ? <span className="pk-live"><i />实时 {d.live_time?.slice(11, 16)} · 现在 {sealedNow} 只封着板</span>
            : <span className="muted">当天的结果在收盘后更新</span>)}
          {d && d.items.length > 0 && <button className="btn pk-share" onClick={() => setSharing(true)}><Share2 size={14} />{sim || d.settled ? '生成战报图' : '生成名单图'}</button>}
        </div>
        {waiting && <p className="pk-wait">今天（{d.today}）还没有名单——交易日 {meta?.publish_at ?? '09:25'} 之后出。下面是上一个交易日的。</p>}

        {day.isLoading ? <div className="state">读取中…</div>
          : day.isError ? <div className="state error">名单没读出来，稍后再试</div>
          : !d || d.items.length === 0 ? <div className="state">还没有名单。</div> : (
            <div className="table-wrap">
              <table className="pk-table">
                <thead>{sim
                  ? <tr><th>#</th><th>股票</th><th>入选价</th><th>入选以来</th><th>期间最高</th><th /></tr>
                  : <tr><th>#</th><th>股票</th><th>竞价涨幅</th><th>{live ? '现在' : '当天收盘'}</th><th>{live ? '此刻' : '结果'}</th><th /></tr>}</thead>
                <tbody>
                  {d.items.map(it => (
                    <tr key={it.code}>
                      <td className="num pk-rank">{it.rank}</td>
                      <td><Link to={`/ask/stock?code=${it.code}&h=21`} className="pk-name">{it.name}</Link><small className="num">{displayCode(it.code)}{it.board && it.board !== '主板' ? ` · ${it.board}` : ''}</small></td>
                      {sim ? (
                        <>
                          <td className="num">{it.pick_price?.toFixed(2) ?? '—'}<small className={trendClass(it.open_pct)}>开盘 {fmtPct(it.open_pct)}</small></td>
                          <td className={`num ${trendClass(since(it))}`}>{fmtPct(since(it))}<small>{it.since_days != null ? (it.since_days === 0 ? '入选当天' : `${it.since_days} 个交易日`) : it.live ? '今天，实时' : '等行情'}</small></td>
                          <td className={`num ${trendClass(it.since_max)}`}>{it.since_max != null ? fmtPct(it.since_max) : '—'}</td>
                        </>
                      ) : (
                        <>
                      <td className={`num ${trendClass(it.auction_pct)}`}>{fmtPct(it.auction_pct)}</td>
                      <td className={`num ${trendClass(it.settled ? it.day_pct : it.live?.change)}`}>{it.settled ? fmtPct(it.day_pct) : it.live ? fmtPct(it.live.change) : '—'}</td>
                      <td>{!it.settled ? (it.live ? (it.live.sealed ? <span className="tag pk-sealed">封板中</span> : it.live.touched ? <span className="tag plain">摸过涨停</span> : <span className="muted">没到涨停</span>) : <span className="muted">等收盘</span>) : it.sealed ? <span className="tag pk-sealed">封板</span> : it.touched ? <span className="tag plain">摸过涨停</span> : <span className="muted">没到涨停</span>}</td>
                        </>
                      )}
                      <td className="pk-acts">
                        {personas.data?.available && <button className="btn" onClick={() => setChatting(it)}><MessagesSquare size={14} />拉群聊聊</button>}
                        <Link className="btn" to={`/stocks/${it.code}`} title="看 K 线"><CandlestickChart size={14} /></Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>

      {sim && <p className="muted pk-note">入选价按入选当天的开盘价；“入选以来”看到入选后第 {d?.follow_days ?? 20} 个交易日收盘为止，“期间最高”是这段时间里最高价比入选价高多少。</p>}
      <p className="muted pk-note">点股票名字可以问小四它接下来一个月的历史概率；想把看法存下来，在小四的回答页里封存。名单按平台的固定规则筛出，不是买卖建议。</p>
      {chatting && <LineupPicker code={chatting.code} name={chatting.name} onClose={() => setChatting(null)} />}
      {sharing && <PickShareCard strategy={STRATEGY} date={d?.date} onClose={() => setSharing(false)} />}
    </div>
  )
}
