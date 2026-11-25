/** Canvas 图表用的颜色（与 styles/tokens.css 保持一致；ECharts 无法读取 CSS 变量）。 */
export const PALETTE = {
  surface: '#fffdf9',
  ink: '#1d211e',
  ink2: '#3a3f3b',
  muted: '#7b8179',
  faint: '#a9ada3',
  line: '#e2ded4',
  accent: '#c8442f',
  up: '#c23a30',
  down: '#2a7a4b',
  flat: '#948e83',
  series: ['#2a78d6', '#eda100', '#6250d6'],
  serif: '"Sixiang Serif", "Noto Serif SC", "Songti SC", serif',
  sans: '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
} as const
