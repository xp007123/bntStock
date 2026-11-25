import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { type Answer, type AskKind, ApiError, type Judgment, sealJudgment, useAsk } from '../../api/client'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import Verdict from '../../components/Verdict'
import Distribution from '../../components/Distribution'
import Seal from '../../components/Seal'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import { horizonText, optionHorizons, stockHorizons } from './horizons'
import './ask.css'

/** 小四的回答：先结论（大数字 + 一句大白话），再证据，最后可以把判断交给小四保管。 */
export default function AnswerPage() {
  const { kind = 'stock' } = useParams() as { kind: AskKind }
  const [params] = useSearchParams()
  const code = params.get('code') ?? ''
  const horizon = Number(params.get('h') ?? (kind === 'option' ? 63 : 20))
  const feePct = Number(params.get('fee') ?? 0)
  const ask = useAsk(kind, code, horizon, kind === 'option' ? feePct / 100 : undefined)

  if (!code) return <div className="state">请先在“问小四”里选一只股票。<Link to="/">去提问</Link></div>
  if (ask.isError) return <div className="ask-doc"><p className="state error">{ask.error.message}</p><Link to="/" className="muted">换个问题</Link></div>
  if (!ask.data) return <Thinking kind={kind} />
  return <AnswerView a={ask.data} feePct={feePct} />
}

function Thinking({ kind }: { kind: AskKind }) {
  return (
    <div className="ask-doc thinking">
      <HomeResearchPet size={64} />
      <p>小四正在翻 2007 年以来的历史{kind === 'option' ? '，算回本的机会' : '，看类似的走势后来怎样'}……</p>
    </div>
  )
}

function AnswerView({ a, feePct }: { a: Answer; feePct: number }) {
  const navigate = useNavigate()
  const sim = a.analysis.similar
  const option = a.kind === 'option'
  const follow = (h: number, fee?: number) =>
    navigate(`/ask/${a.kind}?code=${a.code}&h=${h}${option ? `&fee=${fee ?? feePct}` : ''}`)
  const horizons = (option ? optionHorizons : stockHorizons).filter(h => h.value !== a.horizon).slice(0, 2)

  return (
    <article className="ask-doc">
      <div className="ask-crumb fade-in"><HomeResearchPet size={34} /><span className="eyebrow">小四 · {option ? '问期权' : '问个股'}</span></div>
      <h1 className="ask-question fade-in">{a.question}</h1>
      <div className="ask-terms fade-in">
        <span>股票<b>{a.name} {displayCode(a.code)}</b></span>
        <span>期限<b>{horizonText(a.horizon)}（{a.horizon} 个交易日）</b></span>
        {option && <span>期权费<b>{(a.fee! * 100).toFixed(1)}%</b><i>100% 平值看涨</i></span>}
        <span>数据截至<b>{a.asof}</b></span>
      </div>

      <Verdict label={a.verdict.label} value={String(a.verdict.value)} dots={a.verdict.dots}
               dotsCaption={<>每 100 个相似的时候里<br />有 <b>{Math.round(a.verdict.dots)} 个</b>{option ? '能回本' : '是涨的'}</>}
               plain={a.verdict.plain} note={a.verdict.note} />

      <div className="ask-facts fade-in">
        {a.facts.map(f => (
          <div key={f.label}><span>{f.label}</span><b className={`num ${trendClass(f.value)}`}>{fmtPct(f.value, 1)}</b><small>{f.note}</small></div>
        ))}
      </div>

      <div className="ask-voice fade-in">
        <HomeResearchPet size={48} />
        <div>
          <p>{a.voice}<small>以上是历史统计，不构成买卖建议。</small></p>
          <div className="ask-follow">
            <span className="eyebrow">接着问</span>
            {horizons.map(h => <button key={h.value} onClick={() => follow(h.value)}>换成{h.label}呢？</button>)}
            {option && [feePct - 1.5, feePct + 1.5].filter(f => f > 0).map(f => (
              <button key={f} onClick={() => follow(a.horizon, Number(f.toFixed(1)))}>期权费 {f.toFixed(1)}% 呢？</button>
            ))}
            {!option && <button onClick={() => navigate(`/ask/option?code=${a.code}&h=63&fee=7.5`)}>它的 3 个月期权呢？</button>}
            <Link to={`/stocks/${a.code}`} className="ask-follow-link">看 K 线 →</Link>
          </div>
        </div>
      </div>

      <section className="ask-section">
        <h2>和现在相似的 {sim.n} 个时候，结果分成{option ? '三' : '两'}种</h2>
        <Distribution stats={sim} line={option ? a.fee! : undefined} lineLabel={option ? `回本线 +${(a.fee! * 100).toFixed(1)}%` : undefined} />
        <p className="ask-compare">
          不挑时候、随便哪天买（{a.analysis.all.n.toLocaleString()} 个起点，{a.analysis.sample_range[0].slice(0, 4)}–{a.analysis.sample_range[1].slice(0, 4)}）：
          {option ? <>回本 <b>{Math.round((a.analysis.all.breakeven_prob ?? 0) * 100)}%</b>，扣费后平均 <b className={trendClass(a.analysis.all.payoff_mean)}>{fmtPct(a.analysis.all.payoff_mean ?? 0, 1)}</b></>
                  : <>在涨 <b>{Math.round(a.analysis.all.up_prob * 100)}%</b>，平均 <b className={trendClass(a.analysis.all.mean)}>{fmtPct(a.analysis.all.mean, 1)}</b></>}
        </p>
      </section>

      <section className="ask-section">
        <h2>证据</h2>
        <ul className="ask-evidence">
          {a.evidence.map(e => <li key={e.role}><b>{e.role}</b><p>{e.text}</p><code>{e.source}</code></li>)}
          {a.pending_evidence.map(p => <li key={p} className="pending"><b>{p.split('（')[0]}</b><p>下一版加入（{p.split('（')[1]?.replace('）', '') ?? ''}）。</p></li>)}
        </ul>
      </section>

      <SealPanel a={a} />

      <p className="ask-method">怎么算的：{a.analysis.method} 数据版本 {a.data_version}。</p>
    </article>
  )
}

function SealPanel({ a }: { a: Answer }) {
  const qc = useQueryClient()
  const [sealed, setSealed] = useState<Judgment | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const seal = async () => {
    setBusy(true); setError('')
    try {
      const j = await sealJudgment({ kind: a.kind, code: a.code, horizon: a.horizon, fee: a.fee ?? undefined })
      setSealed(j); qc.invalidateQueries({ queryKey: ['judgments'] })
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }
  return (
    <section className="ask-keep">
      <div>
        <h3>把这个判断交给小四保管</h3>
        {sealed ? (
          <p>已封存。大约 <b className="serif">{sealed.due_estimate}</b> 揭晓（第 {a.horizon} 个交易日收盘后）。这期间不用盯盘，到时候在 <Link to={`/judgments/${sealed.id}`}>我的判断</Link> 里看结果。</p>
        ) : (
          <>
            <p>封存后不再改动。走满 {a.horizon} 个交易日那天，小四会把实际结果和今天的判断放在一起给你看。</p>
            <button className="btn primary" disabled={busy} onClick={seal}>{busy ? '封存中…' : '封存这个判断'}</button>
            {error && <p className="state error">{error}</p>}
          </>
        )}
      </div>
      <Seal size={88} ghost={!sealed} stamp={!!sealed}>{sealed ? <>已<br />封存</> : <>待<br />封存</>}</Seal>
    </section>
  )
}
