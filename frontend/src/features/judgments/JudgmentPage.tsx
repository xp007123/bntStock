import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Check, RotateCcw, Share2, X } from 'lucide-react'
import { type Judgment, useJudgment } from '../../api/client'
import Seal from '../../components/Seal'
import ShareCard from '../../components/ShareCard'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import { isRevealed, markRevealed, motionOff } from '../../lib/motion'
import { leanText, mineRight, stanceText, xiaosiRight } from '../../lib/stance'
import { horizonText } from '../ask/horizons'
import './judgments.css'

/** 一个判断：左边墨黑卡是“当时的判断”，右边是“实际结果”；封存中显示进度，揭晓后把结果放回概率里看。 */
export default function JudgmentPage() {
  const { id = '' } = useParams()
  const q = useJudgment(id)
  if (q.isError) return <div className="state error">判断不存在。<Link to="/judgments">返回我的判断</Link></div>
  if (!q.data) return <div className="state">读取中…</div>
  return <Detail key={q.data.id} j={q.data} />
}

/**
 * 揭晓的过程（第一次打开已到期的判断时播放一次，之后直接看结果，可以手动再看一遍）：
 * wait  结果还盖着斜纹封条，停一下；
 * draw  走势线从封存那天一天一天画到到期日，画在“当时估计的正常范围”里；
 * open  封条从左到右揭开，露出真实涨跌；印章从“已封存”翻成“已揭晓”，小四眨一下眼。
 * 画的是真实路径，不做从 0 滚到结果的假数字。
 */
type Stage = 'wait' | 'draw' | 'open'
const WAIT = 700, DRAW = 1900

