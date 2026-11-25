import SubNav, { MARKET_TABS } from '../../components/SubNav'
import WatchlistCard from '../home/WatchlistCard'
import '../home/HomePage.css'

/** 我的自选：行情下面的第一页。加过自选的股票都在这里，每只能看小四的看法，也能去看 K 线。 */
export default function WatchPage() {
  return (
    <div className="watch-page">
      <SubNav items={MARKET_TABS} />
      <header className="page-head fade-in">
        <h1>我的自选</h1>
        <p className="muted">你关注的股票都在这里。每只给一个数：和现在走势相似的时候，之后 1 个月在涨的比例。点名字看小四的完整回答，点“K 线”看走势。</p>
      </header>
      <WatchlistCard page />
    </div>
  )
}
