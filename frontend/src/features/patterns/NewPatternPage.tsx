import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Play } from 'lucide-react'
import { type Rule, submitJob, useTemplates } from '../../api/client'
import { conditionText } from './ruleText'
import { extractParams, setParam } from './params'
import './patterns.css'

const HORIZONS = [1, 3, 5, 10, 20, 60]

/** 从模板创建：看清每个条件，调整数字，选择观察周期后运行。 */
export default function NewPatternPage() {
  const { index = '0' } = useParams()
  const navigate = useNavigate()
  const templates = useTemplates()
  const template = templates.data?.templates[Number(index)]
  const [edited, setEdited] = useState<Rule | null>(null)
  const [horizons, setHorizons] = useState<number[]>([1, 3, 5, 10, 20])
  const [cooldown, setCooldown] = useState(10)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const rule = edited ?? template
  const params = useMemo(() => (rule ? extractParams(rule) : []), [rule])
  if (templates.isLoading) return <div className="state">读取模板…</div>
  if (!template || !rule) return <div className="card state error">模板不存在。<Link to="/patterns">返回方法库</Link></div>

  const changed = edited !== null && JSON.stringify(edited.conditions) !== JSON.stringify(template.conditions)
  const run = async () => {
    setBusy(true); setError('')
    try {
      const job = await submitJob({
        ...rule, name: changed ? `${template.name}（调整）` : template.name,
        horizons: [...horizons].sort((a, b) => a - b), cooldown,
      })
      navigate(`/patterns/jobs/${job.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e)); setBusy(false)
    }
  }

  return (
    <div className="pt-new">
      <Link to="/patterns" className="back muted"><ArrowLeft size={15} />方法库</Link>
      <header className="pt-head">
        <h1>{template.name}{changed && <span className="tag">已调整</span>}</h1>
        <p className="muted">{template.description}</p>
      </header>

      <section className="card">
        <div className="card-title">实际条件 <span className="muted">全部同时满足才算出现；均按收盘后的日线判定</span></div>
        <ol className="cond-list">
          {rule.conditions.map((c, i) => (
            <li key={i}><b>{c.label}</b><code>{conditionText(c)}</code></li>
          ))}
        </ol>
      </section>

      <section className="card">
        <div className="card-title">调整参数 {changed && <button className="btn" onClick={() => setEdited(null)}>恢复模板</button>}</div>
        <div className="param-grid">
          {params.map(p => (
            <label key={p.path.join('.')}>
              <span>{p.label}</span>
              <input type="number" step={p.kind === 'window' ? 1 : 'any'} min={p.kind === 'window' ? 1 : undefined} max={p.kind === 'window' ? 500 : undefined}
                     value={p.value}
                     onChange={e => {
                       const v = e.target.value === '' ? NaN : Number(e.target.value)
                       if (!Number.isFinite(v)) return
                       setEdited(setParam(rule, p.path, p.kind === 'window' ? Math.round(v) : v))
                     }} />
            </label>
          ))}
        </div>
        <div className="settings">
          <div>
            <span className="muted">观察周期（交易日）</span>
            <div className="seg" role="group" aria-label="观察周期">
              {HORIZONS.map(h => (
                <button key={h} aria-pressed={horizons.includes(h)}
                        onClick={() => setHorizons(hs => hs.includes(h) ? (hs.length > 1 ? hs.filter(x => x !== h) : hs) : [...hs, h])}>{h} 日</button>
              ))}
            </div>
          </div>
          <label>
            <span className="muted">同一只股票的冷却期（根）</span>
            <input type="number" min={0} max={250} value={cooldown} onChange={e => setCooldown(Math.max(0, Math.min(250, Math.round(Number(e.target.value) || 0))))} />
          </label>
        </div>
      </section>

      <div className="run-bar">
        <p className="muted">统计区间：2007-01-01 至数据末日；排除 ST、退市和次日开盘涨停买不进的情况；上市不足 250 根 K 线的不计入。</p>
        <button className="btn primary" disabled={busy} onClick={run}><Play size={15} />{busy ? '提交中…' : '运行选股与历史验证'}</button>
      </div>
      {error && <p className="state error">{error}</p>}
    </div>
  )
}
