import { NavLink, Outlet } from 'react-router-dom'
import { useDataVersion } from '../api/client'
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
      </header>
      <main className="page"><Outlet /></main>
    </div>
  )
}
