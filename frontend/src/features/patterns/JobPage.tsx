import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { cancelJob, type Job, type StudyResult, useJob, useJobEvents, useJobResult } from '../../api/client'
import { displayCode, fmtBig, fmtPct, fmtPrice, trendClass } from '../../lib/format'
import { conditionText } from './ruleText'
import { STATUS } from './JobList'
import YearChart from './YearChart'
import CaseViewer from './CaseViewer'
import './patterns.css'

type Case = { code: string; name: string; date: string }

export default function JobPage() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const done = job.data?.status === 'completed'
  const result = useJobResult(id, done)

  if (job.isError) return <div className="card state error">研究不存在。<Link to="/patterns">返回形态测试</Link></div>
  if (!job.data) return <div className="state">读取研究…</div>
  return (
    <div className="pt-report">
      <Link to="/patterns" className="back muted"><ArrowLeft size={15} />形态测试</Link>
      <header className="pt-head">
        <h1>{job.data.name}</h1>
        <p className="muted">
          {job.data.created} 提交 · 数据版本 {job.data.data_version}（截至 {job.data.data_end}）
          {job.data.elapsed != null && <> · 用时 {job.data.elapsed} 秒</>}
        </p>
      </header>
      <Conditions job={job.data} />
      {done ? (result.data ? <Report job={job.data} result={result.data} /> : <div className="state">读取结果…</div>) : <Progress job={job.data} />}
    </div>
  )
}

function Conditions({ job }: { job: Job }) {
  return (
    <section className="card">
      <div className="card-title">实际条件 <span className="muted">冷却 {job.rule.cooldown} 根 · 观察 {job.rule.horizons?.join(' / ')} 日</span></div>
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

  return (
    <>
      <section className="stat-tiles">
        <div><span>历史事件</span><b className="num">{result.deduplicated_events.toLocaleString()}</b><small>原始信号 {result.raw_signals.toLocaleString()}，去重后</small></div>
        <div><span>涉及股票</span><b className="num">{result.stocks.toLocaleString()}</b><small>扫描 {result.scanned.toLocaleString()} 只</small></div>
        <div><span>今日符合</span><b className="num">{result.selected.length}</b><small>{job.data_end}</small></div>
      </section>

      <section className="card">
        <div className="card-title">历史表现 <span className="muted">信号次日开盘买入，持有 N 个交易日后收盘；未扣费</span></div>
        <div className="table-wrap">
          <table className="sum-table">
            <thead><tr><th>持有期</th><th>有效样本</th><th>上涨比例</th><th>平均收益</th><th>中位收益</th><th>最差 10%</th><th>最好 10%</th><th>相对同期平均</th></tr></thead>
            <tbody>
              {result.summary.map(r => (
                <tr key={r.horizon}>
                  <td>{r.horizon} 日</td>
                  <td className="num">{r.valid.toLocaleString()}{r.unavailable > 0 && <small className="muted"> / 排除 {r.unavailable}</small>}</td>
                  <td className="num">{fmtPct(r.win_rate, 1, false)}</td>
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
        <p className="muted footnote">“相对同期平均”：同一天、同样过滤条件下全部合格股票的等权平均收益之差，不是指数，也不是可交易组合。</p>
      </section>

      <section className="card">
        <div className="card-title">
          逐年表现
          <div className="seg" role="group" aria-label="持有期">
            {horizons.map(h => <button key={h} aria-pressed={horizon === h} onClick={() => setHorizon(h)}>{h} 日</button>)}
          </div>
        </div>
        <YearChart rows={result.years} horizon={horizon} />
      </section>

      <section className="card">
        <div className="card-title">今日符合 <span className="muted">{job.data_end} 收盘后满足全部条件，按成交额排序</span></div>
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
        <div className="card-title">口径与局限</div>
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
  const [sort, setSort] = useState<'date' | 'return'>('date')
  const [horizon, setHorizon] = useState(horizons.includes(10) ? 10 : horizons[0])
  const size = 20
  const events = useJobEvents(job.id, page, sort, horizon, size)
  const total = events.data?.total ?? 0
  return (
    <section className="card">
      <div className="card-title">
        历史案例 <span className="muted">{total.toLocaleString()} 个</span>
        <div className="seg" role="group" aria-label="排序">
          <button aria-pressed={sort === 'date'} onClick={() => { setSort('date'); setPage(0) }}>最近</button>
          {horizons.map(h => (
            <button key={h} aria-pressed={sort === 'return' && horizon === h} onClick={() => { setSort('return'); setHorizon(h); setPage(0) }}>{h} 日收益最高</button>
          ))}
        </div>
      </div>
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
