/** 期限选项（交易日）。与后端 narrative.horizon_text 保持一致。 */
export const stockHorizons = [
  { value: 5, label: ' 1 周' }, { value: 10, label: ' 2 周' }, { value: 21, label: ' 1 个月' }, { value: 63, label: ' 3 个月' },
]
export const optionHorizons = [
  { value: 21, label: ' 1 个月' }, { value: 42, label: ' 2 个月' }, { value: 63, label: ' 3 个月' }, { value: 126, label: ' 6 个月' },
]

const NAMES: Record<number, string> = { 5: '1 周', 10: '2 周', 21: '1 个月', 42: '2 个月', 63: '3 个月', 126: '6 个月', 250: '1 年' }
export const horizonText = (h: number) => NAMES[h] ?? `${h} 个交易日`
