import type { Judgment, Stance } from '../api/client'

/** 封存时让用户自己表个态：点一下。个股说“会不会涨”，期权说“能不能回本”。 */
export const stanceChoices = (option: boolean): { id: Stance; label: string }[] => [
  { id: 'yes', label: option ? '我觉得能回本' : '我觉得会涨' },
  { id: 'no', label: option ? '我觉得回不了本' : '我觉得不会涨' },
  { id: 'follow', label: '听小四的' },
]

export const stanceText = (s: Stance | null | undefined, option: boolean) =>
  s === 'yes' ? (option ? '能回本' : '会涨') : s === 'no' ? (option ? '回不了本' : '不会涨') : s === 'follow' ? '听小四的' : null

/** 小四的倾向：概率过半算“会”。和后端档案统计用同一个口径。 */
export const xiaosiLean = (prob: number) => prob >= 0.5
export const leanText = (prob: number, option: boolean) =>
  xiaosiLean(prob) ? (option ? '多半能回本' : '多半会涨') : (option ? '多半回不了本' : '多半不会涨')

/** 揭晓后：我说对了吗。没表态、听小四的、还没揭晓时返回 null。 */
export const mineRight = (j: Judgment): boolean | null => {
  const s = j.prediction.stance
  if (!j.outcome?.done || (s !== 'yes' && s !== 'no')) return null
  return (s === 'yes') === j.outcome.hit
}
export const xiaosiRight = (j: Judgment): boolean | null =>
  j.outcome?.done ? xiaosiLean(j.prediction.prob) === j.outcome.hit : null
