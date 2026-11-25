import { useState } from 'react'
import type { DistStats } from '../api/client'
import './Distribution.css'

type Zone = { key: string; label: string; color: string }

/** 结果分几种：一条占比条 + 对应颜色的直方图。悬停显示每一档的次数与占比。 */
export default function Distribution({ stats, line, lineLabel }: { stats: DistStats; line?: number; lineLabel?: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const zones: Zone[] = line != null
    ? [{ key: 'down', label: '跌了', color: 'var(--down)' }, { key: 'up_not_breakeven', label: '涨了，但没回本', color: 'var(--flat)' },
       { key: 'breakeven', label: '回本', color: 'var(--up)' }]
    : [{ key: 'down', label: '跌了', color: 'var(--down)' }, { key: 'up', label: '涨了', color: 'var(--up)' }]
  const bins = stats.histogram
  const lo = bins[0].from, hi = bins[bins.length - 1].to
  const max = Math.max(...bins.map(b => b.n), 1)
  const W = 720, H = 190, pt = 8, pb = 24
  const x = (v: number) => (v - lo) / (hi - lo) * W
  const y = (n: number) => pt + (1 - n / max) * (H - pt - pb)
  const colorOf = (b: { from: number; to: number }) =>
    b.to <= 0 ? 'var(--down)' : line != null && b.from < line ? 'var(--flat)' : 'var(--up)'
  const ticks = [-0.4, -0.2, 0, 0.2, 0.4, 0.6].filter(t => t >= lo && t <= hi)
  const hb = hover != null ? bins[hover] : null

  return (
    <div className="dist">
      <div className="dist-zones" aria-hidden="true">
        {zones.map(z => <i key={z.key} style={{ width: `${(stats.zones[z.key] ?? 0) * 100}%`, background: z.color }} />)}
      </div>
      <div className="dist-zone-labels">
        {zones.map(z => (
          <span key={z.key} style={{ width: `${(stats.zones[z.key] ?? 0) * 100}%` }}>
            <b className="num">{Math.round((stats.zones[z.key] ?? 0) * 100)}%</b>{z.label}
          </span>
        ))}
      </div>
      <div className="dist-chart">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="到期涨跌幅的分布" onMouseLeave={() => setHover(null)}>
          {bins.map((b, i) => (
            <g key={i} onMouseEnter={() => setHover(i)}>
              {b.n > 0 && <rect x={x(b.from) + 1.5} y={y(b.n)} width={x(b.to) - x(b.from) - 3} height={y(0) - y(b.n)} fill={colorOf(b)} opacity={hover == null || hover === i ? .9 : .45} />}
              <rect x={x(b.from)} y={pt} width={x(b.to) - x(b.from)} height={H - pt - pb} fill="transparent" />
            </g>
          ))}
          <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--ink)" />
          {line != null && <>
            <line x1={x(line)} x2={x(line)} y1={pt - 4} y2={y(0)} stroke="var(--ink)" strokeDasharray="3 3" />
            <text x={x(line) + 6} y={pt + 8} className="dist-axis" fill="var(--ink)">{lineLabel}</text>
          </>}
          {ticks.map(t => <text key={t} x={x(t)} y={H - 6} textAnchor={t === lo ? 'start' : t === hi ? 'end' : 'middle'} className="dist-axis">{t > 0 ? '+' : ''}{Math.round(t * 100)}%</text>)}
        </svg>
        <p className="dist-hover" aria-live="polite">
          {hb ? <>涨跌在 {Math.round(hb.from * 100)}% 到 {Math.round(hb.to * 100)}% 之间：<b className="num">{hb.n}</b> 次，占 {(hb.n / stats.n * 100).toFixed(1)}%</>
              : <>把鼠标放在柱子上看具体次数。超过 ±40%/+60% 的极端情况并入两端。</>}
        </p>
      </div>
    </div>
  )
}
