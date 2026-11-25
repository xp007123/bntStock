import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { LogOut, Shield } from 'lucide-react'
import { logout, useDataVersion, useMe } from '../api/client'
import './AppLayout.css'

const NAV = [
  { to: '/', label: '问小四', end: true },
  { to: '/stocks', label: '个股看盘' },
  { to: '/patterns', label: '形态测试' },
  { to: '/records', label: '研究记录' },
  { to: '/market', label: '全 A 行情' },
]

function DataBadge() {
  const { data, isError } = useDataVersion()
  if (isError) return <span className="data-badge warn"><i />数据未就绪</span>
  if (!data) return <span className="data-badge"><i />读取数据版本…</span>
  return (
    <span className="data-badge" title={`数据版本 ${data.id}\n${data.adjustment}`}>
      <i className="ok" />日线截至 {data.data_end}
    </span>
  )
}

function UserMenu() {
  const me = useMe()
  const qc = useQueryClient()
  const navigate = useNavigate()
  if (!me.data) return null
  return (
    <div className="user-menu">
      {me.data.is_admin && <NavLink to="/admin" className="icon-link" title="管理后台"><Shield size={15} />管理</NavLink>}
      <span className="user-name">{me.data.username}</span>
      <button className="icon-link" title="退出登录" onClick={async () => { await logout(); qc.clear(); navigate('/login', { replace: true }) }}>
        <LogOut size={15} />退出
      </button>
    </div>
  )
}

export default function AppLayout() {
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="四象智投首页">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          四象智投
        </NavLink>
        <nav aria-label="主导航">
          {NAV.map(n => <NavLink key={n.to} to={n.to} end={n.end}>{n.label}</NavLink>)}
        </nav>
        <DataBadge />
        <UserMenu />
      </header>
      <main className="page"><Outlet /></main>
    </div>
  )
}
