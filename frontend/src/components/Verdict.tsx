import { useEffect, useRef } from 'react'
import { useRolling } from '../lib/motion'
import './Verdict.css'

/**
 * 先结论：墨黑大卡上一个大数字 + 一句大白话 + 一行补充说明。
 * dots 传 0–100 时显示百点图（“每 100 次里有 N 次”），比百分比更直观。
 * 概率不是涨跌，所以数字用暖白、点阵用焦橙；只有传 tone 时才用红绿。
 * 数值变化时（比如换了期限），数字从旧值滚到新值，点阵多亮或少亮几颗。
 */
export default function Verdict({ label, value, unit = '%', plain, note, dots, dotsCaption, tone, tag, pending = false }: {
  label: string
  value: string
  unit?: string
  plain: React.ReactNode
  note?: React.ReactNode
  dots?: number | null
  dotsCaption?: React.ReactNode
  tone?: 'up' | 'down'
  /** 右上角的一句结论标签，如“和随便买差不多” */
  tag?: React.ReactNode
  /** 新的结果还在算：先把旧的压暗，算完再滚过去 */
  pending?: boolean
}) {
  const target = Number(value)
  const numeric = Number.isFinite(target)
  const digits = numeric ? (value.split('.')[1]?.length ?? 0) : 0
  const rolled = useRolling(numeric ? target : 0)
  const on = dots == null ? 0 : Math.round(dots)
  const prevOn = useRef<number | null>(null)
  const before = prevOn.current
  useEffect(() => { prevOn.current = on }, [on])

  return (
    <section className={`verdict fade-in ${pending ? 'pending' : ''}`} aria-label={label} aria-busy={pending}>
      <header className="verdict-head">
        <span className="verdict-label">{label}</span>
        {tag && <span className="verdict-tag">{tag}</span>}
      </header>
      <div className={`verdict-figure num ${tone ?? ''}`}>{numeric ? rolled.toFixed(digits) : value}{unit && <small>{unit}</small>}</div>
      {dots != null && (
        <div className="verdict-dots" aria-label={typeof dotsCaption === 'string' ? dotsCaption : undefined}>
          <div className="grid" aria-hidden="true">
            {Array.from({ length: 100 }, (_, i) => (
              <i key={i} className={i < on ? 'on' : ''}
                 style={i < on ? { animationDelay: `${before == null ? 120 + i * 7 : Math.max(0, i - before) * 16}ms` } : undefined} />
            ))}
          </div>
          {dotsCaption && <span className="cap">{dotsCaption}</span>}
        </div>
      )}
      <p className="verdict-plain">{plain}{note && <span>{note}</span>}</p>
    </section>
  )
}
