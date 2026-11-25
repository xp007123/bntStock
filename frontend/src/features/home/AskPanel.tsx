import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, X } from 'lucide-react'
import { useSecurity } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import { displayCode } from '../../lib/format'
import { optionHorizons, stockHorizons } from '../ask/horizons'

type Tab = 'stock' | 'option' | 'method'
const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'stock', label: '问个股', hint: '这只票还能涨吗' },
  { id: 'option', label: '问期权', hint: '这个期权费值不值' },
  { id: 'method', label: '问方法', hint: '我这招灵不灵' },
]

/** 结构化提问：选股票、期限（期权再填期权费），交给小四算。自由对话在下一版开放。 */
export default function AskPanel({ onPick }: { onPick?: () => void }) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('stock')
  const [code, setCode] = useState('')
  const [h, setH] = useState(21)
  const [fee, setFee] = useState('7.5')
  const sec = useSecurity(code || 'sh600519')
  const feeNum = Number(fee)
  const feeOk = Number.isFinite(feeNum) && feeNum > 0 && feeNum < 100
  const horizons = tab === 'option' ? optionHorizons : stockHorizons
  const pick = (t: Tab) => { setTab(t); if (t === 'option' && ![21, 42, 63, 126].includes(h)) setH(63); if (t === 'stock' && ![5, 10, 21, 63].includes(h)) setH(21) }

  const submit = () => {
    if (tab === 'method') return navigate('/patterns')
    if (!code) return
    navigate(tab === 'option' ? `/ask/option?code=${code}&h=${h}&fee=${feeNum}` : `/ask/stock?code=${code}&h=${h}`)
  }

  return (
    <section className="ask-panel" aria-label="向小四提问">
      <div className="ask-tabs" role="tablist">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => pick(t.id)}><b>{t.label}</b><span>{t.hint}</span></button>
        ))}
      </div>

      {tab === 'method' ? (
        <div className="ask-body">
          <p className="ask-sentence">我常用的一个买点，过去 17 年到底灵不灵？</p>
          <p className="muted ask-hint">在“形态”里选一个模板，调成你习惯的参数，小四会扫描全市场 2007 年以来的历史，告诉你它出现之后大多怎么样。</p>
          <button className="btn primary lg ask-go" onClick={submit}>去验证我的方法<ArrowRight size={17} /></button>
        </div>
      ) : (
        <div className="ask-body">
          <div className="ask-sentence">
            <span className="ask-row">{code ? (
              <span className="ask-chip"><b>{sec.data?.name ?? '…'}</b><span className="num">{displayCode(code)}</span>
                <button aria-label="换一只" onClick={() => setCode('')}><X size={14} /></button></span>
            ) : <StockSearch onPick={c => { setCode(c); onPick?.() }} />}</span>
            <span className="ask-group">
              {tab === 'option' ? '买' : '接下来'}
              <span className="ask-select">
                {horizons.map(o => <button key={o.value} aria-pressed={h === o.value} onClick={() => setH(o.value)}>{o.label.trim()}</button>)}
              </span>
              {tab === 'option' ? '的平值看涨，' : '，'}
            </span>
            {tab === 'option' ? (
              <>
                <span className="ask-group">期权费
                  <span className="ask-fee"><input inputMode="decimal" value={fee} onChange={e => setFee(e.target.value)} aria-label="期权费（%）" />%</span>，
                </span>
                <span>值不值？</span>
              </>
            ) : <span>涨的可能大吗？</span>}
          </div>
          {tab === 'option' && !feeOk && <p className="ask-error">期权费请填 0 到 100 之间的数字</p>}
          <button className="btn primary lg ask-go" disabled={!code || (tab === 'option' && !feeOk)} onClick={submit}>问小四<ArrowRight size={17} /></button>
        </div>
      )}
    </section>
  )
}
