import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { AxisPointerComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { PickSim } from '../../api/client'
import { PALETTE as P } from '../../lib/palette'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, AxisPointerComponent, CanvasRenderer])

const pct = (v: number | null | undefined, sign = true) => (v == null ? '—' : `${sign && v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)
const BENCH = ['#8a7d76', '#c4b8b0']

/** 仿真模拟盘的累计收益（上）和回撤（下）。同期指数做对照，灰色。 */
export default function SimChart({ sim, name }: { sim: PickSim; name: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts>()
  useEffect(() => {
    if (!ref.current) return
    chart.current = echarts.init(ref.current)
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); chart.current?.dispose() }
  }, [])
  useEffect(() => {
    const cum = (arr: (number | null)[]) => arr.map(v => (v == null ? null : +(v - 1).toFixed(5)))
    const axis = { axisLine: { lineStyle: { color: P.line } }, axisTick: { show: false }, axisLabel: { color: P.muted, fontSize: 11 } }
    chart.current?.setOption({
      animation: false,
      textStyle: { fontFamily: P.sans },
      legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 14, itemHeight: 4, textStyle: { color: P.ink2, fontSize: 12 },
                data: [name, ...sim.benchmarks.map(b => `同期${b.name}`)] },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [{ left: 52, right: 16, top: 36, height: '58%' }, { left: 52, right: 16, top: '76%', bottom: 28 }],
      tooltip: {
        trigger: 'axis', backgroundColor: P.surface, borderColor: P.line, borderRadius: 12, padding: [10, 14], textStyle: { color: P.ink, fontSize: 12 },
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex
          const rows = [`<b>${sim.dates[i]}</b>`, `${name} 累计 ${pct(sim.nav[i] - 1)}`,
            ...sim.benchmarks.map(b => `同期${b.name} ${pct(b.nav[i] == null ? null : b.nav[i]! - 1)}`), `从高点回落 ${pct(-sim.drawdown[i], false)}`]
          return rows.join('<br/>')
        },
      },
      xAxis: [
        { type: 'category', data: sim.dates, boundaryGap: false, ...axis, axisLabel: { show: false } },
        { type: 'category', gridIndex: 1, data: sim.dates, boundaryGap: false, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: string) => v.slice(0, 7) } },
      ],
      yAxis: [
        { type: 'value', scale: true, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` }, splitLine: { lineStyle: { color: P.line } } },
        { type: 'value', gridIndex: 1, max: 0, splitNumber: 2, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` }, splitLine: { lineStyle: { color: P.line } } },
      ],
      series: [
        { name, type: 'line', data: cum(sim.nav), showSymbol: false, lineStyle: { width: 2.4, color: P.accent }, itemStyle: { color: P.accent },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(251,94,13,.18)' }, { offset: 1, color: 'rgba(251,94,13,0)' }]) }, z: 3 },
        ...sim.benchmarks.map((b, k) => ({ name: `同期${b.name}`, type: 'line', data: cum(b.nav), showSymbol: false, connectNulls: true,
                                           lineStyle: { width: 1.4, color: BENCH[k % BENCH.length] }, itemStyle: { color: BENCH[k % BENCH.length] } })),
        { name: '回撤', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: sim.drawdown.map(v => -v), showSymbol: false,
          lineStyle: { width: 1, color: P.down }, itemStyle: { color: P.down }, areaStyle: { color: 'rgba(10,135,84,.14)' } },
      ],
    }, true)
  }, [sim, name])
  return <div ref={ref} className="sim-chart" role="img" aria-label={`${name}仿真模拟盘的累计收益和回撤曲线`} />
}
