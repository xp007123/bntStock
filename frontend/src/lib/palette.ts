/** Canvas 图表用的颜色（与 styles/tokens.css 保持一致；ECharts 无法读取 CSS 变量）。 */
export const PALETTE = {
  surface: '#ffffff',
  ink: '#190300',
  ink2: '#4a3a34',
  muted: '#7d6b62',
  faint: '#b3a39a',
  line: '#f1e5db',
  accent: '#fb5e0d',
  up: '#e0203a',
  down: '#0a8754',
  flat: '#a39a94',
  series: ['#190300', '#2a78d6', '#8b5cf6'],
  sans: '"Outfit", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif',
} as const
