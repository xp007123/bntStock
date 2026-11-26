import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { usePersonaRecent, usePersonas } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import SubNav, { ASK_TABS } from '../../components/SubNav'
import Avatar from './Avatar'
import LineupPicker from './LineupPicker'
import './rooms.css'

/** 角色的个人页：他是谁、信什么、先问什么、不碰什么、怎么说话，以及他最近在我的群里说过什么。 */
export default function PersonaPage() {
  const { id = '' } = useParams()
  const personas = usePersonas()
  const recent = usePersonaRecent(id)
  const [stock, setStock] = useState<{ code: string } | null>(null)
  const data = personas.data
  const p = data?.items.find(x => x.id === id)
  if (personas.isLoading) return <div className="state">读取中…</div>
  if (!data || !p) return <div className="state">没有这个角色。<Link to="/personas">看看都有谁</Link></div>
  const others = data.items.filter(x => x.id !== id)
  const said = recent.data?.items ?? []
  return (
    <div className="persona-page">
      <SubNav items={ASK_TABS} />
      <Link to="/personas" className="pp-back"><ChevronLeft size={14} />全部角色</Link>

      <section className="pp-hero fade-in" style={{ '--who': p.color } as React.CSSProperties}>
        <Avatar persona={p} size={128} />
        <div className="pp-who">
          <span className="pp-lens">{p.lens}</span>
          <h1>{p.name}</h1>
          <p className="pp-title">{p.title}</p>
          <p className="pp-tagline">“{p.tagline}”</p>
        </div>
        {data.available && (
          <div className="pp-ask">
            <b>拉 {p.name} 聊一只股票</b>
            <StockSearch onPick={code => setStock({ code })} placeholder="输入代码或名称" />
            <small>选好股票后可以再挑几位和他对着聊</small>
          </div>
        )}
      </section>

      <div className="pp-grid">
        <section className="card pp-card"><h2>他信什么</h2><ul>{p.beliefs.map(b => <li key={b}>{b}</li>)}</ul></section>
        <section className="card pp-card"><h2>看一只股票，他先问什么</h2><ol>{p.asks.map(b => <li key={b}>{b}</li>)}</ol></section>
        {p.avoids.length > 0 && <section className="card pp-card"><h2>他不碰什么</h2><ul>{p.avoids.map(b => <li key={b}>{b}</li>)}</ul></section>}
        <section className="card pp-card">
          <h2>在群里大概这么说话</h2>
          <div className="pp-lines">{p.lines.map(l => <p key={l} className="bubble">{l}</p>)}</div>
        </section>
      </div>

      <section className="card pp-card">
        <h2>他最近在你的群里说过</h2>
        {recent.isLoading ? <p className="muted">读取中…</p> : said.length === 0 ? <p className="muted">还没有。拉他进群聊一只股票，他说过的话会留在这里。</p> : (
          <ul className="pp-said">
            {said.map(m => (
              <li key={`${m.room_id}-${m.seq}`}>
                <Link to={`/rooms/${m.room_id}`}>
                  <span className="pp-said-head"><b>聊{m.title}</b><small>{m.created_at?.slice(5, 10)}</small></span>
                  <p>{m.text.replace(/\n/g, ' ')}</p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="pp-others">
        <h2>其他人</h2>
        <div>{others.map(o => <Link key={o.id} to={`/personas/${o.id}`}><Avatar persona={o} size={44} /><span><b>{o.name}</b><small>{o.lens}</small></span></Link>)}</div>
      </section>
      <p className="muted pp-note">{data.disclaimer}说的是看法和历史上的情况，不构成投资建议。</p>

      {stock && <LineupPicker code={stock.code} name="这只股票" preset={[p.id]} onClose={() => setStock(null)} />}
    </div>
  )
}
