import { useNavigate } from 'react-router-dom'
import { type Upside, useCheckup } from '../../api/client'
import { fmtPct, fmtPrice, trendClass } from '../../lib/format'
import DataCard from '../rooms/DataCard'
import '../rooms/rooms.css'

const pct = (v: number) => `${Math.round(v * 100)}%`

/**
 * 体检：同一只票从几个角度看。
 * - 几个期限一起给：在涨的比例，以及“十次里有八次”大概落在什么价位。
 * - 估值、买点、涨停、行业、概念、资金：每一项就是群聊角色用的那张数据卡，数字全部来自引擎和数据服务。
 * 取不到的那一项不显示。
 */
export default function Checkup({ code, horizon, option = false }: { code: string; horizon: number; option?: boolean }) {
  const q = useCheckup(code)
  const navigate = useNavigate()
  const d = q.data
  if (q.isLoading) return <section className="card ask-section"><h2>{option ? '上涨的依据' : '从几个角度看'}</h2><p className="muted">正在把几项数据凑齐…</p></section>
  if (!d || (d.horizons.length === 0 && d.items.length === 0)) return null
  return (
    <>
      {!option && d.horizons.length > 0 && (
        <section className="card ask-section">
          <h2>几个期限一起看</h2>
          <div className="table-wrap">
            <table className="ck-table">
              <thead><tr><th>期限</th><th>在涨的比例</th><th>平时</th><th>一半情况好于</th><th>十次里有八次落在</th></tr></thead>
              <tbody>
                {d.horizons.map(h => (
                  <tr key={h.horizon} className={h.horizon === horizon ? 'on' : ''} onClick={() => navigate(`/ask/stock?code=${code}&h=${h.horizon}`)} title="点一下按这个期限细看">
                    <td><b>{h.label}</b></td>
                    <td><span className="ck-bar"><i style={{ width: `${h.prob * 100}%` }} /><u style={{ left: `${h.base * 100}%` }} /></span><b className="num">{pct(h.prob)}</b></td>
                    <td className="num muted">{pct(h.base)}</td>
                    <td className={`num ${trendClass(h.median)}`}>{fmtPct(h.median, 1)}</td>
                    <td className="num">{fmtPrice(h.low)} – {fmtPrice(h.high)} 元</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted ck-foot">现价 {fmtPrice(d.horizons[0].close)} 元。价位是把历史上相似的时候的涨跌幅换算过来的：最差的一成和最好的一成不算在内。点某一行可以按那个期限细看。</p>
        </section>
      )}
      {d.items.length > 0 && (
        <section className="card ask-section">
          <h2>{option ? '上涨的依据：从几个角度看这只票' : '从几个角度看'}</h2>
          <div className="ck-grid">{d.items.map(i => <DataCard key={i.tool} card={i.card} />)}</div>
        </section>
      )}
    </>
  )
}

/** 问期权：涨到每一档的可能有多大。期权费只是其中一条线。 */
export function UpsideLadder({ up, fee, lock, horizonLabel }: { up: Upside; fee: number; lock: number; horizonLabel: string }) {
  const peak = up.peak
  const rows = [...up.ladder.map(r => ({ x: r.x, end: r.end, peak: r.peak, line: false })),
    { x: fee, end: up.end.over_fee, peak: peak?.over_fee, line: true }].sort((a, b) => a.x - b.x)
  const yuan = (m: number | null) => (m == null ? '—' : `${Math.round(m * 10000).toLocaleString()} 元`)
  return (
    <>
      <div className="up-ladder">
        <div className="up-head"><span /><span>{peak ? `中途到过（持有满 ${lock} 天后）` : ''}</span><span>到期时还在</span></div>
        {rows.map(r => (
          <div key={`${r.x}-${r.line}`} className={r.line ? 'line' : ''}>
            <span>{r.line ? `期权费 ${(r.x * 100).toFixed(1)}%（回本线）` : `涨超 ${Math.round(r.x * 100)}%`}</span>
            <span>{r.peak != null && <><i><b className="a" style={{ width: `${r.peak * 100}%` }} /></i><em className="num">{pct(r.peak)}</em></>}</span>
            <span><i><b style={{ width: `${r.end * 100}%` }} /></i><em className="num">{pct(r.end)}</em></span>
          </div>
        ))}
      </div>
      <p className="up-money">
        按花 <b>1 万元</b>期权费算（{horizonLabel}，没扣这 1 万本身）：一直拿到到期，{up.back.typical > 0 ? <>一半情况能拿回 <b className="num">{yuan(up.back.typical)}</b> 以上</> : <>有一半情况到期那天没涨、一分拿不回</>}，
        最好的两成 <b className="num">{yuan(up.back.good)}</b> 以上{up.back.peak_typical != null && <>；在中途最高的那天平仓，一半情况是 <b className="num">{yuan(up.back.peak_typical)}</b> 以上</>}。
        拿回的钱超过 1 万才算赚。
      </p>
      <p className="muted ck-foot">“中途到过”按收盘价算，从持有满 {lock} 个交易日那天到到期日。实际没人能正好卖在最高那天，这一列是上限，不是预期。</p>
    </>
  )
}
