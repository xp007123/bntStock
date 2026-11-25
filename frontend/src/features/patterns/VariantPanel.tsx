import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Minus, Plus, X } from 'lucide-react'
import { ApiError, type Condition, type Job, type Rule, useLibrary, variantJob, type VariantChange } from '../../api/client'
import { conditionText, opText } from './ruleText'
import { extractParams, setParam } from './params'

const OPS = ['>', '>=', '<', '<=', 'cross_up', 'cross_down']

/** 增减一条条件：在原研究基础上去掉或增加一条，作为新研究运行，原研究保留。 */
export default function VariantPanel({ job, onClose }: { job: Job; onClose: () => void }) {
  const navigate = useNavigate()
  const library = useLibrary()
  const [tab, setTab] = useState<string>('')
  const [picked, setPicked] = useState<Condition | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const groups = useMemo(() => {
    const out: { name: string; items: { key: string; name: string; note?: string; condition: Condition }[] }[] = []
    if (!library.data) return out
    for (const cat of library.data.categories) {
      out.push({ name: cat, items: library.data.modules.filter(m => m.category === cat).map(m => ({ key: m.key, name: m.name, note: m.note, condition: m.condition })) })
    }
    out.push({ name: '我的条件', items: library.data.conditions.map(c => ({ key: `my-${c.id}`, name: c.name, condition: c.condition })) })
    return out
  }, [library.data])
  const current = groups.find(g => g.name === tab) ?? groups[0]

  // 用一个只有这条条件的临时规则复用参数提取与写回
  const draft: Rule | null = picked ? { name: 'draft', conditions: [picked] } : null
  const params = draft ? extractParams(draft) : []

  const run = async (change: VariantChange) => {
    setBusy(true); setError('')
    try {
      const next = await variantJob(job.id, change)
      onClose()
      navigate(`/patterns/jobs/${next.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e)); setBusy(false)
    }
  }

  return (
    <section className="card variant">
      <div className="card-title">增减一条条件 <button className="btn" onClick={onClose} aria-label="关闭"><X size={15} /></button></div>
      <p className="muted variant-lede">每次只改一条，结果作为新研究保存，原研究不变；完成后可直接与原研究对比。</p>

      <h3>去掉一条</h3>
      <ol className="cond-list removable">
        {job.rule.conditions.map((c, i) => (
          <li key={i}>
            <b>{c.label}</b><code>{conditionText(c)}</code>
            <button className="btn" disabled={busy || job.rule.conditions.length <= 1} onClick={() => run({ action: 'remove', index: i })}>
              <Minus size={14} />去掉
            </button>
          </li>
        ))}
      </ol>

      <h3>增加一条</h3>
      {library.isLoading ? <div className="state">读取条件库…</div> : (
        <div className="picker">
          <div className="seg picker-tabs" role="tablist">
            {groups.map(g => (
              <button key={g.name} aria-pressed={current?.name === g.name} onClick={() => setTab(g.name)}>
                {g.name}{g.name === '我的条件' ? ` ${g.items.length}` : ''}
              </button>
            ))}
          </div>
          <div className="module-grid">
            {current?.items.length ? current.items.map(m => (
              <button key={m.key} className={`module ${picked && JSON.stringify(picked) === JSON.stringify(m.condition) ? 'on' : ''}`}
                      onClick={() => setPicked(JSON.parse(JSON.stringify(m.condition)))} title={m.note}>
                <b>{m.name}</b><span>{conditionText(m.condition)}</span>
              </button>
            )) : <p className="muted">还没有保存的条件。运行研究时用到的新条件会自动保存在这里。</p>}
          </div>
        </div>
      )}

      {picked && draft && (
        <div className="picked">
          <div className="picked-head">
            <label>名称<input value={picked.label} maxLength={60} onChange={e => setPicked({ ...picked, label: e.target.value })} /></label>
            <label>比较
              <select value={picked.op} onChange={e => setPicked({ ...picked, op: e.target.value })}>
                {OPS.map(o => <option key={o} value={o}>{opText(o)}</option>)}
              </select>
            </label>
          </div>
          <code className="picked-text">{conditionText(picked)}</code>
          {params.length > 0 && (
            <div className="param-grid">
              {params.map(p => (
                <label key={p.path.join('.')}>
                  <span>{p.label.replace(/^[^·]*· /, '')}</span>
                  <input type="number" step={p.kind === 'window' ? 1 : 'any'} value={p.value}
                         onChange={e => {
                           const v = Number(e.target.value)
                           if (e.target.value === '' || !Number.isFinite(v)) return
                           setPicked(setParam(draft, p.path, p.kind === 'window' ? Math.round(v) : v).conditions[0])
                         }} />
                </label>
              ))}
            </div>
          )}
          <button className="btn primary" disabled={busy || !picked.label.trim()} onClick={() => run({ action: 'add', condition: picked })}>
            <Plus size={14} />{busy ? '提交中…' : '增加这条并运行'}
          </button>
        </div>
      )}
      {error && <p className="state error">{error}</p>}
    </section>
  )
}
