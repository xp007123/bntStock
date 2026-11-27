import { Link, NavLink } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import type { PickStrategy } from '../../api/client'

/** 某个策略两页（名单 / 历史表现）共用的页头：回到全部策略、策略名、一句话介绍、两页切换。 */
export default function StrategyHead({ id, s, title }: { id: string; s?: PickStrategy; title?: string }) {
  const on = ({ isActive }: { isActive: boolean }) => (isActive ? 'on' : '')
  return (
    <header className="page-head fade-in">
      <Link to="/picks" className="pk-back"><ChevronLeft size={14} />全部策略</Link>
      <h1>{title ?? s?.name ?? ''}{s && <span className="tag plain">{s.alias}</span>}</h1>
      {s && <p className="muted">{s.tagline}每个交易日 {s.publish_at} 出名单。</p>}
      <nav className="seg subnav pk-tabs" aria-label="这个策略的两页">
        <NavLink end to={`/picks/${id}`} className={on}>名单</NavLink>
        <NavLink to={`/picks/${id}/record`} className={on}>{s?.record_label ?? '历史表现'}</NavLink>
      </nav>
    </header>
  )
}
