import { Link } from 'react-router-dom'
import { type Judgment, useJudgments } from '../../api/client'
import Seal from '../../components/Seal'
import { displayCode, fmtPct, trendClass } from '../../lib/format'
import { horizonText } from '../ask/horizons'
import './judgments.css'

/** 我的判断：封存中的判断不用盯，到期自动揭晓；已揭晓的放进档案。 */
export default function JudgmentsPage() {
  const q = useJudgments()
  const items = q.data?.items ?? []
  const sealed = items.filter(j => j.status === 'sealed')
  const settled = items.filter(j => j.status === 'settled')
  const rec = q.data?.record

  return (
    <div className="jd">
      <header className="jd-head">
        <h1>我的判断</h1>
        <p className="muted">交给小四保管的判断。封存后不再改动，走满期限那天自动揭晓，和当初的判断放在一起看。</p>
      </header>

      {rec && rec.settled > 0 && (
        <section className="jd-record">
          <div><span>已揭晓</span><b className="num">{rec.settled} 次</b></div>
          <div><span>当时平均给出的概率</span><b className="num">{Math.round((rec.expected_rate ?? 0) * 100)}%</b></div>
          <div><span>实际成真</span><b className="num">{Math.round((rec.hit_rate ?? 0) * 100)}%</b><small>{rec.hits} 次</small></div>
          <p>次数多了以后，这两个数字越接近，说明小四给的概率越靠谱。单次的好坏说明不了什么。</p>
        </section>
      )}

      {q.isLoading ? <div className="state">读取中…</div> : items.length === 0 ? (
        <section className="jd-empty">
          <Seal size={72} ghost>待<br />封存</Seal>
          <div>
            <h2>还没有判断</h2>
            <p className="muted">在“问小四”里问一只股票或一个期权，看完结论后点“封存这个判断”，小四会替你保管到揭晓那天。</p>
            <Link to="/" className="btn primary">去问小四</Link>
          </div>
        </section>
      ) : (
        <>
          {sealed.length > 0 && <List title="封存中" items={sealed} />}
          {settled.length > 0 && <List title="已揭晓" items={settled} />}
        </>
      )}
    </div>
  )
}

function List({ title, items }: { title: string; items: Judgment[] }) {
  return (
    <section className="jd-list">
      <h2>{title} <span className="muted">{items.length}</span></h2>
      <ul>{items.map(j => <Row key={j.id} j={j} />)}</ul>
    </section>
  )
}

function Row({ j }: { j: Judgment }) {
  const elapsed = j.prediction.elapsed ?? 0
  const o = j.outcome
  return (
    <li>
      <Link to={`/judgments/${j.id}`}>
        <div className="jd-main">
          <span className="eyebrow">{j.kind === 'option' ? '问期权' : '问个股'} · {j.asof} 封存</span>
          <b>{j.name} <span className="num muted">{displayCode(j.code)}</span> · {horizonText(j.horizon)}{j.kind === 'option' ? ` · 期权费 ${((j.fee ?? 0) * 100).toFixed(1)}%` : ''}</b>
          <span className="muted">当时：{j.kind === 'option' ? '回本' : '上涨'}概率 {Math.round(j.prediction.prob * 100)}%</span>
        </div>
        {j.status === 'sealed' ? (
          <div className="jd-side">
            <div className="jd-progress" aria-label={`已走 ${elapsed} / ${j.horizon} 个交易日`}><i style={{ width: `${Math.min(100, elapsed / j.horizon * 100)}%` }} /></div>
            <span className="muted">已走 {elapsed} / {j.horizon} 天 · 约 {j.due_estimate} 揭晓</span>
          </div>
        ) : o && (
          <div className="jd-side">
            <b className={`num ${trendClass(o.return)}`}>{fmtPct(o.return, 1)}</b>
            <span className="muted">{j.kind === 'option' ? (o.hit ? '回本了' : '没回本') : (o.hit ? '涨了' : '没涨')}</span>
          </div>
        )}
        <Seal size={46}>{j.status === 'sealed' ? <>已<br />封存</> : <>已<br />揭晓</>}</Seal>
      </Link>
    </li>
  )
}
