import { useState } from 'react'
import { useIndexDaily, useIndices } from '../../api/client'
import KLineChart from '../../components/KLineChart'
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
      <h2 className="section-title">指数概览 <span className="muted">{indices.data?.[0]?.date ?? ''}</span></h2>
      {indices.isError ? <div className="card state error">指数读取失败</div> : (
        <div className="index-cards">
          {(indices.data ?? []).map(i => (
            <button key={i.code} className={`index-card ${i.code === code ? 'on' : ''}`} onClick={() => setCode(i.code)} aria-pressed={i.code === code}>
              <span>{i.name}</span>
              <b className="num">{fmtPrice(i.close)}</b>
              <small className={`num ${trendClass(i.change)}`}>{fmtPct(i.change)}</small>
            </button>
          ))}
        </div>
      )}
      <section className="card">
        <div className="card-title">{current?.name ?? code} <span className="muted">日 K · 近 1 年</span></div>
        {chart.data ? <KLineChart bars={chart.data.bars} height={360} ariaLabel={`${current?.name ?? code} 日 K 线`} /> : <div className="state">读取中…</div>}
      </section>
    </div>
  )
}
