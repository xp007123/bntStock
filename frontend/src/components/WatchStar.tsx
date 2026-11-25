import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Star } from 'lucide-react'
import { addWatch, ApiError, removeWatch, useWatchlist } from '../api/client'

/** 加自选 / 取消自选。放在股票名旁边。 */
export default function WatchStar({ code }: { code: string }) {
  const q = useWatchlist()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const on = !!q.data?.items.some(i => i.code === code)
  const toggle = async () => {
    setBusy(true); setError('')
    try { qc.setQueryData(['watchlist'], await (on ? removeWatch(code) : addWatch(code))) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return (
    <button className={`watch-star ${on ? 'on' : ''}`} aria-pressed={on} disabled={busy || !q.data} onClick={toggle} title={error || (on ? '从自选里拿掉' : '加到自选，首页每天能看到小四怎么看')}>
      <Star size={15} fill={on ? 'currentColor' : 'none'} />{error ? error : on ? '已自选' : '加自选'}
    </button>
  )
}
