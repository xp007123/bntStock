import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts'
import { AxisPointerComponent, DataZoomComponent, GridComponent, MarkPointComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { Bar } from '../api/client'
import { sma } from '../lib/indicators'
import { fmtBig, fmtPct, fmtPrice } from '../lib/format'
import './KLineChart.css'

echarts.use([CandlestickChart, BarChart, LineChart, GridComponent, TooltipComponent, DataZoomComponent, AxisPointerComponent, MarkPointComponent, CanvasRenderer])

const MA = [
  { n: 5, color: 'var(--series-1)', hex: '#2a78d6' },
  { n: 10, color: 'var(--series-2)', hex: '#eda100' },
  { n: 20, color: 'var(--series-3)', hex: '#6250d6' },
]
const C = { up: '#d23b33', down: '#1e8a4c', grid: '#e4e6df', axis: '#7b8179', surface: '#ffffff', ink: '#272b28' }

type Props = {
  bars: Bar[]
  height?: number
  showVolume?: boolean
  ariaLabel: string
  /** 需要标注的日期（如形态入选日） */
  marks?: string[]
  /** 初始视图对准的日期 */
  focus?: string
}

/** 日 K 线：红涨（空心）绿跌（实心），MA5/10/20，成交量。悬停显示当日数值。 */
export default function KLineChart({ bars, height = 420, showVolume = true, ariaLabel, marks, focus }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts>()

  const series = useMemo(() => {
    const closes = bars.map(b => b.close)
    return { ma: MA.map(m => sma(closes, m.n)) }
  }, [bars])

  useEffect(() => {
    if (!ref.current) return
    chart.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); chart.current?.dispose() }
  }, [])

  useEffect(() => {
    if (!chart.current) return
    const dates = bars.map(b => b.date)
    const isUp = (b: Bar) => b.close >= b.open
    let start = bars.length > 120 ? 100 - (120 / bars.length) * 100 : 0
    let end = 100
    const fi = focus ? dates.indexOf(focus) : -1
    if (fi >= 0 && bars.length > 120) {
      // 入选日放在视图偏左，右侧留出之后的走势
      const lo = Math.max(0, Math.min(fi - 60, bars.length - 120))
      start = (lo / bars.length) * 100
      end = ((lo + 120) / bars.length) * 100
    }
    const markSet = new Set(marks ?? [])
    const markData = bars.flatMap((b, i) => markSet.has(b.date) ? [{
      coord: [i, b.high], value: b.date === focus ? '入选' : '',
      itemStyle: { color: b.date === focus ? '#e65336' : '#e6533699' },
      symbolSize: b.date === focus ? 30 : 14,
    }] : [])
    const priceGrid = showVolume ? { left: 8, right: 56, top: 12, height: '64%' } : { left: 8, right: 56, top: 12, bottom: 48 }
    chart.current.setOption({
      animation: false,
      textStyle: { fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif' },
      grid: showVolume ? [priceGrid, { left: 8, right: 56, top: '76%', height: '14%' }] : [priceGrid],
      axisPointer: { link: [{ xAxisIndex: 'all' }], label: { backgroundColor: C.ink } },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', lineStyle: { color: C.axis, type: 'dashed' } },
        backgroundColor: C.surface, borderColor: C.grid, textStyle: { color: C.ink, fontSize: 12 },
        formatter: (params: { dataIndex: number }[]) => {
          const i = params[0]?.dataIndex
          const b = bars[i]
          if (!b) return ''
          const base = b.prev_close ?? bars[i - 1]?.close
          const chg = base ? b.close / base - 1 : null
          const color = chg == null || chg === 0 ? C.ink : chg > 0 ? C.up : C.down
          return `<b>${b.date}</b><br/>开 ${fmtPrice(b.open)}　高 ${fmtPrice(b.high)}<br/>低 ${fmtPrice(b.low)}　收 <b style="color:${color}">${fmtPrice(b.close)}</b><br/>涨跌 <span style="color:${color}">${fmtPct(chg)}</span><br/>成交额 ${fmtBig(b.amount)}`
        },
      },
      xAxis: [0, ...(showVolume ? [1] : [])].map(g => ({
        type: 'category', data: dates, gridIndex: g, boundaryGap: true,
        axisLine: { lineStyle: { color: C.grid } }, axisTick: { show: false },
        axisLabel: { show: g === (showVolume ? 1 : 0), color: C.axis }, splitLine: { show: false },
      })),
      yAxis: [
        { scale: true, position: 'right', gridIndex: 0, splitLine: { lineStyle: { color: C.grid } }, axisLabel: { color: C.axis }, axisLine: { show: false } },
        ...(showVolume ? [{ gridIndex: 1, position: 'right', splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false }, axisLine: { show: false } }] : []),
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: showVolume ? [0, 1] : [0], start, end },
        { type: 'slider', xAxisIndex: showVolume ? [0, 1] : [0], start, end, height: 18, bottom: 4, borderColor: C.grid, showDetail: false },
      ],
      series: [
        {
          type: 'candlestick', name: 'K', data: bars.map(b => [b.open, b.close, b.low, b.high]),
          itemStyle: { color: C.surface, color0: C.down, borderColor: C.up, borderColor0: C.down, borderWidth: 1 },
          markPoint: markData.length ? {
            symbol: 'pin', symbolOffset: [0, -4], data: markData,
            label: { color: '#fff', fontSize: 10 }, animation: false, tooltip: { show: false },
          } : undefined,
        },
        ...MA.map((m, k) => ({
          type: 'line', name: `MA${m.n}`, data: series.ma[k], showSymbol: false, smooth: false,
          lineStyle: { width: 1.5, color: m.hex }, emphasis: { disabled: true },
        })),
        ...(showVolume ? [{
          type: 'bar', name: '成交量', xAxisIndex: 1, yAxisIndex: 1,
          data: bars.map(b => ({ value: b.volume, itemStyle: { color: isUp(b) ? C.up : C.down, opacity: .55 } })),
        }] : []),
      ],
    }, true)
  }, [bars, series, showVolume, marks, focus])

  const last = bars.length - 1
  return (
    <div className="kline">
      <div className="kline-legend" aria-hidden="true">
        {MA.map((m, k) => (
          <span key={m.n}><i style={{ background: m.color }} />MA{m.n} <b className="num">{fmtPrice(series.ma[k][last])}</b></span>
        ))}
      </div>
      <div ref={ref} style={{ height }} role="img" aria-label={ariaLabel} />
    </div>
  )
}
