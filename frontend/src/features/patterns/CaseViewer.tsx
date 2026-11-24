import { X } from 'lucide-react'
import { useDaily, useExplain } from '../../api/client'
import KLineChart from '../../components/KLineChart'
import { displayCode, fmtPrice } from '../../lib/format'
import { opText } from './ruleText'

/** 单个案例：K 线标出全部入选日，并列出当天每个条件的实际数值。 */
export default function CaseViewer({ jobId, code, name, date, onClose }: { jobId: string; code: string; name: string; date: string; onClose: () => void }) {
  const daily = useDaily(code, 'qfq')
  const explain = useExplain(jobId, code, date)
  const bars = daily.data?.code === code ? daily.data.bars : []
  return (
    <section className="card case-viewer" aria-label="案例 K 线">
      <div className="card-title">
        <span>{name} <span className="muted num">{displayCode(code)}</span> · 入选日 {date}</span>
        <button className="btn" onClick={onClose} aria-label="关闭"><X size={15} /></button>
      </div>
      {bars.length ? <KLineChart bars={bars} height={340} marks={explain.data?.signal_dates} focus={date} ariaLabel={`${name} 日 K 线，标注形态入选日`} />
        : <div className="state">读取 K 线…</div>}
      {explain.isError && <p className="state error">{explain.error.message}</p>}
      {explain.data && (
        <table className="reason-table">
          <thead><tr><th>条件</th><th>左值</th><th></th><th>右值</th><th>结果</th></tr></thead>
          <tbody>
            {explain.data.conditions.map(c => (
              <tr key={c.label}>
                <td>{c.label}</td><td className="num">{fmtPrice(c.left, 4)}</td><td>{opText(c.op)}</td><td className="num">{fmtPrice(c.right, 4)}</td>
                <td>{c.passed ? '✓ 满足' : '✗ 不满足'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted footnote">K 线为前复权；条件按后复权价格计算，价格类数值与图上刻度不同属正常。红色图钉为全部入选日，较大的为当前案例。</p>
    </section>
  )
}
