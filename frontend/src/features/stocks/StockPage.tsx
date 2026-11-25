import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { type Adjust, useDaily, useFinancials, useSecurity } from '../../api/client'
import KLineChart from '../../components/KLineChart'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import SubNav, { MARKET_TABS } from '../../components/SubNav'
import WatchStar from '../../components/WatchStar'
import { dailyChange } from '../../lib/indicators'
import { displayCode, fmtBig, fmtPct, fmtPrice, trendClass } from '../../lib/format'
import { FinancialCard, ValuationCard } from './FinancialPanels'
import './StockPage.css'

const ADJUSTS: { id: Adjust; label: string }[] = [
  { id: 'qfq', label: '前复权' }, { id: 'hfq', label: '后复权' }, { id: 'none', label: '不复权' },
]
const RANGES = [
  { id: 120, label: '半年' }, { id: 250, label: '1 年' }, { id: 750, label: '3 年' }, { id: 0, label: '全部' },
]
export const DEFAULT_STOCK = 'sh600519'

export default function StockPage() {
  const { code = DEFAULT_STOCK } = useParams()
  const [adjust, setAdjust] = useState<Adjust>('qfq')
  const [range, setRange] = useState(250)
  const security = useSecurity(code)
  const daily = useDaily(code, adjust, range || undefined)
  const fin = useFinancials(code)
  const bars = daily.data?.code === code ? daily.data.bars : []
  const last = bars.at(-1)
  const chg = last ? dailyChange(last.close, last.prev_close, bars.at(-2)?.close) : null

  return (
    <div className="stock-page">
      <SubNav items={MARKET_TABS} />
      {security.isError ? (
        <div className="card state error">没有找到 {code}，请换一个代码搜索。</div>
      ) : (
        <div className="stock-grid">
          <section className="card stock-main" aria-label="K 线">
            <header className="stock-head">
              <div>
                <h1>{security.data?.name ?? '…'} <span className="code num">{displayCode(code)}</span><WatchStar code={code} /></h1>
                <p className="muted">{security.data?.sector ?? '未分类'} · 上市以来 {security.data?.rows ?? '—'} 个交易日</p>
              </div>
              <div className="quote">
                <b className={`num ${trendClass(chg)}`}>{fmtPrice(last?.close)}</b>
                <span className={`num chg ${trendClass(chg)}`}>{fmtPct(chg)}</span>
                <span className="muted">{last?.date ?? ''}</span>
              </div>
            </header>
            <div className="stock-controls">
              <div className="seg" role="group" aria-label="复权方式">
                {ADJUSTS.map(a => <button key={a.id} aria-pressed={adjust === a.id} onClick={() => setAdjust(a.id)}>{a.label}</button>)}
              </div>
              <div className="seg" role="group" aria-label="时间范围">
                {RANGES.map(r => <button key={r.id} aria-pressed={range === r.id} onClick={() => setRange(r.id)}>{r.label}</button>)}
              </div>
            </div>
            {daily.isError ? <div className="state error">行情读取失败：{String(daily.error.message)}</div>
              : bars.length === 0 ? <div className="state">读取行情…</div>
              : <KLineChart bars={bars} ariaLabel={`${security.data?.name ?? code} 日 K 线`} />}
          </section>

          <div className="stock-fin"><FinancialCard fin={fin.data} /></div>

          <aside className="stock-side">
            <div className="card">
              <div className="card-title">当日数据</div>
              <dl className="kv">
                <dt>开盘</dt><dd className="num">{fmtPrice(last?.open)}</dd>
                <dt>最高</dt><dd className="num">{fmtPrice(last?.high)}</dd>
                <dt>最低</dt><dd className="num">{fmtPrice(last?.low)}</dd>
                <dt>前收盘</dt><dd className="num">{fmtPrice(last?.prev_close)}</dd>
                <dt>成交量</dt><dd className="num">{fmtBig(last?.volume, '股')}</dd>
                <dt>成交额</dt><dd className="num">{fmtBig(last?.amount)}</dd>
              </dl>
            </div>
            <ValuationCard fin={fin.data} />
            <div className="ask-xiaosi">
              <div className="ask-xiaosi-who"><HomeResearchPet size={40} /><b>拿这只票问小四</b></div>
              <p>类似的走势以前出现过多少次，后来是涨是跌，最坏会怎样。</p>
              <Link className="btn primary" to={`/ask/stock?code=${code}&h=21`}>接下来 1 个月，涨的可能大吗？</Link>
              <Link className="btn" to={`/ask/option?code=${code}&h=63&fee=7.5`}>它的 3 个月期权值不值？</Link>
            </div>
            <p className="footnote muted">
              数据版本 {daily.data?.data_version ?? '—'} · {ADJUSTS.find(a => a.id === adjust)?.label}。
              仅日线收盘数据，不含盘中走势。
            </p>
          </aside>
        </div>
      )}
    </div>
  )
}
