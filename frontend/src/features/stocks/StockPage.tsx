import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { type Adjust, useDaily, useFinancials, useSecurity } from '../../api/client'
import KLineChart from '../../components/KLineChart'
import StockSearch from '../../components/StockSearch'
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
  const navigate = useNavigate()
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
      <div className="stock-toolbar">
        <StockSearch onPick={c => navigate(`/stocks/${c}`)} />
      </div>

      {security.isError ? (
        <div className="card state error">没有找到 {code}，请换一个代码搜索。</div>
      ) : (
        <div className="stock-grid">
          <section className="card stock-main" aria-label="K 线">
            <header className="stock-head">
              <div>
                <h1>{security.data?.name ?? '…'} <span className="code num">{displayCode(code)}</span></h1>
                <p className="muted">{security.data?.sector ?? '未分类'} · 上市以来 {security.data?.rows ?? '—'} 个交易日</p>
              </div>
              <div className="quote">
                <b className={`num ${trendClass(chg)}`}>{fmtPrice(last?.close)}</b>
                <span className={`num ${trendClass(chg)}`}>{fmtPct(chg)}</span>
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
            <div className="card ask-xiaosi">
              <div className="card-title">问小四</div>
              <p className="muted">下一阶段可以在这里直接问：这只票未来上涨的概率、场外期权值不值。</p>
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
