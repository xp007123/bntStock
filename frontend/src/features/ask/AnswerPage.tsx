import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowUpRight } from 'lucide-react'
import { type Answer, type AskKind, ApiError, type Judgment, sealJudgment, useAsk } from '../../api/client'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import type { PetStatus } from '../../components/xiaosi/ResearchPet'
import Verdict from '../../components/Verdict'
import Distribution from '../../components/Distribution'
import Seal from '../../components/Seal'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import { motionOff, useRolling } from '../../lib/motion'
import { horizonText, optionHorizons, stockHorizons } from './horizons'
import './ask.css'

/** 小四的回答：先结论（大数字 + 一句大白话），再证据；右边一直能看到小四的话和“封存”。 */
export default function AnswerPage() {
  const { kind = 'stock' } = useParams() as { kind: AskKind }
  const [params] = useSearchParams()
  const code = params.get('code') ?? ''
  const horizon = Number(params.get('h') ?? (kind === 'option' ? 63 : 20))
  const feePct = Number(params.get('fee') ?? 0)
  const ask = useAsk(kind, code, horizon, kind === 'option' ? feePct / 100 : undefined)

  // “接着问”同一只股票时，先留着上一个回答，新结果到了再把数字滚过去，而不是整页清空重来
  const last = useRef<Answer | null>(null)
  if (ask.data) last.current = ask.data
  const kept = !ask.data && !ask.isError && last.current?.kind === kind && last.current.code === code ? last.current : null

  if (!code) return <div className="state">请先在“问小四”里选一只股票。<Link to="/">去提问</Link></div>
  if (ask.isError) return (
    <div className="ask-blank">
      <HomeResearchPet size={96} status="error" />
      <p className="state error">{ask.error.message}</p>
      <Link to="/" className="btn">换个问题</Link>
    </div>
  )
  const a = ask.data ?? kept
  if (!a) return <Thinking kind={kind} />
  return <AnswerView a={a} feePct={feePct} pending={!ask.data} />
}

/** 等待时说的是小四真的在做的事（见“怎么算的”），不是假的进度。 */
function Thinking({ kind }: { kind: AskKind }) {
  const steps = ['翻 2007 年以来的每一个交易日', '找出和现在最像的那些时候', kind === 'option' ? '数一数后来有多少次能回本' : '数一数后来有多少次是涨的']
  const [i, setI] = useState(0)
  useEffect(() => { const t = window.setInterval(() => setI(v => (v + 1) % steps.length), 1500); return () => window.clearInterval(t) }, [steps.length])
  return (
    <div className="ask-blank">
      <HomeResearchPet size={120} status="researching" />
      <p>小四正在<span key={i} className="ask-step">{steps[i]}</span>……</p>
    </div>
  )
}

function Fact({ label, value, note }: { label: string; value: number; note: string }) {
  const shown = useRolling(value)
  return <div><span>{label}</span><b className={`num ${trendClass(value)}`}>{fmtPct(shown, 1)}</b><small>{note}</small></div>
}

