import { NavLink, useLocation } from 'react-router-dom'

/** 页内的二级切换。主导航收成 4 项后，“验证方法”“行情”各自下面的两页用它切。 */
export default function SubNav({ items }: { items: { to: string; label: string; match?: (path: string) => boolean }[] }) {
  const { pathname } = useLocation()
  return (
    <nav className="seg subnav" aria-label="页内切换">
      {items.map(i => {
        const on = i.match ? i.match(pathname) : pathname.startsWith(i.to)
        return <NavLink key={i.to} to={i.to} className={on ? 'on' : ''} aria-current={on ? 'page' : undefined}>{i.label}</NavLink>
      })}
    </nav>
  )
}

export const ASK_TABS = [
  { to: '/', label: '提问', match: (p: string) => p === '/' || p.startsWith('/ask') },
  { to: '/rooms', label: '聊过的' },
  { to: '/personas', label: '角色' },
]
export const ADMIN_TABS = [
  { to: '/admin', label: '用户与数据', match: (p: string) => p === '/admin' },
  { to: '/admin/personas', label: '角色管理' },
]
export const METHOD_TABS = [
  { to: '/patterns', label: '方法库' },
  { to: '/records', label: '我验证过的' },
]
export const MARKET_TABS = [
  { to: '/watch', label: '自选' },
  { to: '/stocks', label: '个股' },
  { to: '/market', label: '大盘' },
]
