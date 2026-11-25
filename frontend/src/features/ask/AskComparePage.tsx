import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, X } from 'lucide-react'
import { type Answer, useAskCompare, useSecurity } from '../../api/client'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import StockSearch from '../../components/StockSearch'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import { useRemember } from '../../lib/recent'
import { horizonText, stockHorizons } from './horizons'
import './ask.css'

/** 两只股票对着问：同一个问题、同一个期限，结论并排。只摆引擎算出来的数，不替用户选。 */
export default function AskComparePage() {
  const [params, setParams] = useSearchParams()
  const a = params.get('a') ?? ''
  const b = params.get('b') ?? ''
  const h = Number(params.get('h') ?? 21)
  const q = useAskCompare(a, b, h)
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }) }
  const c = q.data
  useRemember(c ? { kind: 'compare', to: `/ask/compare?a=${a}&b=${b}&h=${h}`, title: `${c.items[0].name} vs ${c.items[1].name}`, detail: `${horizonText(h)}谁更可能涨` } : null)

  return (
    <article className="ask-doc ask-compare-page">
      <header className="ask-head fade-in">
        <Link to="/" className="back muted"><ArrowLeft size={15} />换个问题</Link>
        <h1 className="ask-question">{c ? c.question : '两只股票，同一个问题，结论并排看'}</h1>
        <div className="ask-terms">
          <span className="tag night">小四 · 两只对比</span>
          <span className="seg" role="group" aria-label="期限">
            {stockHorizons.map(o => <button key={o.value} aria-pressed={h === o.value} onClick={() => set('h', String(o.value))}>{o.label.trim()}</button>)}
          </span>
          {c && <span>数据截至<b>{c.asof}</b></span>}
        </div>
      </header>

      <div className="acmp-pick">
        <Slot code={a} onPick={v => set('a', v)} label="第一只" />
        <span className="acmp-vs">对比</span>
        <Slot code={b} onPick={v => set('b', v)} label="第二只" />
      </div>

      {!a || !b ? <p className="muted acmp-hint">两只都选好，小四用同一套算法、同一个期限分别算，结果放在一起。</p>
        : q.isError ? <div className="ask-blank"><HomeResearchPet size={96} status="error" /><p className="state error">{q.error.message}</p></div>
        : !c ? <div className="ask-blank"><HomeResearchPet size={110} status="researching" /><p>小四正在分别翻两只股票的历史……</p></div>
        : (
          <>
            <div className="acmp-grid stagger">
              {c.items.map(x => <Side key={x.code} x={x} lead={c.lead === x.code} />)}
            </div>
            <section className="ask-voice acmp-voice fade-in">
              <div className="ask-voice-who"><HomeResearchPet size={52} status="idle" /><b>小四说</b></div>
              <p>{c.voice}</p>
              <small>以上是历史统计，不构成买卖建议。“相似的时候”各自按自己的历史找，两只的样本数可能不同。</small>
            </section>
          </>
        )}
    </article>
  )
}

function Slot({ code, onPick, label }: { code: string; onPick: (c: string) => void; label: string }) {
  const sec = useSecurity(code || 'sh600519')
  return (
    <div className="acmp-slot">
      <span className="eyebrow">{label}</span>
      {code ? (
        <span className="ask-chip"><b>{sec.data?.name ?? '…'}</b><span className="num">{displayCode(code)}</span>
          <button aria-label="换一只" onClick={() => onPick('')}><X size={14} /></button></span>
      ) : <StockSearch onPick={onPick} />}
    </div>
  )
}

function Side({ x, lead }: { x: Answer; lead: boolean }) {
  const navigate = useNavigate()
  const s = x.analysis.similar, all = x.analysis.all
  return (
    <section className={`card acmp-side ${lead ? 'lead' : ''}`}>
      <header>
        <b>{x.name}</b><span className="muted num">{displayCode(x.code)}</span>
        {lead && <span className="tag">在涨的比例更高</span>}
      </header>
      <div className="acmp-big"><b className="num">{Math.round(s.up_prob * 100)}<small>%</small></b>
        <span>{horizonText(x.horizon)}后在涨的比例<br />（和它现在相似的 {s.n} 个时候）</span></div>
      <div className="progress" aria-hidden="true"><i style={{ width: `${s.up_prob * 100}%` }} /></div>
      <dl>
        <div><dt>它平时（随便哪天买）</dt><dd className="num">{Math.round(all.up_prob * 100)}%</dd></div>
        <div><dt>平均下来</dt><dd className={`num ${trendClass(s.mean)}`}>{fmtPct(s.mean, 1)}</dd></div>
        <div><dt>运气最差的十分之一</dt><dd className={`num ${trendClass(s.p10)}`}>{fmtPct(s.p10, 1)}</dd></div>
        <div><dt>运气最好的十分之一</dt><dd className={`num ${trendClass(s.p90)}`}>{fmtPct(s.p90, 1)}</dd></div>
      </dl>
      <button className="ask-follow-link" onClick={() => navigate(`/ask/stock?code=${x.code}&h=${x.horizon}`)}>看它的完整回答<ArrowUpRight size={14} /></button>
    </section>
  )
}
