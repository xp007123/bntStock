import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useDataVersion, useIndices, useJobs, useJudgments, useMe } from '../../api/client'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import Seal from '../../components/Seal'
import { fmtPct, fmtPrice, trendClass } from '../../lib/format'
import { isRevealed } from '../../lib/motion'
import { horizonText } from '../ask/horizons'
import JobList from '../patterns/JobList'
import AskPanel from './AskPanel'
import WatchlistCard from './WatchlistCard'
import '../patterns/patterns.css'
import './HomePage.css'

const greeting = () => {
  const h = new Date().getHours()
  return h < 5 ? '夜深了' : h < 11 ? '早上好' : h < 13 ? '中午好' : h < 18 ? '下午好' : '晚上好'
}

/** 首页：左边墨黑主卡里向小四提问；右边是交给小四保管的判断、大盘和数据口径。全部来自接口。 */
export default function HomePage() {
  const me = useMe()
  // 选好股票时小四点一下头
  const [nod, setNod] = useState(false)
  const picked = () => { setNod(true); window.setTimeout(() => setNod(false), 1600) }
  return (
    <section className="home">
      <header className="home-hello fade-in">
        <h1><span>{greeting()}，</span>{me.data?.username}</h1>
        <h1>今天想验证什么？</h1>
      </header>

      <div className="home-grid">
        <div className="home-main stagger">
          <section className="home-hero">
            <div className="hero-text">
              <span className="hero-eyebrow"><i />问小四</span>
              <h2>说给小四听，<br />它去翻历史。</h2>
              <p>一只股票、一个期权报价、一个你常用的买点都行。小四会去翻 2007 年以来的历史，告诉你类似的情况后来大多怎么样，最坏会怎样。</p>
            </div>
            <div className="hero-pet"><HomeResearchPet size={168} followPointer status={nod ? 'complete' : 'idle'} /></div>
            <AskPanel onPick={picked} />
          </section>
          <JobsCard />
        </div>

        <aside className="home-side stagger">
          <WatchlistCard />
          <JudgmentsCard />
          <IndicesCard />
          <DataCard />
        </aside>
      </div>

      <p className="home-foot">所有数字都来自历史统计，不构成投资建议。</p>
    </section>
  )
}

const More = ({ to, children }: { to: string; children: React.ReactNode }) =>
  <Link to={to} className="more">{children}<ArrowRight size={14} /></Link>

/** 我的判断：封存中的按“谁先揭晓”排，不用盯盘，只告诉你还要等多久。 */
function JudgmentsCard() {
  const q = useJudgments()
  const items = q.data?.items ?? []
  const sealed = items.filter(j => j.status === 'sealed').sort((a, b) => a.due_estimate.localeCompare(b.due_estimate))
  const settled = items.filter(j => j.status === 'settled')
  const rec = q.data?.record
  return (
    <section className="card home-card">
      <div className="card-title">我的判断 <More to="/judgments">全部</More></div>
      {q.isLoading ? <p className="muted">读取中…</p> : q.isError ? <p className="muted">判断读取失败</p> : items.length === 0 ? (
        <div className="home-empty">
          <Seal size={52} ghost>待<br />封存</Seal>
          <p>还没有判断。问完小四后点“封存这个判断”，它会替你保管到揭晓那天。</p>
        </div>
      ) : (
        <>
          <div className="mini-stats">
            <div><b className="num">{sealed.length}</b><span>封存中</span></div>
            <div><b className="num">{settled.length}</b><span>已揭晓</span></div>
            {rec && rec.settled > 0 && rec.hit_rate != null && <div><b className="num">{Math.round(rec.hit_rate * 100)}%</b><span>实际成真</span></div>}
          </div>
          <ul className="mini-list">
            {sealed.slice(0, 3).map(j => {
              const elapsed = j.prediction.elapsed ?? 0
              return (
                <li key={j.id}>
                  <Link to={`/judgments/${j.id}`}>
                    <div className="mini-line"><b>{j.name}</b><span>{j.kind === 'option' ? '问期权' : '问个股'} · {horizonText(j.horizon)}</span></div>
                    <div className="progress live" aria-label={`已走 ${elapsed} / ${j.horizon} 个交易日`}><i style={{ width: `${Math.min(100, elapsed / j.horizon * 100)}%` }} /></div>
                    <small>已走 {elapsed} / {j.horizon} 天 · 约 {j.due_estimate} 揭晓</small>
                  </Link>
                </li>
              )
            })}
            {settled.filter(j => sealed.length === 0 || !isRevealed(j.id)).slice(0, 3).map(j => (
              <li key={j.id}>
                <Link to={`/judgments/${j.id}`}>
                  <div className="mini-line"><b>{j.name}</b>{j.outcome && isRevealed(j.id) && <span className={`num ${trendClass(j.outcome.return)}`}>{fmtPct(j.outcome.return, 1)}</span>}</div>
                  <small>{j.kind === 'option' ? '问期权' : '问个股'} · {horizonText(j.horizon)} · {isRevealed(j.id) ? '已揭晓' : '到期了，点开揭晓'}</small>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function IndicesCard() {
  const q = useIndices()
  const items = (q.data ?? []).slice(0, 5)
  return (
    <section className="card home-card">
      <div className="card-title"><span>大盘 <span className="muted">{items[0]?.date ?? ''} 收盘</span></span><More to="/market">看指数</More></div>
      {q.isError ? <p className="muted">指数读取失败</p> : !q.data ? <p className="muted">读取中…</p> : (
        <ul className="index-list">
          {items.map(i => (
            <li key={i.code}>
              <span>{i.name}</span>
              <b className="num">{fmtPrice(i.close)}</b>
              <em className={`num chg ${trendClass(i.change)}`}>{fmtPct(i.change)}</em>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function JobsCard() {
  const q = useJobs()
  const jobs = (q.data ?? []).slice(0, 3)
  return (
    <section className="card home-card">
      <div className="card-title"><span>最近验证过的方法 <span className="muted">{q.data ? `共 ${q.data.length} 条` : ''}</span></span><More to="/patterns">去验证方法</More></div>
      {q.isLoading ? <p className="muted">读取中…</p> : jobs.length ? <JobList jobs={jobs} />
        : <p className="muted">还没有验证过方法。把你常用的买点写成条件，小四会告诉你它历史上灵不灵。</p>}
    </section>
  )
}

/** 数字有出处：小四的所有数字都从这份数据里算出来。 */
function DataCard() {
  const { data, isError } = useDataVersion()
  return (
    <section className="home-data">
      <span className="eyebrow">小四用的数据</span>
      {isError ? <b>数据未就绪</b> : !data ? <b>读取中…</b> : (
        <>
          <b className="num">日线截至 {data.data_end}</b>
          <p title={data.adjustment}>版本 {data.id}。每个交易日收盘后更新，小四的所有数字都从这份数据里算出来。</p>
        </>
      )}
    </section>
  )
}
