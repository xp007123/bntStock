import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useIndexDaily, useIndices } from '../../api/client'
import KLineChart from '../../components/KLineChart'
import SubNav, { MARKET_TABS } from '../../components/SubNav'
import { fmtPct, fmtPrice, trendClass } from '../../lib/format'
import './MarketPage.css'

/** 全 A 行情（次要入口）：当前先提供指数概览，全市场列表在后续迁移。 */
export default function MarketPage() {
  const indices = useIndices()
  const [code, setCode] = useState('sh000001')
  const chart = useIndexDaily(code, 250)
  const current = indices.data?.find(i => i.code === code)

  return (
    <div className="market">
      <SubNav items={MARKET_TABS} />
      <header className="page-head fade-in">
        <h1>大盘</h1>
        <p className="muted">主要指数{indices.data?.[0]?.date ? ` ${indices.data[0].date} 收盘` : ''}。点一个指数看它近一年的日 K。</p>
      </header>
      {indices.isError ? <div className="card state error">指数读取失败</div> : (
        <div className="index-cards stagger">
          {(indices.data ?? []).map(i => (
            <button key={i.code} className={`index-card ${i.code === code ? 'on' : ''}`} onClick={() => setCode(i.code)} aria-pressed={i.code === code}>
              <span>{i.name}</span>
              <b className="num">{fmtPrice(i.close)}</b>
              <em className={`num chg ${trendClass(i.change)}`}>{fmtPct(i.change)}</em>
            </button>
          ))}
        </div>
      )}
      <section className="card">
        <div className="card-title">
          <span>{current?.name ?? code} <span className="muted">日 K · 近 1 年</span></span>
          <Link to={`/ask/index?code=${code}&h=21`} className="btn dark">问小四：{current?.name ?? '它'}接下来 1 个月涨的可能<ArrowRight size={15} /></Link>
        </div>
        {chart.data ? <KLineChart bars={chart.data.bars} height={360} ariaLabel={`${current?.name ?? code} 日 K 线`} /> : <div className="state">读取中…</div>}
      </section>
    </div>
  )
}
