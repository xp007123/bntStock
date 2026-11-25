import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import { useSecurity } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import { displayCode } from '../../lib/format'
import { optionHorizons, stockHorizons } from '../ask/horizons'

type Tab = 'stock' | 'option' | 'method'

/** 结构化提问：选股票、期限（期权再填期权费），交给小四算。自由对话在下一版开放。 */
export default function AskPanel() {
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
        {([['stock', '问个股'], ['option', '问期权'], ['method', '问方法']] as const).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => pick(k)}>{label}</button>
        ))}
      </div>

      {tab === 'method' ? (
        <div className="ask-body">
          <p className="ask-sentence">我常用的一个买点，过去 17 年到底灵不灵？</p>
          <p className="muted ask-hint">在“形态”里选一个模板，调成你习惯的参数，小四会扫描全市场 2007 年以来的历史，告诉你它出现之后大多怎么样。</p>
          <button className="btn primary ask-go" onClick={submit}>去验证我的方法</button>
        </div>
      ) : (
        <div className="ask-body">
          <div className="ask-sentence">
            {code ? (
              <span className="ask-chip"><b>{sec.data?.name ?? '…'}</b><span className="num">{displayCode(code)}</span>
                <button aria-label="换一只" onClick={() => setCode('')}><X size={14} /></button></span>
            ) : <StockSearch onPick={setCode} />}
            <span>{tab === 'option' ? '买' : '接下来'}</span>
            <span className="ask-select">
              {horizons.map(o => <button key={o.value} aria-pressed={h === o.value} onClick={() => setH(o.value)}>{o.label.trim()}</button>)}
            </span>
            {tab === 'option' ? (
              <>
                <span>的平值看涨，期权费</span>
                <span className="ask-fee"><input inputMode="decimal" value={fee} onChange={e => setFee(e.target.value)} aria-label="期权费（%）" />%</span>
                <span>，值不值？</span>
              </>
            ) : <span>，涨的可能大吗？</span>}
          </div>
          {tab === 'option' && !feeOk && <p className="state error" style={{ padding: 0, textAlign: 'left' }}>期权费请填 0 到 100 之间的数字</p>}
          <button className="btn primary ask-go" disabled={!code || (tab === 'option' && !feeOk)} onClick={submit}>问小四</button>
        </div>
      )}
    </section>
  )
}
