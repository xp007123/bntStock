import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, openRoom, type Persona, usePersonas } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import SubNav, { ASK_TABS } from '../../components/SubNav'
import Avatar from './Avatar'
import './rooms.css'

/** 角色页：我们有哪些角色。每人一张卡：看什么、信什么、怎么说话；可以直接拉 TA 单聊一只股票。 */
export default function PersonasPage() {
  const personas = usePersonas()
  const data = personas.data
  return (
    <div className="personas">
      <SubNav items={ASK_TABS} />
      <header className="page-head fade-in">
        <h1>群里都有谁</h1>
        <p className="muted">几位路子完全不同的投资人，各看各的。同一只股票，他们会得出不一样的结论，这正是值得听的地方。{data?.disclaimer}</p>
      </header>
      {personas.isLoading ? <div className="state">读取中…</div> : !data ? <div className="card state error">角色读取失败</div> : (
        <>
          <section className="persona-host card">
            <Avatar persona={data.host} size={48} />
            <div><b>{data.host.name}<span className="tag">主持人</span></b><p className="muted">{data.host.tagline}。负责开场、点名、拱火、收场，自己不下结论。</p></div>
          </section>
          <div className="persona-grid stagger">{data.items.map(p => <Card key={p.id} p={p} available={data.available} />)}</div>
          {!data.available && <p className="muted">群聊还没开通，暂时只能看介绍。</p>}
        </>
      )}
    </div>
  )
}

function Card({ p, available }: { p: Persona; available: boolean }) {
  const navigate = useNavigate()
  const [picking, setPicking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const go = async (code: string) => {
    setBusy(true); setError('')
    try { navigate(`/rooms/${(await openRoom(code, [p.id])).id}`) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(false) }
  }
  return (
    <article className="persona-card card" style={{ '--who': p.color } as React.CSSProperties}>
      <header>
        <Avatar persona={p} size={56} />
        <div><h2>{p.name}</h2><span className="muted">{p.title}</span></div>
        <span className="tag night">{p.lens}</span>
      </header>
      <p className="persona-tagline">“{p.tagline}”</p>
      <div className="persona-cols">
        <div><h3>他信什么</h3><ul>{p.beliefs.slice(0, 4).map(b => <li key={b}>{b}</li>)}</ul></div>
        <div><h3>他先问什么</h3><ol>{p.asks.slice(0, 4).map(b => <li key={b}>{b}</li>)}</ol></div>
      </div>
      {p.lines[0] && <p className="persona-line"><span className="muted">在群里大概这么说话：</span>{p.lines[0]}</p>}
      {available && (
        <footer>
          {picking ? (
            <div className="persona-pick">
              <StockSearch onPick={go} placeholder={`和${p.name}聊哪只股票？输入代码或名称`} />
              <button className="btn" disabled={busy} onClick={() => setPicking(false)}>{busy ? '正在拉群…' : '算了'}</button>
            </div>
          ) : <button className="btn dark" onClick={() => setPicking(true)}>拉 {p.name} 聊聊</button>}
          {error && <p className="invite-error">{error}</p>}
        </footer>
      )}
    </article>
  )
}
