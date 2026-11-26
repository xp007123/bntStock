import { NavLink, useLocation } from 'react-router-dom'

/** 页内的二级切换。主导航只有 4 项（选股 / 问小四 / 行情 / 我的），每项下面的几页用它切。 */
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
export const PICK_TABS = [
  { to: '/picks', label: '今日名单', match: (p: string) => p === '/picks' },
  { to: '/picks/record', label: '历史表现' },
  { to: '/patterns', label: '方法库' },
  { to: '/records', label: '我验证过的' },
]
export const ME_TABS = [
  { to: '/me', label: '账户' },
  { to: '/judgments', label: '我的判断' },
]
export const MARKET_TABS = [
  { to: '/watch', label: '自选' },
  { to: '/stocks', label: '个股' },
  { to: '/market', label: '大盘' },
]