function AnswerView({ a, feePct, pending }: { a: Answer; feePct: number; pending: boolean }) {
  const navigate = useNavigate()
  const [cheer, setCheer] = useState(false)
  const sim = a.analysis.similar
  const option = a.kind === 'option'
  const follow = (h: number, fee?: number) =>
    navigate(`/ask/${a.kind}?code=${a.code}&h=${h}${option ? `&fee=${fee ?? feePct}` : ''}`)
  const horizons = (option ? optionHorizons : stockHorizons).filter(h => h.value !== a.horizon).slice(0, 2)
  const pet: PetStatus = pending ? 'thinking' : cheer ? 'complete' : 'idle'
  const sealedNow = () => { setCheer(true); window.setTimeout(() => setCheer(false), 1800) }

  return (
    <article className="ask-doc">
      <header className="ask-head fade-in">
        <Link to="/" className="back muted"><ArrowLeft size={15} />换个问题</Link>
        <h1 className="ask-question">{a.question}</h1>
        <div className="ask-terms">
          <span className="tag night">小四 · {option ? '问期权' : '问个股'}</span>
          <span>股票<b>{a.name} {displayCode(a.code)}</b></span>
          <span>期限<b>{horizonText(a.horizon)}（{a.horizon} 个交易日）</b></span>
          {option && <span>期权费<b>{(a.fee! * 100).toFixed(1)}%</b><i>100% 平值看涨</i></span>}
          <span>数据截至<b>{a.asof}</b></span>
        </div>
      </header>

      <div className="ask-grid">
        <div className="ask-main stagger">
          <Verdict label={a.verdict.label} value={String(a.verdict.value)} dots={a.verdict.dots} pending={pending}
                   dotsCaption={<>每 100 个相似的时候里<br />有 <b>{Math.round(a.verdict.dots)} 个</b>{option ? '能回本' : '是涨的'}</>}
                   plain={a.verdict.plain} note={a.verdict.note} />

          <div className={`ask-facts ${pending ? 'pending' : ''}`}>
            {a.facts.map(f => <Fact key={f.label} {...f} />)}
          </div>

          <section className={`card ask-section ${pending ? 'pending' : ''}`}>
            <h2>和现在相似的 {sim.n} 个时候，结果分成{option ? '三' : '两'}种</h2>
            <Distribution key={`${a.horizon}-${a.fee}`} stats={sim} line={option ? a.fee! : undefined} lineLabel={option ? `回本线 +${(a.fee! * 100).toFixed(1)}%` : undefined} />
            <p className="ask-compare">
              <span className="tag plain">对照</span>
              不挑时候、随便哪天买（{a.analysis.all.n.toLocaleString()} 个起点，{a.analysis.sample_range[0].slice(0, 4)}–{a.analysis.sample_range[1].slice(0, 4)}）：
              {option ? <>回本 <b>{Math.round((a.analysis.all.breakeven_prob ?? 0) * 100)}%</b>，扣费后平均 <b className={trendClass(a.analysis.all.payoff_mean)}>{fmtPct(a.analysis.all.payoff_mean ?? 0, 1)}</b></>
                      : <>在涨 <b>{Math.round(a.analysis.all.up_prob * 100)}%</b>，平均 <b className={trendClass(a.analysis.all.mean)}>{fmtPct(a.analysis.all.mean, 1)}</b></>}
            </p>
          </section>

          <section className="card ask-section">
            <h2>证据</h2>
            <ul className="ask-evidence">
              {a.evidence.map(e => <li key={e.role}><b>{e.role}</b><p>{e.text}</p><code>{e.source}</code></li>)}
              {a.pending_evidence.map(p => <li key={p} className="pending"><b>{p.split('（')[0]}</b><p>下一版加入（{p.split('（')[1]?.replace('）', '') ?? ''}）。</p></li>)}
            </ul>
          </section>

          <p className="ask-method">怎么算的：{a.analysis.method} 数据版本 {a.data_version}。</p>
        </div>

        <aside className="ask-rail stagger">
          <section className="ask-voice">
            <div className="ask-voice-who"><HomeResearchPet size={52} status={pet} /><b>{pending ? '小四在重新算…' : '小四说'}</b></div>
            <p className={pending ? 'pending' : ''}>{a.voice}</p>
            <small>以上是历史统计，不构成买卖建议。</small>
            <div className="ask-follow">
              <span className="eyebrow">接着问</span>
              {horizons.map(h => <button key={h.value} disabled={pending} onClick={() => follow(h.value)}>换成{h.label}呢？</button>)}
              {option && [feePct - 1.5, feePct + 1.5].filter(f => f > 0).map(f => (
                <button key={f} disabled={pending} onClick={() => follow(a.horizon, Number(f.toFixed(1)))}>期权费 {f.toFixed(1)}% 呢？</button>
              ))}
              {!option && <button disabled={pending} onClick={() => navigate(`/ask/option?code=${a.code}&h=63&fee=7.5`)}>它的 3 个月期权呢？</button>}
              <Link to={`/stocks/${a.code}`} className="ask-follow-link">看 K 线<ArrowUpRight size={14} /></Link>
            </div>
          </section>

          <SealPanel key={`${a.kind}-${a.code}-${a.horizon}-${a.fee}`} a={a} disabled={pending} onSealed={sealedNow} />
        </aside>
      </div>
    </article>
  )
}

