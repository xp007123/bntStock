import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { MessageCircle, Play, Shapes, Trash2 } from 'lucide-react'
import { ApiError, removeLibraryItem, submitJob, useJobs, useLibrary, useTemplates } from '../../api/client'
import JobList from './JobList'
import './patterns.css'

/** 形态测试首页：从内置模板创建（小四创建在下一阶段开放）；右侧为研究记录。 */
export default function PatternsPage() {
  const templates = useTemplates()
  const jobs = useJobs()
  const navigate = useNavigate()

  return (
    <div className="pt-layout">
      <section>
        <header className="pt-head">
          <h1>形态测试</h1>
          <p className="muted">把一种日线走势写成条件，扫描 2007 年以来的全市场，看它出现之后股票是涨是跌。</p>
        </header>

        <div className="pt-entries">
          <div className="pt-entry on"><Shapes size={18} /><div><b>从内置模板创建</b><span>选模板、调参数，直接运行</span></div></div>
          <div className="pt-entry off" title="下一阶段开放"><MessageCircle size={18} /><div><b>让小四帮你创建</b><span>说出你的方法，小四翻译成条件（下一阶段）</span></div></div>
        </div>

        {templates.isError ? <div className="card state error">模板读取失败</div> : (
          <div className="tpl-grid">
            {(templates.data?.templates ?? []).map((t, i) => (
              <button key={t.name} className="tpl-card" onClick={() => navigate(`/patterns/new/${i}`)}>
                <b>{t.name}</b>
                <p>{t.description}</p>
                <span className="muted">{t.conditions.length} 个条件 · 同时满足</span>
              </button>
            ))}
          </div>
        )}
        <MyPatterns />
      </section>

      <aside className="card pt-records">
        <div className="card-title">研究记录 <span className="muted">{jobs.data?.length ?? 0} 条</span></div>
        {jobs.data?.length ? <JobList jobs={jobs.data} /> : <p className="muted pt-empty">还没有研究。选一个模板运行后，结果会保存在这里。</p>}
        <Link to="/records" className="muted pt-more">全部研究记录</Link>
      </aside>
    </div>
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
      <h2>我的形态 <span className="muted">{items.length} 套 · 提交研究时自动保存</span></h2>
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
              if (!window.confirm(`从我的形态中删除「${p.name}」？已有研究记录不受影响。`)) return
              qc.setQueryData(['pattern-library'], await removeLibraryItem('patterns', p.id))
            }}><Trash2 size={14} /></button>
          </li>
        ))}
      </ul>
    </section>
  )
}
