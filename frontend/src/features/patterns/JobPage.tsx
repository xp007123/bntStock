import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, GitCompare, RefreshCw, SlidersHorizontal } from 'lucide-react'
import { ApiError, cancelJob, type EventSort, type Job, rerunJob, type StudyResult, useDataVersion, useJob, useJobEvents, useJobResult, useJobs } from '../../api/client'
import { displayCode, fmtBig, fmtPct, fmtPrice, trendClass } from '../../lib/format'
import { conditionText } from './ruleText'
import { STATUS } from './JobList'
import YearChart from './YearChart'
import Verdict from '../../components/Verdict'
import { patternVerdict } from './verdict'
import CaseViewer from './CaseViewer'
import VariantPanel from './VariantPanel'
import './patterns.css'

type Case = { code: string; name: string; date: string }

export default function JobPage() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const done = job.data?.status === 'completed'
  const result = useJobResult(id, done)

  if (job.isError) return <div className="card state error">研究不存在。<Link to="/patterns">返回方法库</Link></div>
  if (!job.data) return <div className="state">读取研究…</div>
  return (
    <div className="pt-report">
      <Link to="/patterns" className="back muted"><ArrowLeft size={15} />方法库</Link>
      <header className="pt-head">
        <h1>{job.data.name}</h1>
        <p className="muted">
          {job.data.created} 提交 · 数据版本 {job.data.data_version}（截至 {job.data.data_end}）
          {job.data.elapsed != null && <> · 用时 {job.data.elapsed} 秒</>}
        </p>
      </header>
      <Lineage job={job.data} />
      {done ? (result.data ? <Report job={job.data} result={result.data} /> : <div className="state">读取结果…</div>)
            : <><Conditions job={job.data} /><Progress job={job.data} /></>}
    </div>
  )
}

/** 由“增减一条条件”或“重跑”生成的研究，标明来源并提供对比入口。 */
function Lineage({ job }: { job: Job }) {
  if (job.comparison_base && job.comparison_change) {
    const ch = job.comparison_change
    return (
      <p className="lineage">
        基于 <Link to={`/patterns/jobs/${job.comparison_base}`}>原研究</Link>{ch.action === 'remove' ? '去掉' : '增加'}了一条条件「{ch.condition.label}」
        {job.status === 'completed' && <> · <Link to={`/patterns/compare?left=${job.comparison_base}&right=${job.id}`}>与原研究对比</Link></>}
      </p>
    )
  }
  if (job.rerun_of && job.rerun_of !== job.id) {
    return <p className="lineage">用最新数据重跑自 <Link to={`/patterns/jobs/${job.rerun_of}`}>原研究</Link>（数据截至 {job.data_end}）</p>
  }
  return null
}

