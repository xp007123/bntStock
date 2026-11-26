import { usePickStrategies } from '../../api/client'
import SubNav, { PICK_TABS } from '../../components/SubNav'
import StrategyCard from './StrategyCard'
import './picks.css'

/** 策略名单：所有选股策略摆在一起，每个一张卡。点进去看当天的票和它过去的表现。 */
export default function PickBoardPage() {
  const q = usePickStrategies()
  const items = q.data?.items ?? []
  return (
    <div className="picks">
      <SubNav items={PICK_TABS} />
      <header className="page-head fade-in">
        <h1>策略名单</h1>
        <p className="muted">每个策略按自己的固定规则，每个交易日出一份名单。点进去看当天的票，和它过去的表现。</p>
      </header>
      {q.isLoading ? <div className="state">读取中…</div>
        : q.isError ? <div className="state error">策略没读出来，稍后再试</div>
        : items.length === 0 ? <div className="state">还没有策略。</div>
        : <div className="sc-grid stagger">{items.map(s => <StrategyCard key={s.id} s={s} full />)}</div>}
    </div>
  )
}
