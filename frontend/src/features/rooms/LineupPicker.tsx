import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Check, X } from 'lucide-react'
import { ApiError, openRoom, usePersonas } from '../../api/client'
import Avatar from './Avatar'
import './rooms.css'

const MAX = 6

/**
 * 开群前选阵容：平台上所有的角色摆出来，默认勾好常驻的几位，用户可以换人。
 * 这是用户第一次看到“原来还有这些人”的地方，所以每个人都带上他看什么、一句话主张。
 */
export default function LineupPicker({ code, name, preset, onClose }: { code: string; name: string; preset?: string[]; onClose: () => void }) {
  const personas = usePersonas()
  const navigate = useNavigate()
  const data = personas.data
  const [picked, setPicked] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (data && picked === null) setPicked(preset?.length ? preset : data.default) }, [data, picked, preset])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [onClose])
  const on = picked ?? []
  const toggle = (id: string) => setPicked(on.includes(id) ? on.filter(x => x !== id) : on.length >= MAX ? on : [...on, id])
  const go = async () => {
    if (!data || on.length === 0) return
    setBusy(true); setError('')
    // 座次按角色列表的顺序：挨着坐的最容易吵起来
    const members = data.items.map(p => p.id).filter(id => on.includes(id))
    try { navigate(`/rooms/${(await openRoom(code, members)).id}`) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(false) }
  }
  // 挂到 body 上：入口所在的卡片有入场动画（transform），弹层留在里面会被框在那张卡片里
  return createPortal(
    <div className="lineup-modal" role="dialog" aria-modal="true" aria-label="选谁进群" onClick={onClose}>
      <div className="lineup-box" onClick={e => e.stopPropagation()}>
        <button className="lineup-close" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        <h2>拉谁来聊{name}？</h2>
        <p className="muted">路子不同的人放在一起才吵得起来。最少 1 位，最多 {MAX} 位；小四负责主持。</p>
        {!data ? <div className="state">读取中…</div> : (
          <ul className="lineup-list">
            {data.items.map(p => {
              const sel = on.includes(p.id)
              return (
                <li key={p.id}>
                  <button className={sel ? 'on' : ''} aria-pressed={sel} onClick={() => toggle(p.id)}>
                    <Avatar persona={p} size={52} />
                    <span><b>{p.name}<i>{p.lens}</i></b><small>{p.tagline}</small></span>
                    <em aria-hidden="true">{sel && <Check size={15} />}</em>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
        {error && <p className="invite-error">{error}</p>}
        <div className="lineup-foot">
          <span className="muted">已选 {on.length} 位</span>
          <button className="btn primary lg" disabled={busy || on.length === 0} onClick={go}>{busy ? '正在拉群…' : <>开群<ArrowRight size={16} /></>}</button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
