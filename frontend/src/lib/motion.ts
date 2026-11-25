import { useEffect, useRef, useState } from 'react'

/** 用户要求减少动效，或页面当前没在渲染时，跳过所有编排好的动效。 */
export const motionOff = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('still')

/**
 * 数字从“上一个真实值”滚到“新的真实值”。第一次出现时直接显示，不从 0 滚（不显示不存在的数字）。
 */
export function useRolling(value: number, ms = 640) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    const start = from.current
    if (start === value) return
    if (motionOff()) { from.current = value; setShown(value); return }
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / ms)
      const eased = 1 - Math.pow(1 - p, 3)
      const v = start + (value - start) * eased
      from.current = v
      setShown(p === 1 ? value : v)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, ms])
  return shown
}

// ---- 揭晓看过没有：只记在这台设备上，决定要不要播放揭晓过程
const KEY = 'sixiang.revealed'
const read = (): number[] => { try { return JSON.parse(localStorage.getItem(KEY) ?? '[]') } catch { return [] } }
export const isRevealed = (id: number) => read().includes(id)
export const markRevealed = (id: number) => {
  const ids = read()
  if (!ids.includes(id)) { try { localStorage.setItem(KEY, JSON.stringify([...ids, id].slice(-500))) } catch { /* 存不下就每次都播 */ } }
}
