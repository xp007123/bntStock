import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, CandlestickChart, ChevronLeft, ChevronRight, MessagesSquare } from 'lucide-react'
import { ApiError, openRoom, type PickItem, usePersonas, usePickDay, usePickStrategies } from '../../api/client'
import SubNav, { PICK_TABS } from '../../components/SubNav'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import './picks.css'

const STRATEGY = 'sjm'
const pct0 = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`)
const pct1 = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

/** 今日名单：每个交易日开盘前出的 10 只，以及它们当天后来怎么样。页面上所有数字都来自接口。 */
export default function PicksPage() {
  const [params, setParams] = useSearchParams()
  const date = params.get('date') ?? undefined
  const day = usePickDay(STRATEGY, date)
  const strategies = usePickStrategies()
  const personas = usePersonas()
  const navigate = useNavigate()
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const d = day.data
  const head = strategies.data?.items.find(s => s.id === STRATEGY)?.headline
  const idx = d?.date ? d.days.indexOf(d.date) : -1
  const go = (to: string | undefined) => to && setParams(to === d?.days[d.days.length - 1] ? {} : { date: to })
  const chat = async (it: PickItem) => {
    setBusy(it.code); setError('')
    try { navigate(`/rooms/${(await openRoom(it.code)).id}`) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy('') }
  }
  const sealed = d?.items.filter(i => i.sealed).length ?? 0
  const waiting = d && d.today !== d.date && d.days[d.days.length - 1] === d.date && !date   // 今天的还没出，看到的是上一次的

  return (
    <div className="picks">
      <SubNav items={PICK_TABS} />
      <header className="page-head fade-in">
        <h1>竞价先锋<span className="tag plain">三角猫</span></h1>
        <p className="muted">{d?.strategy.tagline ?? '开盘前 5 分钟，挑出集合竞价里抢得最凶的 10 只。'}每个交易日 09:25 出名单。</p>
      </header>

      {head && (
        <section className="pk-head card fade-in">
          <div><span>当天封住涨停的</span><b className="num">{pct0(head.sealed_rate)}</b><small>同期全市场是 {pct1(head.market_sealed_rate)}</small></div>
          <div><span>名单里至少有一只封板的日子</span><b className="num">{pct0(head.any_sealed_rate)}</b><small>共 {head.days} 个交易日</small></div>
          <div><span>排第 1 名的那只，封住涨停的</span><b className="num">{pct0(head.top1_sealed_rate)}</b><small>竞价涨幅最高的一只</small></div>
          <Link to="/picks/record" className="pk-more">看完整的历史表现<ArrowRight size={14} /></Link>
        </section>
      )}

      <section className="card pk-list fade-in">
        <div className="pk-bar">
          <div className="pk-date">
            <button className="btn" disabled={idx <= 0} onClick={() => go(d?.days[idx - 1])} aria-label="前一个交易日"><ChevronLeft size={16} /></button>
            <b className="num">{d?.date ?? '—'}</b>
            <button className="btn" disabled={!d || idx < 0 || idx >= d.days.length - 1} onClick={() => go(d?.days[idx + 1])} aria-label="后一个交易日"><ChevronRight size={16} /></button>
            {d?.is_today && <span className="tag night">今天</span>}
          </div>
          {d && d.items.length > 0 && (d.settled
            ? <span className="muted">这一天 {d.items.length} 只里，{sealed} 只收盘封住涨停</span>
            : <span className="muted">当天的结果在收盘后更新（行情现在到 {d.data_end}）</span>)}
        </div>
        {waiting && <p className="pk-wait">今天（{d.today}）还没有名单——交易日 09:25 之后出。下面是上一个交易日的。</p>}

        {day.isLoading ? <div className="state">读取中…</div>
          : day.isError ? <div className="state error">名单没读出来，稍后再试</div>
          : !d || d.items.length === 0 ? <div className="state">还没有名单。</div> : (
            <div className="table-wrap">
              <table className="pk-table">
                <thead><tr><th>#</th><th>股票</th><th>竞价涨幅</th><th>当天收盘</th><th>结果</th><th /></tr></thead>
                <tbody>
                  {d.items.map(it => (
                    <tr key={it.code}>
                      <td className="num pk-rank">{it.rank}</td>
                      <td><Link to={`/ask/stock?code=${it.code}&h=21`} className="pk-name">{it.name}</Link><small className="num">{displayCode(it.code)}{it.board && it.board !== '主板' ? ` · ${it.board}` : ''}</small></td>
                      <td className={`num ${trendClass(it.auction_pct)}`}>{fmtPct(it.auction_pct)}</td>
                      <td className={`num ${trendClass(it.day_pct)}`}>{it.settled ? fmtPct(it.day_pct) : '—'}</td>
                      <td>{!it.settled ? <span className="muted">等收盘</span> : it.sealed ? <span className="tag pk-sealed">封板</span> : it.touched ? <span className="tag plain">摸过涨停</span> : <span className="muted">没到涨停</span>}</td>
                      <td className="pk-acts">
                        {personas.data?.available && <button className="btn" disabled={!!busy} onClick={() => chat(it)}><MessagesSquare size={14} />{busy === it.code ? '拉群中…' : '拉群聊聊'}</button>}
                        <Link className="btn" to={`/stocks/${it.code}`} title="看 K 线"><CandlestickChart size={14} /></Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {error && <p className="state error">{error}</p>}
      </section>

      {d && (
        <section className="card pk-rules">
          <h2 className="card-title">这 10 只是怎么选出来的</h2>
          <ol>{d.strategy.rules.map(r => <li key={r}>{r}</li>)}</ol>
          <p className="muted">点股票名字可以问小四它接下来一个月的历史概率；想把看法存下来，在小四的回答页里封存。名单是按固定规则筛出来的，不是买卖建议。</p>
        </section>
      )}
    </div>
  )
}
