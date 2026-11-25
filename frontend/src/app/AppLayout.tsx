import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { CandlestickChart, FlaskConical, LogOut, type LucideIcon, MessageCircle, Shield, Stamp } from 'lucide-react'
import { logout, useDataVersion, useJudgments, useMe } from '../api/client'
import StockSearch from '../components/StockSearch'
import HomeResearchPet from '../components/xiaosi/HomeResearchPet'
import './AppLayout.css'

type Item = { to: string; label: string; short?: string; icon: LucideIcon; match?: (path: string) => boolean }
// 四项：问、看结果、验证方法（方法库 + 我验证过的）、行情（个股 + 大盘）。后两项的两页在页内切换。
const GROUPS: { title: string; items: Item[] }[] = [
  { title: '', items: [
    { to: '/', label: '问小四', icon: MessageCircle, match: p => p === '/' || p.startsWith('/ask') },
    { to: '/judgments', label: '我的判断', short: '判断', icon: Stamp },
    { to: '/patterns', label: '验证方法', short: '方法', icon: FlaskConical, match: p => p.startsWith('/patterns') || p.startsWith('/records') },
    { to: '/stocks', label: '行情', icon: CandlestickChart, match: p => p.startsWith('/stocks') || p.startsWith('/market') },
  ] },
]

/** 小四手里的数据截至哪天：数字有出处，放在导航底部随时能看到。 */
function DataNote() {
  const { data, isError } = useDataVersion()
  if (isError) return <span className="data-note warn"><i />数据未就绪</span>
  if (!data) return <span className="data-note"><i />读取数据版本…</span>
  return <span className="data-note" title={`数据版本 ${data.id}\n${data.adjustment}`}><i className="ok" />日线截至 {data.data_end}</span>
}

function UserMenu() {
  const me = useMe()
  const qc = useQueryClient()
  const navigate = useNavigate()
  if (!me.data) return null
  return (
    <div className="user-menu">
      {me.data.is_admin && <NavLink to="/admin" className="icon-link" title="管理后台"><Shield size={15} /><span>管理</span></NavLink>}
      <span className="user-chip" title={me.data.username}><i aria-hidden="true">{me.data.username.slice(0, 1).toUpperCase()}</i><span>{me.data.username}</span></span>
      <button className="icon-link" title="退出登录" aria-label="退出登录" onClick={async () => { await logout(); qc.clear(); navigate('/login', { replace: true }) }}>
        <LogOut size={15} />
      </button>
    </div>
  )
}

export default function AppLayout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const judgments = useJudgments()
  const sealed = judgments.data?.items.filter(j => j.status === 'sealed').length ?? 0

  // 封存数变了（刚封存了一个）：数字跳一下
  const before = useRef<number | null>(null)
  const [bump, setBump] = useState(0)
  useEffect(() => {
    if (!judgments.data) return
    if (before.current !== null && sealed > before.current) setBump(b => b + 1)
    before.current = sealed
  }, [sealed, judgments.data])

  // 墨黑的选中块在菜单项之间滑过去，而不是瞬间跳
  const nav = useRef<HTMLElement>(null)
  const [pill, setPill] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  useLayoutEffect(() => {
    const place = () => {
      const on = nav.current?.querySelector<HTMLElement>('a.on')
      if (!on || !nav.current) return setPill(null)
      const a = on.getBoundingClientRect(), n = nav.current.getBoundingClientRect()
      setPill({ x: a.left - n.left, y: a.top - n.top, w: a.width, h: a.height })
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [pathname])

  return (
    <div className="app">
      <aside className="sidebar">
        <Link to="/" className="brand" aria-label="四象智投首页">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          <span className="brand-text"><b>四象智投</b><small>心里有数，再出手</small></span>
        </Link>

        <nav aria-label="主导航" ref={nav}>
          <i className="nav-pill" aria-hidden="true" style={pill ? { transform: `translate(${pill.x}px, ${pill.y}px)`, width: pill.w, height: pill.h, opacity: 1 } : { opacity: 0 }} />
          {GROUPS.map(g => (
            <div key={g.title} className="nav-group">
              {g.title && <span className="nav-title">{g.title}</span>}
              {g.items.map(n => {
                const active = n.match ? n.match(pathname) : pathname.startsWith(n.to)
                return (
                  <NavLink key={n.to} to={n.to} className={active ? 'on' : ''} aria-current={active ? 'page' : undefined} title={n.label}>
                    <n.icon size={17} /><span className="nav-full">{n.label}</span><span className="nav-short">{n.short ?? n.label}</span>
                    {n.to === '/judgments' && sealed > 0 && <em key={bump} className={bump ? 'bump' : ''} title={`${sealed} 个判断封存中`}>{sealed}</em>}
                  </NavLink>
                )
              })}
            </div>
          ))}
        </nav>

        <div className="side-pet">
          <HomeResearchPet size={44} />
          <div><b>小四</b><DataNote /></div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <Link to="/" className="topbar-brand" aria-label="四象智投首页"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span></Link>
          <StockSearch onPick={c => navigate(`/stocks/${c}`)} placeholder="搜股票看 K 线：代码或名称，如 600519 / 茅台" />
          <UserMenu />
        </header>
        <main className="page"><Outlet /></main>
      </div>
    </div>
  )
}
