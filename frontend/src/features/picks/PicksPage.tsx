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
  const sealed = d?.items.filter(i => i.sealed).length ?? 0
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
          {head.map(h => <div key={h.label}><span>{h.label}</span><b className="num">{pct0(h.value)}</b><small>{h.note}</small></div>)}
          <Link to={`/picks/${STRATEGY}/record`} className="pk-more">看完整的历史表现<ArrowRight size={14} /></Link>
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
          {d && d.items.length > 0 && (d.settled
            ? <span className="muted">这一天 {d.items.length} 只里，{sealed} 只收盘封住涨停</span>
            : live ? <span className="pk-live"><i />实时 {d.live_time?.slice(11, 16)} · 现在 {sealedNow} 只封着板</span>
            : <span className="muted">当天的结果在收盘后更新</span>)}
          {d && d.items.length > 0 && <button className="btn pk-share" onClick={() => setSharing(true)}><Share2 size={14} />{d.settled ? '生成战报图' : '生成名单图'}</button>}
        </div>
        {waiting && <p className="pk-wait">今天（{d.today}）还没有名单——交易日 09:25 之后出。下面是上一个交易日的。</p>}

        {day.isLoading ? <div className="state">读取中…</div>
          : day.isError ? <div className="state error">名单没读出来，稍后再试</div>
          : !d || d.items.length === 0 ? <div className="state">还没有名单。</div> : (
            <div className="table-wrap">
              <table className="pk-table">
                <thead><tr><th>#</th><th>股票</th><th>竞价涨幅</th><th>{live ? '现在' : '当天收盘'}</th><th>{live ? '此刻' : '结果'}</th><th /></tr></thead>
                <tbody>
                  {d.items.map(it => (
                    <tr key={it.code}>
                      <td className="num pk-rank">{it.rank}</td>
                      <td><Link to={`/ask/stock?code=${it.code}&h=21`} className="pk-name">{it.name}</Link><small className="num">{displayCode(it.code)}{it.board && it.board !== '主板' ? ` · ${it.board}` : ''}</small></td>
                      <td className={`num ${trendClass(it.auction_pct)}`}>{fmtPct(it.auction_pct)}</td>
                      <td className={`num ${trendClass(it.settled ? it.day_pct : it.live?.change)}`}>{it.settled ? fmtPct(it.day_pct) : it.live ? fmtPct(it.live.change) : '—'}</td>
                      <td>{!it.settled ? (it.live ? (it.live.sealed ? <span className="tag pk-sealed">封板中</span> : it.live.touched ? <span className="tag plain">摸过涨停</span> : <span className="muted">没到涨停</span>) : <span className="muted">等收盘</span>) : it.sealed ? <span className="tag pk-sealed">封板</span> : it.touched ? <span className="tag plain">摸过涨停</span> : <span className="muted">没到涨停</span>}</td>
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

      <p className="muted pk-note">点股票名字可以问小四它接下来一个月的历史概率；想把看法存下来，在小四的回答页里封存。名单按平台的固定规则筛出，不是买卖建议。</p>
      {chatting && <LineupPicker code={chatting.code} name={chatting.name} onClose={() => setChatting(null)} />}
      {sharing && <PickShareCard strategy={STRATEGY} date={d?.date} onClose={() => setSharing(false)} />}
    </div>
  )
}
