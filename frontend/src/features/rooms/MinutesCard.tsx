import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Share2 } from 'lucide-react'
import { ApiError, type Minutes, type Persona, sealJudgment } from '../../api/client'
import { fmtPct, trendClass } from '../../lib/format'
import Avatar from './Avatar'

const HORIZON = 21     // “站他”封存的期限：一个月

/** 立场说中了没有：看多看涨、看空看跌才算。没表态的不评。 */
const called = (stance: string | null, ret: number) => (stance === '看多' ? ret > 0 : stance === '看空' ? ret < 0 : null)

/**
 * 纪要卡：小四把每位嘉宾的立场记下来。每个人的那句话是原话，数据是当时查到的原文。
 * “站他”= 按他的立场封存一个判断，到期自动揭晓。过几天再回来看，卡上会多一行“之后涨跌多少”。
 */
export default function MinutesCard({ card, cast, onShare }: { card: Minutes; cast: Record<string, Persona>; onShare: () => void }) {
  const [stood, setStood] = useState<{ pid: string; id: number } | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const stand = async (pid: string, stance: string) => {
    setBusy(pid); setError('')
    try { setStood({ pid, id: (await sealJudgment({ kind: 'stock', code: card.code, horizon: HORIZON, stance: stance === '看多' ? 'yes' : 'no' })).id }) }
    catch (e) { setError(e instanceof ApiError ? e.message : '没封存上，再试一次') }
    setBusy('')
  }
  const since = card.since
  return (
    <div className="minutes">
      <div className="minutes-head">
        <b>{card.name} · 纪要</b>
        <button className="minutes-share" onClick={onShare}><Share2 size={13} />分享</button>
      </div>
      <ul>
        {card.stances.map(s => {
          const ok = since ? called(s.stance, since.ret) : null
          return (
            <li key={s.persona_id}>
              <Avatar persona={cast[s.persona_id]} name={s.name} size={30} />
              <div>
                <span className="minutes-who">
                  {s.name}
                  {s.stance && <i className={s.stance === '看多' ? 'up' : s.stance === '看空' ? 'down' : ''}>{s.stance}</i>}
                  {ok && <em>目前说中</em>}
                </span>
                <p>{s.quote}</p>
              </div>
              {(s.stance === '看多' || s.stance === '看空') && (stood?.pid === s.persona_id
                ? <Link className="minutes-stood" to={`/judgments/${stood.id}`}>已封存</Link>
                : <button className="minutes-stand" disabled={!!busy || !!stood} onClick={() => stand(s.persona_id, s.stance!)}>{busy === s.persona_id ? '封存中…' : '站他'}</button>)}
            </li>
          )
        })}
      </ul>
      {card.split && <p className="minutes-split"><b>分歧</b>{card.split}</p>}
      {card.data && <p className="minutes-data">〔数据〕{card.data}</p>}
      {since && <p className="minutes-since">纪要之后 {since.days} 个交易日，股价 <em className={`num ${trendClass(since.ret)}`}>{fmtPct(since.ret, 1)}</em></p>}
      {stood && <p className="minutes-note">已经按{card.stances.find(s => s.persona_id === stood.pid)?.name}的看法封存了一个判断，一个月后自动揭晓。</p>}
      {error && <p className="minutes-note error">{error}</p>}
    </div>
  )
}
