import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { YearRow } from '../../api/client'
import { fmtPct } from '../../lib/format'
import { PALETTE as P } from '../../lib/palette'

echarts.use([BarChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])

/** 逐年平均收益：红为正、绿为负。悬停查看样本数与上涨比例。 */
export default function YearChart({ rows, horizon }: { rows: YearRow[]; horizon: number }) {
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
    const data = rows.filter(r => r.horizon === horizon)
    chart.current?.setOption({
      animation: false,
      textStyle: { fontFamily: P.sans },
      grid: { left: 48, right: 12, top: 12, bottom: 28 },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: P.surface, borderColor: P.line, borderRadius: 12, padding: [10, 14], textStyle: { color: P.ink, fontSize: 12 },
        formatter: (p: { dataIndex: number }[]) => {
          const r = data[p[0].dataIndex]
          return `<b>${r.year} 年</b><br/>平均涨跌 ${fmtPct(r.mean)}<br/>在涨的比例 ${fmtPct(r.win_rate, 1, false)}<br/>算了 ${r.valid} 次`
        },
      },
      xAxis: { type: 'category', data: data.map(r => r.year), axisLine: { lineStyle: { color: P.line } }, axisTick: { show: false }, axisLabel: { color: P.muted } },
      yAxis: { type: 'value', axisLabel: { color: P.muted, formatter: (v: number) => `${(v * 100).toFixed(0)}%` }, splitLine: { lineStyle: { color: P.line } } },
      series: [{
        type: 'bar', barMaxWidth: 22,
        data: data.map(r => ({ value: r.mean, itemStyle: { color: (r.mean ?? 0) >= 0 ? P.up : P.down, borderRadius: (r.mean ?? 0) >= 0 ? [6, 6, 0, 0] : [0, 0, 6, 6] } })),
      }],
    }, true)
  }, [rows, horizon])
  return <div ref={ref} style={{ height: 220 }} role="img" aria-label={`逐年 ${horizon} 日平均收益`} />
}
