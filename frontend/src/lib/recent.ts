import { useEffect, useState } from 'react'
import { useMe } from '../api/client'

/** 最近问过的问题：只存在这台电脑的浏览器里，按账号分开，最多 8 条，重复的挪到最前面。 */
export type RecentAsk = {
  kind: 'stock' | 'option' | 'index' | 'compare'
  /** 回答页的地址（含参数），点一下重问 */
  to: string
  /** 显示用：股票或指数名称，对比时是“A vs B” */
  title: string
  /** 显示用：问的是什么（“1 个月涨的可能”“期权费 7.5%”） */
  detail: string
  at: number
}

const MAX = 8
const key = (uid: number) => `sixiang.recent.${uid}`
const EVENT = 'sixiang-recent'

function read(uid: number): RecentAsk[] {
  try { return JSON.parse(localStorage.getItem(key(uid)) ?? '[]') as RecentAsk[] } catch { return [] }
}

export function remember(uid: number, ask: Omit<RecentAsk, 'at'>) {
  const list = [{ ...ask, at: Date.now() }, ...read(uid).filter(r => r.to !== ask.to)].slice(0, MAX)
  try { localStorage.setItem(key(uid), JSON.stringify(list)) } catch { /* 存不下就算了，不影响提问 */ }
  window.dispatchEvent(new Event(EVENT))
}

export function forget(uid: number) {
  localStorage.removeItem(key(uid))
  window.dispatchEvent(new Event(EVENT))
}

/** 当前账号最近问过的问题 */
export function useRecent(): { uid: number | null; items: RecentAsk[] } {
  const me = useMe()
  const uid = me.data?.id ?? null
  const [items, setItems] = useState<RecentAsk[]>([])
  useEffect(() => {
    if (uid == null) return
    const load = () => setItems(read(uid))
    load()
    window.addEventListener(EVENT, load)
    window.addEventListener('storage', load)
    return () => { window.removeEventListener(EVENT, load); window.removeEventListener('storage', load) }
  }, [uid])
  return { uid, items }
}

/** 回答出来后记一笔 */
export function useRemember(ask: Omit<RecentAsk, 'at'> | null) {
  const me = useMe()
  const uid = me.data?.id
  const sig = ask ? ask.to : ''
  useEffect(() => { if (uid != null && ask) remember(uid, ask) }, [uid, sig]) // eslint-disable-line react-hooks/exhaustive-deps
}
