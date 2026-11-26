import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { usePersonas } from '../../api/client'
import Avatar from './Avatar'
import LineupPicker from './LineupPicker'
import './rooms.css'

/** 入口：拉他们进来聊聊。群聊没开通（没配模型）时整块不显示。 */
export default function InviteCard({ code, name }: { code: string; name: string }) {
  const personas = usePersonas()
  const [picking, setPicking] = useState(false)
  const data = personas.data
  if (!data?.available) return null
  const guests = data.default.map(id => data.items.find(p => p.id === id)).filter(Boolean) as typeof data.items
  const more = data.items.length - guests.length
  return (
    <section className="invite">
      <div className="invite-faces">{guests.map(p => <Avatar key={p.id} persona={p} size={34} />)}<Avatar persona={data.host} size={34} /></div>
      <h3>拉他们进来聊聊</h3>
      <p>{guests.map(p => p.name).join('、')}，各看各的，会怎么吵{name}？小四主持，你也可以插话。{more > 0 && <>还有 {more} 位可以换上场。</>}</p>
      <button className="btn dark lg" onClick={() => setPicking(true)}>选人开群<ArrowRight size={16} /></button>
      {picking && <LineupPicker code={code} name={name} onClose={() => setPicking(false)} />}
    </section>
  )
}
