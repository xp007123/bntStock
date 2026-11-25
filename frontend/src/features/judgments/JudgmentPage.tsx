import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { type Judgment, useJudgment } from '../../api/client'
import Seal from '../../components/Seal'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import { horizonText } from '../ask/horizons'
import './judgments.css'

/** 一个判断：封存中显示进度；揭晓后把当时的判断和实际结果并排，并把结果放回概率里看。 */
export default function JudgmentPage() {
  const { id = '' } = useParams()
  const q = useJudgment(id)
  if (q.isError) return <div className="state error">判断不存在。<Link to="/judgments">返回我的判断</Link></div>
  if (!q.data) return <div className="state">读取中…</div>
  const j = q.data
  const option = j.kind === 'option'
  return (
    <article className="jd-detail">
      <Link to="/judgments" className="back muted"><ArrowLeft size={15} />我的判断</Link>
      <div className="jd-card">
        <Seal size={78} stamp={j.status === 'settled'}>{j.status === 'settled' ? <>已<br />揭晓</> : <>已<br />封存</>}</Seal>
        <span className="eyebrow">{option ? '问期权' : '问个股'} · {j.asof} 封存 · 数据 {j.data_version}</span>
        <h1>{j.name} <span className="num muted">{displayCode(j.code)}</span></h1>
        <p className="jd-q">{j.question}</p>

        <div className="jd-vs">
          <div>
            <span>当时的判断</span>
            <b className="num">{Math.round(j.prediction.prob * 100)}%</b>
            <small>{option ? '回本概率' : `${horizonText(j.horizon)}后在涨的概率`} · 平时是 {Math.round(j.prediction.base_prob * 100)}%</small>
          </div>
          <div>
            <span>实际结果</span>
            {j.outcome?.done ? (
              <>
                <b className={`num ${trendClass(j.outcome.return)}`}>{fmtPct(j.outcome.return, 1)}</b>
                <small>{option ? (j.outcome.hit ? `超过期权费 ${((j.fee ?? 0) * 100).toFixed(1)}%，回本了` : `没超过期权费 ${((j.fee ?? 0) * 100).toFixed(1)}%，没回本`) : (j.outcome.hit ? '涨了' : '没涨')}
                  {option && j.outcome.payoff != null && <> · 扣费后 {fmtPct(j.outcome.payoff, 1)}</>}</small>
              </>
            ) : (
              <>
                <b className="num muted">?</b>
                <small>已走 {j.prediction.elapsed ?? 0} / {j.horizon} 个交易日 · 约 {j.due_estimate} 揭晓</small>
              </>
            )}
          </div>
        </div>

        {j.outcome?.done && <Path j={j} />}

        <div className="jd-voice">
          <HomeResearchPet size={44} />
          <p>{j.outcome?.done ? reflect(j) : <>封存中。这段时间不用盯盘，涨跌都是过程。到期那天，小四会把结果和当初的判断放在一起给你看。<br /><span className="muted">当时小四说：{j.prediction.voice}</span></>}</p>
        </div>
        <p className="jd-foot muted">
          {j.outcome?.done ? <>{j.outcome.start_date} 收盘 {j.outcome.start_close.toFixed(2)} → {j.outcome.end_date} 收盘 {j.outcome.end_close.toFixed(2)}（不复权价；涨跌按复权计算）。</> : null}
          好结果不代表判断对，坏结果也不代表判断错；看的是很多次以后，概率说得准不准。
        </p>
      </div>
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

function Path({ j }: { j: Judgment }) {
  const pts = j.outcome!.path
  const W = 600, H = 120
  const lo = Math.min(...pts, j.prediction.p10, 0), hi = Math.max(...pts, j.prediction.p90, j.fee ?? 0)
  const x = (i: number) => i / (pts.length - 1) * W
  const y = (v: number) => 8 + (hi - v) / (hi - lo || 1) * (H - 24)
  const last = pts[pts.length - 1]
  return (
    <div className="jd-path">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="封存期间的涨跌路径">
        <rect x={0} y={y(j.prediction.p90)} width={W} height={y(j.prediction.p10) - y(j.prediction.p90)} fill="var(--side)" />
        <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" />
        {j.fee != null && <>
          <line x1={0} x2={W} y1={y(j.fee)} y2={y(j.fee)} stroke="var(--faint)" strokeDasharray="3 3" />
          <text x={4} y={y(j.fee) - 4} className="dist-axis">回本线 +{(j.fee * 100).toFixed(1)}%</text>
        </>}
        <polyline points={pts.map((v, i) => `${x(i)},${y(v)}`).join(' ')} fill="none" stroke="var(--ink)" strokeWidth={1.5} />
        <circle cx={x(pts.length - 1)} cy={y(last)} r={4} fill={last >= 0 ? 'var(--up)' : 'var(--down)'} />
      </svg>
      <p className="muted">灰色带：当时估计的正常范围（运气最差一成到最好一成之间）。</p>
    </div>
  )
}
