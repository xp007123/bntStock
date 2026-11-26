import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, X } from 'lucide-react'
import { useIndices, useJudgments, useSecurity } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import { displayCode } from '../../lib/format'
import { optionHorizons, stockHorizons } from '../ask/horizons'

type Tab = 'stock' | 'option' | 'index' | 'method'
const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'stock', label: '问个股', hint: '还能涨吗' },
  { id: 'option', label: '问期权', hint: '能涨多少' },
  { id: 'index', label: '问大盘', hint: '接下来怎么走' },
  { id: 'method', label: '问方法', hint: '这招灵不灵' },
]

/** 结构化提问：选股票、期限（期权再填期权费），交给小四算。自由对话在下一版开放。 */
export default function AskPanel({ onPick }: { onPick?: () => void }) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('stock')
  const [code, setCode] = useState('')
  const [h, setH] = useState(21)
  const [fee, setFee] = useState('7.5')
  const [indexCode, setIndexCode] = useState('sh000001')
  const indices = useIndices()
  const sec = useSecurity(code || 'sh600519')
  // 还没封存过判断的新用户：默认问 1 周，这样下周就能经历第一次揭晓
  const judgments = useJudgments()
  const firstTime = judgments.data?.items.length === 0
  const touched = useRef(false)
  useEffect(() => { if (firstTime && !touched.current) setH(v => (v === 21 ? 5 : v)) }, [firstTime])
  const feeNum = Number(fee)
  const feeOk = Number.isFinite(feeNum) && feeNum > 0 && feeNum < 100
  const horizons = tab === 'option' ? optionHorizons : stockHorizons
  const pick = (t: Tab) => { setTab(t); if (t === 'option' && ![21, 42, 63, 126].includes(h)) setH(63); if (t !== 'option' && ![5, 10, 21, 63].includes(h)) setH(21) }

  const submit = () => {
    if (tab === 'method') return navigate('/patterns')
    if (tab === 'index') return navigate(`/ask/index?code=${indexCode}&h=${h}`)
    if (!code) return
    navigate(tab === 'option' ? `/ask/option?code=${code}&h=${h}&fee=${feeNum}` : `/ask/stock?code=${code}&h=${h}`)
  }

  const hText = horizons.find(o => o.value === h)?.label.trim() ?? ''
  const who = tab === 'index' ? (indices.data ?? []).find(i => i.code === indexCode)?.name ?? '' : code ? sec.data?.name ?? '…' : ''
  const ready = tab === 'method' || (tab === 'index' ? !!who : !!code && (tab !== 'option' || feeOk))
  const sentence = tab === 'method' ? '我常用的一个买点，历史上到底灵不灵？'
    : !who ? '先选一只股票'
    : tab === 'option' ? `${who} ${hText}平值看涨，期权费 ${feeOk ? feeNum : '?'}%，能涨多少？`
    : `${who}接下来 ${hText}，涨的可能大吗？`

  return (
    <section className="ask-panel" aria-label="向小四提问">
      <div className="ask-tabs" role="tablist">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => pick(t.id)}><b>{t.label}</b><span>{t.hint}</span></button>
        ))}
      </div>

      {/* 左边一行一项地填（标签对齐成一列），右边是“你要问的这句话”和按钮。四个标签同一个骨架，换标签时不跳动。 */}
      <div className="ask-body">
        <div className="ask-fields">
          {tab === 'method' ? (
            <>
              <div className="ask-field"><span className="ask-label">怎么问</span>
                <p className="ask-hint">在方法库里挑一种常见买法（放量突破、均线金叉、缩量回踩…），调成你习惯的参数。</p></div>
              <div className="ask-field"><span className="ask-label">小四做什么</span>
                <p className="ask-hint">扫一遍全市场 2007 年以来的历史，告诉你这个买点出现之后大多怎么样。</p></div>
            </>
          ) : (
            <>
              <div className="ask-field">
                <span className="ask-label">{tab === 'index' ? '指数' : '股票'}</span>
                {tab === 'index' ? (
                  <span className="ask-select ask-index">
                    {(indices.data ?? []).slice(0, 5).map(i => <button key={i.code} aria-pressed={indexCode === i.code} onClick={() => setIndexCode(i.code)}>{i.name}</button>)}
                  </span>
                ) : code ? (
                  <span className="ask-chip"><b>{sec.data?.name ?? '…'}</b><span className="num">{displayCode(code)}</span>
                    <button aria-label="换一只" onClick={() => setCode('')}><X size={14} /></button></span>
                ) : <StockSearch onPick={c => { setCode(c); onPick?.() }} />}
              </div>
              <div className="ask-field">
                <span className="ask-label">{tab === 'option' ? '期限' : '看多久'}</span>
                <span className="ask-select">
                  {horizons.map(o => <button key={o.value} aria-pressed={h === o.value} onClick={() => { touched.current = true; setH(o.value) }}>{o.label.trim()}</button>)}
                </span>
                {tab === 'option' && <span className="ask-note">平值看涨</span>}
              </div>
              {tab === 'option' && (
                <div className="ask-field">
                  <span className="ask-label">期权费</span>
                  <span className="ask-fee"><input inputMode="decimal" value={fee} onChange={e => setFee(e.target.value)} aria-label="期权费（%）" />%</span>
                  <span className={`ask-note ${feeOk ? '' : 'bad'}`}>{feeOk ? '券商报的价，占名义本金' : '请填 0 到 100 之间的数字'}</span>
                </div>
              )}
              {tab === 'stock' && firstTime && h === 5 && <p className="muted ask-first">第一次用？先问 1 周的：封存之后，下周就能回来看揭晓。</p>}
            </>
          )}
        </div>

        <div className="ask-ready">
          <span className="ask-ready-label">你要问的是</span>
          <p className={`ask-sentence ${ready ? '' : 'empty'}`}>{sentence}</p>
          <button className="btn primary lg ask-go" disabled={!ready} onClick={submit}>{tab === 'method' ? '去验证我的方法' : '问小四'}<ArrowRight size={17} /></button>
          {tab === 'stock' && <button className="ask-compare-link" onClick={() => navigate(`/ask/compare?${code ? `a=${code}&` : ''}h=${h}`)}>或者，拿两只对着问</button>}
        </div>
      </div>
    </section>
  )
}
