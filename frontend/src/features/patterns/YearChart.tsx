import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { YearRow } from '../../api/client'
import { fmtPct } from '../../lib/format'

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
      grid: { left: 48, right: 12, top: 12, bottom: 28 },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: '#fff', borderColor: '#e4e6df', textStyle: { color: '#272b28', fontSize: 12 },
        formatter: (p: { dataIndex: number }[]) => {
          const r = data[p[0].dataIndex]
          return `<b>${r.year} 年</b><br/>平均 ${fmtPct(r.mean)}<br/>上涨比例 ${fmtPct(r.win_rate, 1, false)}<br/>有效样本 ${r.valid}`
        },
      },
      xAxis: { type: 'category', data: data.map(r => r.year), axisLine: { lineStyle: { color: '#e4e6df' } }, axisTick: { show: false }, axisLabel: { color: '#7b8179' } },
      yAxis: { type: 'value', axisLabel: { color: '#7b8179', formatter: (v: number) => `${(v * 100).toFixed(0)}%` }, splitLine: { lineStyle: { color: '#e4e6df' } } },
      series: [{
        type: 'bar', barMaxWidth: 22,
        data: data.map(r => ({ value: r.mean, itemStyle: { color: (r.mean ?? 0) >= 0 ? '#d23b33' : '#1e8a4c', borderRadius: (r.mean ?? 0) >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] } })),
      }],
    }, true)
  }, [rows, horizon])
  return <div ref={ref} style={{ height: 220 }} role="img" aria-label={`逐年 ${horizon} 日平均收益`} />
}