function Detail({ j }: { j: Judgment }) {
  const option = j.kind === 'option'
  const done = !!j.outcome?.done
  const elapsed = j.prediction.elapsed ?? 0
  const [run, setRun] = useState(0)
  const fresh = () => done && !motionOff() && (run > 0 || !isRevealed(j.id))
  const [stage, setStage] = useState<Stage>(() => (fresh() ? 'wait' : 'open'))
  const [face, setFace] = useState<'sealed' | 'settled'>(() => (!done || fresh() ? 'sealed' : 'settled'))
  const [flip, setFlip] = useState(false)
  const [sharing, setSharing] = useState(false)
  const mine = stanceText(j.prediction.stance, option)
  const iWasRight = mineRight(j), xiaosiWasRight = xiaosiRight(j)

  useEffect(() => {
    if (!done) return
    if (!fresh()) { markRevealed(j.id); setStage('open'); setFace('settled'); return }
    setStage('wait'); setFace('sealed'); setFlip(false)
    const timers = [
      window.setTimeout(() => setStage('draw'), WAIT),
      window.setTimeout(() => { setStage('open'); setFlip(true); markRevealed(j.id) }, WAIT + DRAW),
      window.setTimeout(() => setFace('settled'), WAIT + DRAW + 250),
      window.setTimeout(() => setFlip(false), WAIT + DRAW + 2200),
    ]
    return () => timers.forEach(window.clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j.id, done, run])

  const open = stage === 'open'
  return (
    <article className="jd-detail">
      <Link to="/judgments" className="back muted"><ArrowLeft size={15} />我的判断</Link>
      <header className="jd-top fade-in">
        <div>
          <div className="jd-tags">
            <span className="tag night">{option ? '问期权' : '问个股'}</span>
            <span className="tag plain">{j.asof} 封存</span>
            <span className="tag plain">数据 {j.data_version}</span>
          </div>
          <h1>{j.name} <span className="num muted">{displayCode(j.code)}</span></h1>
          <p className="jd-q">{j.question}</p>
        </div>
        <Seal size={84} className={flip ? 'flip' : ''}>{face === 'settled' ? <>已<br />揭晓</> : <>已<br />封存</>}</Seal>
      </header>

      <div className="jd-vs stagger">
        <div className="jd-then">
          <span>当时的判断</span>
          <b className="num">{Math.round(j.prediction.prob * 100)}<i>%</i></b>
          <small>{option ? '回本概率' : `${horizonText(j.horizon)}后在涨的概率`} · 平时是 {Math.round(j.prediction.base_prob * 100)}%</small>
        </div>
        {done && j.outcome ? (
          <div className={`jd-now ${open ? '' : 'covered'}`}>
            <span>实际结果</span>
            <b className={`num ${trendClass(j.outcome.return)}`}>{fmtPct(j.outcome.return, 1)}</b>
            <small>{option ? (j.outcome.hit ? `超过期权费 ${((j.fee ?? 0) * 100).toFixed(1)}%，回本了` : `没超过期权费 ${((j.fee ?? 0) * 100).toFixed(1)}%，没回本`) : (j.outcome.hit ? '涨了' : '没涨')}
              {option && j.outcome.payoff != null && <> · 扣费后 {fmtPct(j.outcome.payoff, 1)}</>}</small>
            <div className="jd-cover" aria-hidden="true">
              <span>实际结果</span>
              <b className="num">?</b>
              <small>{stage === 'wait' ? '到期了，马上揭晓' : `第 1 天 → 第 ${j.horizon} 天`}</small>
            </div>
          </div>
        ) : (
          <div className="jd-now waiting">
            <span>实际结果</span>
            <b className="num">?</b>
            <div className="progress live" aria-label={`已走 ${elapsed} / ${j.horizon} 个交易日`}><i style={{ width: `${Math.min(100, elapsed / j.horizon * 100)}%` }} /></div>
            <small>已走 {elapsed} / {j.horizon} 个交易日 · 约 {j.due_estimate} 揭晓</small>
          </div>
        )}
      </div>

      {/* 你、小四、实际结果：三方对照。对错只在揭晓之后显示 */}
      <div className="jd-views">
        <div>
          <span>你当时的看法</span>
          <b>{mine ?? '没有表态'}</b>
          {open && iWasRight != null && <em className={iWasRight ? 'ok' : 'no'}>{iWasRight ? <Check size={13} /> : <X size={13} />}{iWasRight ? '说对了' : '这次没说对'}</em>}
          {open && done && j.prediction.stance === 'follow' && <em className="plain">跟小四一起</em>}
        </div>
        <div>
          <span>小四的倾向</span>
          <b>{leanText(j.prediction.prob, option)}</b>
          {open && xiaosiWasRight != null && <em className={xiaosiWasRight ? 'ok' : 'no'}>{xiaosiWasRight ? <Check size={13} /> : <X size={13} />}{xiaosiWasRight ? '和结果一致' : '和结果相反'}</em>}
        </div>
      </div>

      {done && (
        <section className="card">
          <div className="card-title">封存期间是怎么走的
            {open && <button className="jd-replay" onClick={() => setRun(r => r + 1)}><RotateCcw size={13} />再看一遍揭晓</button>}
          </div>
          <Path j={j} stage={stage} />
        </section>
      )}

      <section className="jd-voice card">
        <HomeResearchPet size={52} status={!done ? 'idle' : open ? (flip ? 'complete' : 'idle') : 'researching'} />
        {!done ? <p>封存中。这段时间不用盯盘，涨跌都是过程。到期那天，小四会把结果和当初的判断放在一起给你看。<span className="muted">当时小四说：{j.prediction.voice}</span></p>
          : open ? <p key="open" className="fade-in">{reflect(j)}</p>
          : <p key="wait">到期了。小四把封存以来每一天的走势画给你看，画完就揭晓。</p>}
      </section>
      <p className="jd-foot muted">
        {done && open && j.outcome ? <>{j.outcome.start_date} 收盘 {j.outcome.start_close.toFixed(2)} → {j.outcome.end_date} 收盘 {j.outcome.end_close.toFixed(2)}（不复权价；涨跌按复权计算）。</> : null}
        好结果不代表判断对，坏结果也不代表判断错；看的是很多次以后，概率说得准不准。
      </p>
      {(!done || open) && (
        <div className="jd-actions">
          <button className="btn" onClick={() => setSharing(true)}><Share2 size={15} />生成分享卡</button>
        </div>
      )}
      {sharing && <ShareCard j={j} onClose={() => setSharing(false)} />}
    </article>
  )
}

function reflect(j: Judgment) {
  const o = j.outcome!
  const p = j.prediction.prob
  const likely = p >= 0.5
  const happened = o.hit
  const head = happened === likely ? '这次的结果和多数情况一致。' : `这次落在了那${happened ? '少数' : '较少见'}的${Math.round((happened ? p : 1 - p) * 100)}%里。`
  return `${head}实际涨跌${o.position}。${j.kind === 'option' ? '期权的结果很依赖少数大涨，单次回本或亏掉期权费都很正常。' : ''}把它放进档案，看长期。`
}

function Path({ j, stage }: { j: Judgment; stage: Stage }) {
  const pts = j.outcome!.path
  const W = 600, H = 120
  const lo = Math.min(...pts, j.prediction.p10, 0), hi = Math.max(...pts, j.prediction.p90, j.fee ?? 0)
  const x = (i: number) => i / (pts.length - 1) * W
  const y = (v: number) => 8 + (hi - v) / (hi - lo || 1) * (H - 24)
  const last = pts[pts.length - 1]
  return (
    <div className={`jd-path stage-${stage}`}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="封存期间的涨跌路径">
        <rect x={0} y={y(j.prediction.p90)} width={W} height={y(j.prediction.p10) - y(j.prediction.p90)} rx={8} fill="var(--accent-softer)" />
        <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" />
        {j.fee != null && <>
          <line x1={0} x2={W} y1={y(j.fee)} y2={y(j.fee)} stroke="var(--ink)" strokeDasharray="4 4" />
          <text x={4} y={y(j.fee) - 4} className="dist-axis">回本线 +{(j.fee * 100).toFixed(1)}%</text>
        </>}
        <polyline className="jd-line" pathLength={1} points={pts.map((v, i) => `${x(i)},${y(v)}`).join(' ')} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round"
                  style={{ transitionDuration: stage === 'draw' ? `${DRAW}ms` : '0ms' }} />
        <circle className="jd-end" cx={x(pts.length - 1)} cy={y(last)} r={5} fill={last >= 0 ? 'var(--up)' : 'var(--down)'} stroke="var(--surface)" strokeWidth={2} />
      </svg>
      <p className="muted">浅橙色带：当时估计的正常范围（运气最差一成到最好一成之间）。</p>
    </div>
  )
}
