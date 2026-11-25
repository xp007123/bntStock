import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { ApiError, openRoom, usePersonas } from '../../api/client'
import Avatar from './Avatar'
import './rooms.css'

/** 入口：拉他们进来聊聊。群聊没开通（没配模型）时整块不显示。 */
export default function InviteCard({ code, name }: { code: string; name: string }) {
  const personas = usePersonas()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const data = personas.data
  if (!data?.available) return null
  const guests = data.default.map(id => data.items.find(p => p.id === id)).filter(Boolean) as typeof data.items
  const go = async () => {
    setBusy(true); setError('')
    try { navigate(`/rooms/${(await openRoom(code)).id}`) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(false) }
  }
  return (
    <section className="invite">
      <div className="invite-faces">{guests.map(p => <Avatar key={p.id} persona={p} size={34} />)}<Avatar persona={data.host} size={34} /></div>
      <h3>拉他们进来聊聊</h3>
      <p>{guests.map(p => p.name).join('、')}，各看各的，会怎么吵{name}？小四主持，你也可以插话。</p>
      <button className="btn dark lg" disabled={busy} onClick={go}>{busy ? '正在拉群…' : <>开个群<ArrowRight size={16} /></>}</button>
      {error && <p className="invite-error">{error}</p>}
    </section>
  )
}