function Toolbar({ job }: { job: Job }) {
  const [panel, setPanel] = useState<'variant' | 'compare' | null>(null)
  const [error, setError] = useState('')
  const version = useDataVersion()
  const jobs = useJobs()
  const navigate = useNavigate()
  // 只更新财务等附属数据时行情版本不变，不算旧数据
  const stale = !!version.data && version.data.id !== job.data_version && version.data.market_version !== job.data_version
  const others = (jobs.data ?? []).filter(j => j.status === 'completed' && j.id !== job.id)
  const rerun = async () => {
    setError('')
    try { navigate(`/patterns/jobs/${(await rerunJob(job.id)).id}`) } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }
  return (
    <>
      <div className="toolbar">
        {stale ? (
          <span className="stale-note">数据已更新到 {version.data?.data_end}，这条研究用的是旧数据。</span>
        ) : (
          <button className="btn" aria-pressed={panel === 'variant'} onClick={() => setPanel(p => (p === 'variant' ? null : 'variant'))}>
            <SlidersHorizontal size={15} />增减一条条件
          </button>
        )}
        <button className="btn" aria-pressed={panel === 'compare'} onClick={() => setPanel(p => (p === 'compare' ? null : 'compare'))}>
          <GitCompare size={15} />与其他研究对比
        </button>
        {stale && <button className="btn primary" onClick={rerun}><RefreshCw size={15} />用最新数据重跑</button>}
        {error && <span className="state error">{error}</span>}
      </div>
      {panel === 'variant' && <VariantPanel job={job} onClose={() => setPanel(null)} />}
      {panel === 'compare' && (
        <section className="card">
          <div className="card-title">选择对比的研究 <span className="muted">当前研究作为 A</span></div>
          {others.length === 0 ? <p className="muted">还没有其他已完成的研究。</p> : (
            <ul className="job-list">
              {others.map(o => (
                <li key={o.id}><Link to={`/patterns/compare?left=${job.id}&right=${o.id}`}>
                  <div className="job-line"><b>{o.name}</b><span className="muted">{o.event_count.toLocaleString()} 个事件</span></div>
                  <div className="muted job-meta">
                    {o.created.slice(5, 16)} · {o.conditions} 个条件 · 数据 {o.data_end}{o.data_version !== job.data_version ? '（数据版本不同）' : ''}
                  </div>
                </Link></li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  )
}

function Conditions({ job }: { job: Job }) {
  return (
    <section className="card">
      <div className="card-title">用的是哪些条件 <span className="muted">全部同时满足才算出现一次 · 同一只股票 {job.rule.cooldown} 天内只算一次</span></div>
      <ol className="cond-list">
        {job.rule.conditions.map((c, i) => <li key={i}><b>{c.label}</b><code>{conditionText(c)}</code></li>)}
      </ol>
    </section>
  )
}

function Progress({ job }: { job: Job }) {
  const qc = useQueryClient()
  const active = job.status === 'queued' || job.status === 'running'
  return (
    <section className="card progress-card">
      <div className="card-title">{STATUS[job.status]} <span className="muted">{job.message}</span></div>
      {active && <>
        <div className="bar"><i style={{ width: `${job.progress}%` }} /></div>
        <p className="muted">已发现 {job.event_count.toLocaleString()} 个历史事件 · 今日符合 {job.selected_count} 只。关闭页面不影响后台计算。</p>
        <button className="btn" onClick={async () => { await cancelJob(job.id); qc.invalidateQueries({ queryKey: ['pattern-job', job.id] }) }}>取消</button>
      </>}
    </section>
  )
}

function Report({ job, result }: { job: Job; result: StudyResult }) {
  const horizons = job.rule.horizons ?? [1, 3, 5, 10, 20]
  const [horizon, setHorizon] = useState(horizons.includes(10) ? 10 : horizons[horizons.length - 1])
  const [current, setCurrent] = useState<Case | null>(null)
  const open = (c: Case) => { setCurrent(c); requestAnimationFrame(() => document.getElementById('case')?.scrollIntoView({ behavior: 'smooth', block: 'start' })) }
  const v = patternVerdict(result.summary, result.years)

  return (
    <>
      {v ? (
        <section className="report-verdict">
          <Verdict label={`${v.horizon} 个交易日后在涨的比例`} value={v.value} dots={v.dots}
                   dotsCaption={<>每 100 次里<br />大约有 <b>{Math.round(v.dots)} 次</b>在涨</>}
                   plain={v.plain} note={v.notes.join(' · ')}
                   tag={v.tone === 'same' ? '结论：和随便买差不多' : v.tone === 'good' ? '结论：比随便买略好' : '结论：比随便买还差'} />
        </section>
      ) : <p className="state">没有足够的历史样本，算不出结论。</p>}

      <Conditions job={job} />
      <Toolbar job={job} />

      <section className="stat-tiles">
        <div><span>历史上出现过</span><b className="num">{result.deduplicated_events.toLocaleString()} 次</b><small>同一只股票 {job.rule.cooldown} 天内只算一次</small></div>
        <div><span>涉及股票</span><b className="num">{result.stocks.toLocaleString()} 只</b><small>一共查了 {result.scanned.toLocaleString()} 只</small></div>
        <div><span>今天符合</span><b className="num">{result.selected.length} 只</b><small>{job.data_end} 收盘后</small></div>
      </section>

      <section className="card">
        <div className="card-title">拿几天，结果怎样 <span className="muted">出现后第二天开盘买入，拿满 N 个交易日按收盘算；没扣手续费</span></div>
        <div className="table-wrap">
          <table className="sum-table">
            <thead><tr><th>拿几天</th><th>算了多少次</th><th>在涨的比例</th><th>平均涨跌</th><th>一半好于</th><th>运气最差的十分之一</th><th>运气最好的十分之一</th><th>比随便买</th></tr></thead>
            <tbody>
              {result.summary.map(r => (
                <tr key={r.horizon}>
                  <td>{r.horizon} 天</td>
                  <td className="num">{r.valid.toLocaleString()}{r.unavailable > 0 && <small className="muted"> / 排除 {r.unavailable}</small>}</td>
                  <td className="num"><span className="winbar" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(1, r.win_rate ?? 0)) * 100}%` }} /></span>{fmtPct(r.win_rate, 1, false)}</td>
                  <td className={`num ${trendClass(r.mean)}`}>{fmtPct(r.mean)}</td>
                  <td className={`num ${trendClass(r.median)}`}>{fmtPct(r.median)}</td>
                  <td className={`num ${trendClass(r.p10)}`}>{fmtPct(r.p10)}</td>
                  <td className={`num ${trendClass(r.p90)}`}>{fmtPct(r.p90)}</td>
                  <td className={`num ${trendClass(r.excess_mean)}`}>{fmtPct(r.excess_mean)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted footnote">“比随便买”：和同一天、同样条件下的所有股票平均相比，多赚或少赚多少。它不是指数，也不是能直接照着买的组合。</p>
      </section>

      <section className="card">
        <div className="card-title">
          每一年的表现 <span className="muted">有的方法只在某几年灵</span>
          <div className="seg" role="group" aria-label="拿几天">
            {horizons.map(h => <button key={h} aria-pressed={horizon === h} onClick={() => setHorizon(h)}>拿 {h} 天</button>)}
          </div>
        </div>
        <YearChart rows={result.years} horizon={horizon} />
      </section>

      <section className="card">
        <div className="card-title">今天符合的股票 <span className="muted">{job.data_end} 收盘后满足全部条件，按成交额排序；不是买入建议</span></div>
        {result.selected.length === 0 ? <p className="muted">今天没有股票满足全部条件。</p> : (
          <div className="table-wrap">
            <table className="list-table">
              <thead><tr><th>股票</th><th>行业</th><th>收盘</th><th>涨跌</th><th>成交额</th></tr></thead>
              <tbody>
                {result.selected.map(s => (
                  <tr key={s.code} onClick={() => open({ code: s.code, name: s.name, date: s.date })}>
                    <td><b>{s.name}</b> <span className="muted num">{displayCode(s.code)}</span></td>
                    <td className="muted">{s.sector}</td>
                    <td className="num">{fmtPrice(s.price)}</td>
                    <td className={`num ${trendClass(s.change)}`}>{fmtPct(s.change)}</td>
                    <td className="num">{fmtBig(s.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {current && <div id="case"><CaseViewer jobId={job.id} {...current} onClose={() => setCurrent(null)} /></div>}

      <Events job={job} horizons={horizons} onOpen={open} />

      <section className="card method">
        <div className="card-title">怎么算的、有哪些局限</div>
        <p>{result.method}</p>
        <p>{result.reference}</p>
        <ul>{result.limitations.map(l => <li key={l}>{l}</li>)}</ul>
        {result.errors.length > 0 && <p className="muted">{result.errors.length} 只股票读取异常，未计入。</p>}
      </section>
    </>
  )
}

function Events({ job, horizons, onOpen }: { job: Job; horizons: number[]; onOpen: (c: Case) => void }) {
  const [page, setPage] = useState(0)
  const [sort, setSort] = useState<EventSort>('date')
  const [horizon, setHorizon] = useState(horizons.includes(10) ? 10 : horizons[0])
  const size = 20
  const events = useJobEvents(job.id, page, sort, horizon, size)
  const total = events.data?.total ?? 0
  const SORTS: { id: EventSort; label: string }[] = [{ id: 'date', label: '最近' }, { id: 'typical', label: '典型' }, { id: 'best', label: '最好' }, { id: 'worst', label: '最差' }]
  return (
    <section className="card">
      <div className="card-title">
        历史案例 <span className="muted">{total.toLocaleString()} 个</span>
        <div className="case-sort">
          <div className="seg" role="group" aria-label="案例排序">
            {SORTS.map(o => <button key={o.id} aria-pressed={sort === o.id} onClick={() => { setSort(o.id); setPage(0) }}>{o.label}</button>)}
          </div>
          {sort !== 'date' && (
            <select aria-label="按哪个持有期挑选" value={horizon} onChange={e => { setHorizon(Number(e.target.value)); setPage(0) }}>
              {horizons.map(h => <option key={h} value={h}>按 {h} 日收益</option>)}
            </select>
          )}
        </div>
      </div>
      {sort === 'typical' && <p className="muted footnote">“典型”按 {horizon} 日收益最接近全体中位数排序，最能代表一般情况；“最好 / 最差”只用于核对形态，不代表全体。</p>}
      <div className="table-wrap">
        <table className="list-table">
          <thead><tr><th>入选日</th><th>股票</th><th>收盘</th>{horizons.map(h => <th key={h}>{h} 日</th>)}</tr></thead>
          <tbody>
            {(events.data?.items ?? []).map(e => (
              <tr key={e.code + e.date} onClick={() => onOpen({ code: e.code, name: e.name, date: e.date })}>
                <td className="num">{e.date}</td>
                <td><b>{e.name}</b> <span className="muted num">{displayCode(e.code)}</span></td>
                <td className="num">{fmtPrice(e.price)}</td>
                {horizons.map(h => <td key={h} className={`num ${trendClass(e.returns[String(h)])}`}>{fmtPct(e.returns[String(h)])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button className="btn" disabled={page === 0} onClick={() => setPage(p => p - 1)}>上一页</button>
        <span className="muted">{page + 1} / {Math.max(1, Math.ceil(total / size))}</span>
        <button className="btn" disabled={(page + 1) * size >= total} onClick={() => setPage(p => p + 1)}>下一页</button>
      </div>
      <p className="muted footnote">收盘为原始价格；“—”表示该周期无法计算（次日涨停买不进、停牌或观察期未走完）。点击一行查看 K 线与入选原因。</p>
    </section>
  )
}