/**
 * 封存：服务端确认封存成功后，按钮收成一块橙色飞到右上角，变成印章盖下去，卡片跟着一沉。
 * 用户看到的是“我的判断被收走保管了”。动效只在真的封存成功后播放。
 */
function SealPanel({ a, disabled, onSealed }: { a: Answer; disabled: boolean; onSealed: () => void }) {
  const qc = useQueryClient()
  const [sealed, setSealed] = useState<Judgment | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const panel = useRef<HTMLElement>(null)
  const button = useRef<HTMLButtonElement>(null)

  const land = (j: Judgment) => {
    setSealed(j)
    onSealed()
    qc.invalidateQueries({ queryKey: ['judgments'] })
    if (!motionOff()) panel.current?.animate(
      [{ transform: 'translateY(0)' }, { transform: 'translateY(4px)' }, { transform: 'translateY(0)' }],
      { duration: 260, delay: 230, easing: 'cubic-bezier(.2,.7,.2,1)' })
  }

  const fly = (j: Judgment) => {
    const from = button.current?.getBoundingClientRect()
    const to = panel.current?.querySelector('.seal')?.getBoundingClientRect()
    if (!from || !to || motionOff()) return land(j)
    const dot = document.createElement('i')
    dot.className = 'seal-flyer'
    Object.assign(dot.style, { left: `${from.left}px`, top: `${from.top}px`, width: `${from.width}px`, height: `${from.height}px` })
    document.body.appendChild(dot)
    button.current!.style.visibility = 'hidden'
    const done = () => { dot.remove(); land(j) }
    dot.animate([
      { left: `${from.left}px`, top: `${from.top}px`, width: `${from.width}px`, height: `${from.height}px`, borderRadius: '999px', transform: 'rotate(0deg) scale(1)' },
      { left: `${from.left + from.width / 2 - 28}px`, top: `${from.top - 6}px`, width: '56px', height: '56px', borderRadius: '28px', transform: 'rotate(0deg) scale(1)', offset: .38 },
      { left: `${to.left}px`, top: `${to.top}px`, width: `${to.width}px`, height: `${to.height}px`, borderRadius: '28%', transform: 'rotate(-8deg) scale(1.5)' },
    ], { duration: 620, easing: 'cubic-bezier(.5,0,.2,1)', fill: 'forwards' }).finished.then(done, done)
  }

  const seal = async () => {
    setBusy(true); setError('')
    try {
      fly(await sealJudgment({ kind: a.kind, code: a.code, horizon: a.horizon, fee: a.fee ?? undefined }))
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }
  return (
    <section ref={panel} className={`ask-keep ${sealed ? 'done' : ''}`}>
      <Seal size={72} ghost={!sealed} stamp={!!sealed}>{sealed ? <>已<br />封存</> : <>待<br />封存</>}</Seal>
      <h3>把这个判断交给小四保管</h3>
      {sealed ? (
        <div className="ask-kept fade-in">
          <p>已封存。大约 <b>{sealed.due_estimate}</b> 揭晓（第 {a.horizon} 个交易日收盘后）。这期间不用盯盘。</p>
          <Link to={`/judgments/${sealed.id}`} className="btn dark lg">去我的判断里看</Link>
        </div>
      ) : (
        <>
          <p>封存后不再改动。走满 {a.horizon} 个交易日那天，小四会把实际结果和今天的判断放在一起给你看。</p>
          <button ref={button} className="btn primary lg" disabled={busy || disabled} onClick={seal}>{busy ? '封存中…' : '封存这个判断'}</button>
          {error && <p className="ask-keep-error">{error}</p>}
        </>
      )}
    </section>
  )
}
