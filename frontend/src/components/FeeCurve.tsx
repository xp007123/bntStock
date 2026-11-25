import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { PALETTE as P } from '../lib/palette'
import { fmtPct } from '../lib/format'
import './FeeCurve.css'

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])

type Point = { fee: number; similar: number; all: number; payoff_mean: number }

/**
 * 期权费一条线看完：横轴期权费 1%–15%，纵轴回本的比例。
 * 橙线是“和现在相似的时候”，灰虚线是“随便哪天买”。竖线是你现在问的价位；点线上任意一处换成那个价位重算。
 */
export default function FeeCurve({ curve, fee, onPick }: { curve: Point[]; fee: number; onPick?: (feePct: number) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const pickRef = useRef(onPick)
  pickRef.current = onPick
  const pct = (v: number) => Number((v * 100).toFixed(1))

  useEffect(() => {
    if (!box.current) return
    const c = echarts.init(box.current, undefined, { renderer: 'canvas' })
    chart.current = c
    const ro = new ResizeObserver(() => c.resize())
    ro.observe(box.current)
    c.getZr().on('click', e => {
      const at = c.convertFromPixel({ seriesIndex: 0 }, [e.offsetX, e.offsetY])
      if (!at || !pickRef.current) return
      const x = Math.round(at[0] * 2) / 2                 // 吸到 0.5% 一档
      if (x >= 1 && x <= 15) pickRef.current(x)
    })
    return () => { ro.disconnect(); c.dispose(); chart.current = null }
  }, [])

  useEffect(() => {
    chart.current?.setOption({
      animation: false,
      textStyle: { fontFamily: P.sans },
      grid: { left: 8, right: 24, top: 24, bottom: 8, containLabel: true },
      xAxis: { type: 'value', min: 1, max: 15, interval: 2, axisLine: { lineStyle: { color: P.line } }, axisTick: { show: false },
               axisLabel: { color: P.muted, fontSize: 11, formatter: '{value}%' }, splitLine: { show: false } },
      yAxis: { type: 'value', min: 0, max: 100, interval: 25, axisLabel: { color: P.muted, fontSize: 11, formatter: '{value}%' },
               splitLine: { lineStyle: { color: P.line } } },
      tooltip: {
        trigger: 'axis', backgroundColor: P.surface, borderColor: P.line, borderRadius: 12, padding: [8, 12], textStyle: { color: P.ink, fontSize: 12 },
        axisPointer: { type: 'line', lineStyle: { color: P.faint } },
        formatter: (ps: { dataIndex: number }[]) => {
          const p = curve[ps[0]?.dataIndex ?? 0]
          return `期权费 <b>${pct(p.fee)}%</b><br/>相似的时候回本：<b>${Math.round(p.similar * 100)}%</b><br/>`
            + `随便哪天买回本：${Math.round(p.all * 100)}%<br/>扣费后平均：${fmtPct(p.payoff_mean, 1)}<br/><span style="color:${P.muted}">点一下按这个价位重算</span>`
        },
      },
      series: [
        { name: '和现在相似的时候', type: 'line', data: curve.map(c => [pct(c.fee), c.similar * 100]), showSymbol: false, symbolSize: 8,
          lineStyle: { width: 2.5, color: P.accent }, itemStyle: { color: P.accent }, z: 3,
          markLine: { silent: true, symbol: 'none', lineStyle: { color: P.ink, type: 'solid', width: 1 },
                      label: { formatter: `你问的 ${pct(fee)}%`, color: P.ink, fontSize: 11, fontWeight: 600 },
                      data: [{ xAxis: pct(fee) }] } },
        { name: '随便哪天买', type: 'line', data: curve.map(c => [pct(c.fee), c.all * 100]), showSymbol: false,
          lineStyle: { width: 1.5, color: P.muted, type: 'dashed' }, itemStyle: { color: P.muted }, z: 2 },
      ],
    }, true)
  }, [curve, fee])

  const half = [...curve].reverse().find(c => c.similar >= 0.5)
  const even = [...curve].reverse().find(c => c.payoff_mean >= 0)
  return (
    <div className="fee-curve">
      <p className="fc-legend">
        <span><i className="ln accent" />和现在相似的时候</span>
        <span><i className="ln dashed" />随便哪天买</span>
      </p>
      <div ref={box} className="fc-chart" role="img" aria-label="期权费从 1% 到 15%，各自的回本比例" />
      <p className="fc-read">
        {half ? <>期权费在 <b>{pct(half.fee)}%</b> 以内，相似的时候里回本的超过一半。</> : <>期权费哪怕只有 1%，相似的时候里回本的也不到一半。</>}
        {even ? <> 扣掉期权费后平均不亏的最高价位约 <b>{pct(even.fee)}%</b>。</> : <> 在 1%–15% 之间，扣掉期权费后平均都是亏的。</>}
      </p>
    </div>
  )
}
