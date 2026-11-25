import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CandlestickChart, Plus, X } from 'lucide-react'
import { addWatch, ApiError, removeWatch, useWatchlist } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import { fmtPct, fmtPrice, trendClass } from '../../lib/format'
import { horizonText } from '../ask/horizons'

/**
 * 我的自选：你关注的这几只，小四今天怎么看。
 * 每只给一个数：和现在相似的时候，之后 1 个月在涨的比例；旁边的刻度是它平时的比例。点一行看完整回答。
 */
export default function WatchlistCard({ page = false }: { page?: boolean }) {
  const q = useWatchlist()
  const qc = useQueryClient()
  const [adding, setAdding] = useState(page)
  const [error, setError] = useState('')
  const all = q.data?.items ?? []
  // 首页只放前几只，全部在“行情 → 自选”里
  const items = page ? all : all.slice(0, 6)
  const act = async (fn: () => Promise<unknown>) => {
    setError('')
    try { qc.setQueryData(['watchlist'], await fn()) } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }

  return (
    <section className={`card home-card watch ${page ? 'watch-full' : ''}`}>
      <div className="card-title">
        <span>我的自选 <span className="muted">{q.data && items.length ? `小四今天怎么看 · ${q.data.data_end} 收盘` : ''}</span></span>
        <span className="watch-tools">
          {!adding && <button className="more" onClick={() => setAdding(true)}><Plus size={14} />加一只</button>}
          {!page && <Link to="/watch" className="more">全部<ArrowRight size={14} /></Link>}
        </span>
      </div>

      {adding && (
        <div className="watch-add">
          <StockSearch onPick={c => { if (!page) setAdding(false); act(() => addWatch(c)) }} placeholder="输入代码或名称，选中就加进自选" />
          {!page && <button className="btn" onClick={() => setAdding(false)}>不加了</button>}
        </div>
      )}
      {error && <p className="watch-error">{error}</p>}

      {q.isLoading ? <p className="muted">读取中…</p> : q.isError ? <p className="muted">自选读取失败</p> : items.length === 0 ? (
        !adding && <p className="muted watch-empty">把常看的股票加进来。以后每天打开首页，就能看到小四对它们的看法，不用一只只去搜。</p>
      ) : (
        <ul className="watch-list">
          {items.map(i => (
            <li key={i.code}>
              <Link to={`/ask/stock?code=${i.code}&h=${i.horizon}`} title="看小四的完整回答">
                <div className="watch-name"><b>{i.name}</b><span className="num">{fmtPrice(i.close)} <em className={`num ${trendClass(i.change)}`}>{fmtPct(i.change)}</em></span></div>
                {i.prob != null && i.base_prob != null ? (
                  <div className="watch-prob">
                    <div className="watch-bar" aria-hidden="true">
                      <i style={{ width: `${i.prob * 100}%` }} />
                      <u style={{ left: `${i.base_prob * 100}%` }} />
                    </div>
                    <span>{horizonText(i.horizon)}后在涨 <b className="num">{Math.round(i.prob * 100)}%</b><small>平时 {Math.round(i.base_prob * 100)}%</small></span>
                  </div>
                ) : <p className="muted watch-note">{i.note ?? '暂时算不出来'}</p>}
              </Link>
              <Link className="watch-k" to={`/stocks/${i.code}`} title={`看 ${i.name} 的 K 线`}><CandlestickChart size={14} />K 线</Link>
              <button className="watch-x" aria-label={`把 ${i.name} 从自选里拿掉`} onClick={() => act(() => removeWatch(i.code))}><X size={14} /></button>
            </li>
          ))}
        </ul>
      )}
      {!page && all.length > items.length && <Link to="/watch" className="muted watch-rest">还有 {all.length - items.length} 只，去自选里看全部</Link>}
      {items.length > 0 && <p className="muted footnote">橙色条：和现在走势相似的时候，之后在涨的比例。竖线：它不挑时候的比例。只是历史统计。</p>}
    </section>
  )
}
