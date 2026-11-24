import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { useSecuritySearch } from '../api/client'
import { displayCode } from '../lib/format'
import './StockSearch.css'

/** 按代码或名称搜索股票。键盘上下选择，回车确认。 */
export default function StockSearch({ onPick }: { onPick: (code: string) => void }) {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const { data = [], isFetching } = useSecuritySearch(debounced)

  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 150); return () => clearTimeout(t) }, [q])
  useEffect(() => setActive(0), [debounced])
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const pick = (code: string) => { onPick(code); setQ(''); setOpen(false) }
  const hits = debounced ? data : []

  return (
    <div className="stock-search" ref={box}>
      <Search size={16} className="muted" />
      <input
        value={q}
        placeholder="输入代码或名称，如 600519 / 茅台"
        aria-label="搜索股票"
        role="combobox"
        aria-expanded={open && hits.length > 0}
        onFocus={() => setOpen(true)}
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onKeyDown={e => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, hits.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
          if (e.key === 'Enter' && hits[active]) pick(hits[active].code)
          if (e.key === 'Escape') setOpen(false)
        }}
      />
      {open && debounced && (
        <ul className="stock-search-list" role="listbox">
          {hits.length === 0 && <li className="empty">{isFetching ? '搜索中…' : '没有找到匹配的股票'}</li>}
          {hits.map((h, i) => (
            <li key={h.code} role="option" aria-selected={i === active}
                className={i === active ? 'active' : ''} onMouseEnter={() => setActive(i)} onMouseDown={() => pick(h.code)}>
              <b>{h.name}</b><span className="num">{displayCode(h.code)}</span><span className="muted">{h.sector ?? ''}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
