import type { Persona } from '../../api/client'

/** 头像：不用真人照片。每个角色一个固定的颜色，中间是名字的第一个字。 */
export default function Avatar({ persona, name, size = 36, me = false }: { persona?: Persona | null; name?: string; size?: number; me?: boolean }) {
  const label = (persona?.name ?? name ?? '?').trim()
  const color = me ? 'var(--ink)' : persona?.color ?? 'var(--muted)'
  return (
    <span className={`room-avatar ${persona?.role === 'host' ? 'host' : ''}`} title={persona ? `${persona.name} · ${persona.lens}` : label}
          style={{ width: size, height: size, fontSize: size * 0.42, background: color }} aria-hidden="true">
      {label.slice(0, 1).toUpperCase()}
    </span>
  )
}
