import './Verdict.css'

/**
 * 先结论：一个大数字 + 一句大白话 + 一行补充说明。
 * dots 传 0–100 时显示百点图（“每 100 次里有 N 次”），比百分比更直观。
 */
export default function Verdict({ label, value, unit = '%', plain, note, dots, dotsCaption, tone }: {
  label: string
  value: string
  unit?: string
  plain: React.ReactNode
  note?: React.ReactNode
  dots?: number | null
  dotsCaption?: React.ReactNode
  tone?: 'up' | 'down'
}) {
  return (
    <section className="verdict fade-in" aria-label={label}>
      <span className="eyebrow verdict-label">{label}</span>
      <div className={`verdict-figure num ${tone ?? ''}`}>{value}{unit && <small>{unit}</small>}</div>
      {dots != null && (
        <div className="verdict-dots" aria-label={typeof dotsCaption === 'string' ? dotsCaption : undefined}>
          <div className="grid" aria-hidden="true">
            {Array.from({ length: 100 }, (_, i) => <i key={i} className={i < Math.round(dots) ? 'on' : ''} />)}
          </div>
          {dotsCaption && <span className="cap">{dotsCaption}</span>}
        </div>
      )}
      <p className="verdict-plain">{plain}{note && <span>{note}</span>}</p>
    </section>
  )
}
