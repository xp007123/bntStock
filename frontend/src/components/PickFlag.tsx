import { Link } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { useStockPick } from '../api/client'
import '../features/picks/picks.css'

/** 这只股票在最近一次选股名单里：给一个小提示，点过去看整份名单。不在名单里就什么都不显示。 */
export default function PickFlag({ code }: { code: string }) {
  const pick = useStockPick(code).data?.pick
  if (!pick) return null
  return (
    <Link to={`/picks/${pick.strategy}?date=${pick.date}`} className="pick-flag" title="看这一天的整份名单">
      <Zap size={13} />{pick.date} 进了{pick.name}名单，第 {pick.rank} 名
    </Link>
  )
}
