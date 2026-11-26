import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronRight, FlaskConical, LogOut, MessagesSquare, Shield, Stamp, Star, Zap } from 'lucide-react'
import { logout, useJobs, useJudgments, useMe, useRooms, useWatchlist } from '../../api/client'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import SubNav, { ME_TABS } from '../../components/SubNav'
import { horizonText } from '../ask/horizons'
import './me.css'

const maskPhone = (p: string) => (p.length >= 7 ? `${p.slice(0, 3)}****${p.slice(-4)}` : p)

/** 我的：一张墨黑的名片（我是谁、我攒下了多少东西），下面是快要揭晓的判断和几个入口。数字全部来自接口。 */
export default function MePage() {
  const me = useMe()
  const judgments = useJudgments()
  const watch = useWatchlist()
  const rooms = useRooms()
  const jobs = useJobs()
  const qc = useQueryClient()
  const navigate = useNavigate()
  if (!me.data) return <div className="state">读取中…</div>
  const items = judgments.data?.items ?? []
  const sealed = items.filter(j => j.status === 'sealed').sort((a, b) => a.due_estimate.localeCompare(b.due_estimate))
  const settled = items.length - sealed.length
  const rec = judgments.data?.record
  const hit = rec && rec.settled > 0 && rec.hit_rate != null ? `${Math.round(rec.hit_rate * 100)}%` : null

  const stats = [
    { to: '/judgments', n: sealed.length, label: '封存中的判断' },
    { to: '/watch', n: watch.data?.items.length ?? 0, label: '自选的股票' },
    { to: '/rooms', n: rooms.data?.items.length ?? 0, label: '聊过的群' },
    { to: '/records', n: jobs.data?.length ?? 0, label: '验证过的方法' },
  ]
  const links = [
    { to: '/judgments', icon: Stamp, title: '我的判断', note: settled ? `已揭晓 ${settled} 个${hit ? `，实际成真 ${hit}` : ''}` : '封存的想法，到期自动揭晓' },
    { to: '/watch', icon: Star, title: '我的自选', note: '每只都能看小四今天怎么看' },
    { to: '/rooms', icon: MessagesSquare, title: '聊过的群', note: '记录都在，随时回去接着聊' },
    { to: '/records', icon: FlaskConical, title: '我验证过的方法', note: '自己调过参数、跑过的方法' },
    { to: '/picks', icon: Zap, title: '策略名单', note: '每个交易日出的选股名单' },
    ...(me.data.is_admin ? [{ to: '/admin', icon: Shield, title: '管理后台', note: '用户审核、数据同步、角色管理' }] : []),
  ]

  return (
    <div className="me">
      <SubNav items={ME_TABS} />

      <section className="me-hero fade-in">
        <div className="me-who">
          <span className="me-face" aria-hidden="true">{me.data.username.slice(0, 1).toUpperCase()}</span>
          <div>
            <h1>{me.data.username}{me.data.is_admin && <span className="me-badge">管理员</span>}</h1>
            <p className="num">手机 {maskPhone(me.data.phone)}</p>
          </div>
        </div>
        <div className="me-pet" aria-hidden="true"><HomeResearchPet size={112} /></div>
        <div className="me-stats">
          {stats.map(s => (
            <Link key={s.to} to={s.to}><b className="num">{s.n}</b><span>{s.label}</span></Link>
          ))}
        </div>
      </section>

      <div className="me-grid">
        <section className="card me-next fade-in">
          <div className="card-title"><span>快要揭晓的判断</span><Link to="/judgments" className="more">全部<ChevronRight size={14} /></Link></div>
          {sealed.length === 0 ? (
            <p className="muted me-empty">现在没有封存中的判断。问完小四后点“封存这个判断”，它替你保管到揭晓那天。</p>
          ) : (
            <ul>
              {sealed.slice(0, 3).map(j => {
                const elapsed = j.prediction.elapsed ?? 0
                return (
                  <li key={j.id}>
                    <Link to={`/judgments/${j.id}`}>
                      <div className="me-line"><b>{j.name}</b><span>{j.kind === 'option' ? '问期权' : '问个股'} · {horizonText(j.horizon)}</span></div>
                      <div className="progress live" aria-label={`已走 ${elapsed} / ${j.horizon} 个交易日`}><i style={{ width: `${Math.min(100, elapsed / j.horizon * 100)}%` }} /></div>
                      <small>已走 {elapsed} / {j.horizon} 天 · 约 {j.due_estimate} 揭晓</small>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section className="card me-menu fade-in">
          {links.map(l => (
            <Link key={l.to} to={l.to}>
              <i><l.icon size={17} /></i>
              <span><b>{l.title}</b><small>{l.note}</small></span>
              <ChevronRight size={16} />
            </Link>
          ))}
        </section>
      </div>

      <button className="me-out" onClick={async () => { await logout(); qc.clear(); navigate('/login', { replace: true }) }}><LogOut size={15} />退出登录</button>
    </div>
  )
}
