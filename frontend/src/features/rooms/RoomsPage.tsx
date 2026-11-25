import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { usePersonas, useRooms } from '../../api/client'
import SubNav, { ASK_TABS } from '../../components/SubNav'
import Avatar from './Avatar'
import './rooms.css'

/** 聊过的：自己开过的群，最近聊的在前。点进去能回看，也能接着聊。 */
export default function RoomsPage() {
  const rooms = useRooms()
  const personas = usePersonas()
  const cast = Object.fromEntries((personas.data?.items ?? []).map(p => [p.id, p]))
  const items = rooms.data?.items ?? []
  return (
    <div className="rooms">
      <SubNav items={ASK_TABS} />
      <header className="page-head fade-in">
        <h1>聊过的</h1>
        <p className="muted">你开过的群都在这里。点进去可以回看，也可以接着聊。</p>
      </header>
      {personas.data && !personas.data.available ? <div className="card state">群聊还没开通。</div>
        : rooms.isLoading ? <div className="state">读取中…</div>
        : items.length === 0 ? (
          <section className="card rooms-empty">
            <p>还没开过群。问一只股票，在结论页点“拉他们进来聊聊”；或者去 <Link to="/personas">角色</Link> 里挑一个人单聊。</p>
            <Link to="/" className="btn primary lg">去问一只股票</Link>
          </section>
        ) : (
          <ul className="rooms-list stagger">
            {items.map(r => (
              <li key={r.id}>
                <Link to={`/rooms/${r.id}`}>
                  <div className="rooms-faces">{r.members.slice(0, 4).map(pid => cast[pid] && <Avatar key={pid} persona={cast[pid]} size={30} />)}</div>
                  <div className="rooms-main">
                    <b>{r.title}<span className="muted">{r.count} 条 · {r.updated_at.slice(5, 10)}</span></b>
                    <span className="muted">{r.last ? `${r.last.name}：${r.last.text.replace(/\n/g, ' ')}` : '还没人说话'}</span>
                  </div>
                  <ChevronRight size={18} className="jd-go" />
                </Link>
              </li>
            ))}
          </ul>
        )}
    </div>
  )
}
