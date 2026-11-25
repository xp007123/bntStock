import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts/core'
import { LineChart, ScatterChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, MarkAreaComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useSeries } from '../api/client'
import { fmtPct, fmtPrice, trendClass } from '../lib/format'
import { PALETTE as P } from '../lib/palette'
import './SimilarTimes.css'

echarts.use([LineChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent, CanvasRenderer])

type Props = {
  code: string
  index?: boolean
  horizon: number
  horizonLabel: string
  /** [日期, 之后 N 个交易日的涨跌]，来自收益分布引擎 */
  points: [string, number][]
}

/**
 * “和现在相似的时候”画在走势上：每个红点 / 绿点是历史上和现在很像的一天，红的之后涨了，绿的之后跌了。
 * 点一个，下面回放那一天之后 N 个交易日是怎么走的。
 */
export default function SimilarTimes({ code, index = false, horizon, horizonLabel, points }: Props) {
  const series = useSeries(code, index)
  const box = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const [sel, setSel] = useState(points.length - 1)
  useEffect(() => setSel(points.length - 1), [points])

  const at = useMemo(() => {
    const m = new Map<string, number>()
    series.data?.dates.forEach((d, i) => m.set(d, i))
    return m
  }, [series.data])
  const up = points.filter(p => p[1] > 0).length

  useEffect(() => {
    if (!box.current) return
    chart.current = echarts.init(box.current, undefined, { renderer: 'canvas' })
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(box.current)
    chart.current.on('click', 'series.scatter', (e: { dataIndex: number }) => setSel(e.dataIndex))
    return () => { ro.disconnect(); chart.current?.dispose(); chart.current = null }
  }, [])

  const s = series.data
  const pick = points[sel]
  const start = pick ? at.get(pick[0]) : undefined

  useEffect(() => {
    if (!chart.current || !s) return
    const dots = points.map(([d, r]) => {
      const i = at.get(d)
      return { value: [d, i == null ? null : s.close[i]], ret: r,
               itemStyle: { color: r > 0 ? P.up : P.down, borderColor: P.surface, borderWidth: 1.5 } }
    })
    const end = start == null ? undefined : s.dates[Math.min(s.dates.length - 1, start + horizon)]
    chart.current.setOption({
      animation: false,
      textStyle: { fontFamily: P.sans },
      grid: { left: 8, right: 16, top: 16, bottom: 28, containLabel: true },
      xAxis: { type: 'category', data: s.dates, boundaryGap: false, axisLine: { lineStyle: { color: P.line } }, axisTick: { show: false },
               axisLabel: { color: P.muted, fontSize: 11, formatter: (v: string) => v.slice(0, 4), interval: 'auto', hideOverlap: true } },
      yAxis: { type: 'log', min: (v: { min: number }) => v.min * 0.92, max: (v: { max: number }) => v.max * 1.08, splitNumber: 4,
               splitLine: { lineStyle: { color: P.line } }, axisLabel: { color: P.muted, fontSize: 11, formatter: (v: number) => (v >= 100 ? String(Math.round(v)) : v.toFixed(1)), showMinLabel: false, showMaxLabel: false } },
      dataZoom: [{ type: 'inside', minValueSpan: 120 }],
      tooltip: {
        trigger: 'item', backgroundColor: P.surface, borderColor: P.line, borderRadius: 12, padding: [8, 12], textStyle: { color: P.ink, fontSize: 12 },
        formatter: (p: { seriesType: string; data: { value: [string, number]; ret: number } }) =>
          p.seriesType === 'scatter' ? `${p.data.value[0]}<br/>之后${horizonLabel}：<b>${fmtPct(p.data.ret, 1)}</b><br/><span style="color:${P.muted}">点一下看它怎么走的</span>` : '',
      },
      series: [
        { type: 'line', data: s.close, showSymbol: false, lineStyle: { width: 1.5, color: P.ink2 }, silent: true, z: 1,
          markArea: start == null ? undefined : { silent: true, itemStyle: { color: '#fb5e0d1f' }, data: [[{ xAxis: s.dates[start] }, { xAxis: end }]] } },
        { type: 'scatter', data: dots, symbolSize: (_: unknown, p: { dataIndex: number }) => (p.dataIndex === sel ? 14 : 8), z: 3,
          emphasis: { scale: 1.4 }, cursor: 'pointer' },
      ],
    }, true)
  }, [s, points, at, sel, start, horizon, horizonLabel])

  const path = useMemo(() => {
    if (!s || start == null) return null
    const seg = s.close.slice(start, start + horizon + 1)
    return seg.map(v => v / seg[0] - 1)
  }, [s, start, horizon])

  if (series.isError) return <p className="muted">走势读取失败</p>
  const step = (d: number) => setSel(i => Math.max(0, Math.min(points.length - 1, i + d)))

  return (
    <div className="similar-times">
      <p className="st-legend">
        <span><i className="dot up" />之后涨了 <b className="num">{up}</b> 个</span>
        <span><i className="dot down" />之后跌了 <b className="num">{points.length - up}</b> 个</span>
        <span className="muted">滚轮可以放大某一段</span>
      </p>
      <div ref={box} className="st-chart" role="img" aria-label={`走势图上标出了 ${points.length} 个和现在相似的时候`} />
      {!s && <div className="state">读取走势…</div>}
      {pick && s && (
        <div className="st-pick">
          <button className="btn" aria-label="上一个" disabled={sel === 0} onClick={() => step(-1)}><ChevronLeft size={16} /></button>
          <div className="st-pick-text">
            <span className="muted">第 {sel + 1} / {points.length} 个</span>
            <p><b>{pick[0]}</b> 那天，走势和现在很像{start != null && <>（当时收盘 {fmtPrice(s.close[start])}）</>}。之后{horizonLabel}：
              <b className={`num ${trendClass(pick[1])}`}>{fmtPct(pick[1], 1)}</b></p>
          </div>
          {path && <PathSpark path={path} />}
          <button className="btn" aria-label="下一个" disabled={sel === points.length - 1} onClick={() => step(1)}><ChevronRight size={16} /></button>
        </div>
      )}
    </div>
  )
}

/** 那一天之后每天相对起点的涨跌，零线是起点 */
function PathSpark({ path }: { path: number[] }) {
  const W = 180, H = 48
  const lo = Math.min(0, ...path), hi = Math.max(0, ...path)
  const y = (v: number) => H - 4 - (v - lo) / (hi - lo || 1) * (H - 8)
  const x = (i: number) => i / Math.max(1, path.length - 1) * W
  const d = path.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const last = path[path.length - 1]
  return (
    <svg className="st-spark" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <line x1="0" x2={W} y1={y(0)} y2={y(0)} stroke={P.line} strokeDasharray="3 3" />
      <path d={d} fill="none" stroke={last > 0 ? P.up : P.down} strokeWidth="2" strokeLinejoin="round" />
      <circle cx={x(path.length - 1)} cy={y(last)} r="3.5" fill={last > 0 ? P.up : P.down} />
    </svg>
  )
}
