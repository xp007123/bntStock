import type { Persona } from '../../api/client'
import { faceUrl } from './faces'

const HOST_COLOR = '#fb5e0d'

/** 头像：不用真人照片。内置角色是一张卡通小人（见 faces.ts），底色是角色自己的颜色；没有画像的（后台新建的角色、用户自己）显示名字的第一个字。 */
export default function Avatar({ persona, name, size = 36, me = false }: { persona?: Persona | null; name?: string; size?: number; me?: boolean }) {
  const label = (persona?.name ?? name ?? '?').trim()
  const color = me ? 'var(--ink)' : persona?.color ?? 'var(--muted)'
  const face = me || !persona ? null : faceUrl(persona.id, persona.role === 'host' ? HOST_COLOR : persona.color)
  return (
    <span className={`room-avatar ${persona?.role === 'host' ? 'host' : ''} ${face ? 'face' : ''}`} title={persona ? `${persona.name} · ${persona.lens}` : label}
          style={{ width: size, height: size, fontSize: size * 0.42, background: color }} aria-hidden="true">
      {face ? <img src={face} alt="" draggable={false} /> : label.slice(0, 1).toUpperCase()}
    </span>
  )
}
