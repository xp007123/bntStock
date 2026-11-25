import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Play, SlidersHorizontal, Trash2 } from 'lucide-react'
import { ApiError, type Method, removeLibraryItem, submitJob, useJobs, useLibrary, useMethods } from '../../api/client'
import SubNav, { METHOD_TABS } from '../../components/SubNav'
import JobList from './JobList'
import { patternVerdict } from './verdict'
import './patterns.css'

const TONE = { good: '比随便买略好', same: '和随便买差不多', bad: '比随便买还差' } as const

/**
 * 方法库：大家常说的几种买法，小四已经按默认参数翻过全市场的历史，点开就有结论。
 * 想按自己的习惯改参数，再从卡片上的“调参数自己算”进去。
 */
export default function PatternsPage() {
  const methods = useMethods()
  const jobs = useJobs()
  const list = methods.data?.methods ?? []
  const computing = list.filter(m => m.status === 'queued' || m.status === 'running').length

  return (
    <div className="pt-layout">
      <section>
        <SubNav items={METHOD_TABS} />
        <header className="pt-head">
          <h1>方法库</h1>
          <p className="muted">大家常说的几种买法，到底灵不灵？小四已经按默认参数翻过 2007 年以来的全市场，点开就有结论。想按你自己的习惯改，就调参数再算一遍。</p>
        </header>

        {computing > 0 && <p className="lineage">行情更新后，小四正在重新算 {computing} 种方法，算完会自动显示。全市场扫一遍大约要半分钟一种。</p>}

        {methods.isError ? <div className="card state error">方法库读取失败</div> : methods.isLoading ? <div className="state">读取方法库…</div> : (
          <div className="tpl-grid stagger">{list.map(m => <MethodCard key={m.index} m={m} />)}</div>
        )}
        <MyPatterns />
      </section>

      <aside className="card pt-records">
        <div className="card-title">我验证过的 <span className="muted">{jobs.data?.length ?? 0} 条</span></div>
        {jobs.data?.length ? <JobList jobs={jobs.data.slice(0, 6)} /> : <p className="muted pt-empty">还没有自己验证过的方法。调过参数再算的结果会保存在这里。</p>}
        <Link to="/records" className="muted pt-more">全部</Link>
      </aside>
    </div>
  )
}

function MethodCard({ m }: { m: Method }) {
  const v = m.status === 'completed' && m.summary && m.years ? patternVerdict(m.summary, m.years) : null
  const active = m.status === 'queued' || m.status === 'running'
  return (
    <article className="tpl-card">
      <Link className="tpl-main" to={m.status === 'completed' && m.job ? `/patterns/jobs/${m.job}` : `/patterns/new/${m.index}`}>
        <b>{m.name}</b>
        <p>{m.description}</p>
        {v ? (
          <div className="tpl-verdict">
            <strong className="num">{v.value}<i>%</i></strong>
            <div><span>出现后 {v.horizon} 天在涨的比例</span><em className={`tag ${v.tone === 'good' ? '' : 'plain'}`}>{TONE[v.tone]}</em></div>
          </div>
        ) : active ? (
          <div className="tpl-wait"><div className="progress live"><i style={{ width: `${Math.max(4, m.progress ?? 0)}%` }} /></div><span className="muted">{m.status === 'queued' ? '排队中，马上开始算' : `小四正在算… ${Math.round(m.progress ?? 0)}%`}</span></div>
        ) : m.status === 'completed' ? (
          <p className="muted tpl-none">历史上出现的次数太少，算不出结论。</p>
        ) : (
          <p className="muted tpl-none">这次没算出来{m.message ? `：${m.message}` : ''}。可以调参数自己算。</p>
        )}
      </Link>
      <footer>
        <span className="muted">{m.conditions} 个条件{m.events != null && <> · 历史上出现 {m.events.toLocaleString()} 次</>}{m.selected != null && <> · 今天 {m.selected} 只</>}</span>
        <Link to={`/patterns/new/${m.index}`} className="tpl-tune"><SlidersHorizontal size={13} />调参数自己算</Link>
      </footer>
      {v && <ArrowRight size={16} className="tpl-go" />}
    </article>
  )
}

/** 我的形态：提交过的整套规则自动保存，可一键用最新数据再运行。 */
function MyPatterns() {
  const library = useLibrary()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const items = library.data?.patterns ?? []
  if (!items.length) return null
  return (
    <section className="my-patterns">
      <h2>我调过的方法 <span className="muted">{items.length} 套 · 算过就自动保存</span></h2>
      {error && <p className="state error">{error}</p>}
      <ul>
        {items.map(p => (
          <li key={p.id}>
            <div><b>{p.name}</b><span className="muted">{p.rule.conditions.length} 个条件 · 最近 {p.updated_at.slice(0, 10)}</span></div>
            {p.last_job && <Link className="muted" to={`/patterns/jobs/${p.last_job}`}>上次结果</Link>}
            <button className="btn" onClick={async () => {
              setError('')
              try { navigate(`/patterns/jobs/${(await submitJob(p.rule)).id}`) } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
            }}><Play size={14} />运行</button>
            <button className="btn" aria-label={`删除 ${p.name}`} onClick={async () => {
              if (!window.confirm(`从我调过的方法中删除「${p.name}」？已有的结果不受影响。`)) return
              qc.setQueryData(['pattern-library'], await removeLibraryItem('patterns', p.id))
            }}><Trash2 size={14} /></button>
          </li>
        ))}
      </ul>
    </section>
  )
}
