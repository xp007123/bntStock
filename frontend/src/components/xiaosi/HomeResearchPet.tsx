import { useEffect, useRef, useState } from 'react'
import ResearchPet, { type PetStatus } from './ResearchPet'
import type { StateId } from './research-pet/bloub/states'
import './HomeResearchPet.css'

const moments: { motion: string; poses: StateId[] }[] = [
  { motion: 'breathe', poses: ['idle', 'idle', 'wink', 'idle'] },
  { motion: 'curious', poses: ['idle', 'idle', 'wink', 'idle'] },
  { motion: 'bounce', poses: ['idle', 'wink', 'idle', 'idle'] },
  { motion: 'inspire', poses: ['idle', 'thinking', 'thinking', 'idle'] },
]

/** Homepage ambient personality. Actual task status always takes precedence. */
export default function HomeResearchPet({ size = 164, status = 'idle', motion = true, onWink }: {
  size?: number; status?: PetStatus; motion?: boolean; onWink?: () => void
}) {
  const [step, setStep] = useState(0)
  const [active, setActive] = useState(false)
  const winkCallback = useRef(onWink)
  useEffect(() => { winkCallback.current = onWink }, [onWink])
  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setActive(motion && !reduced.matches && !document.hidden)
    sync()
    reduced.addEventListener('change', sync)
    document.addEventListener('visibilitychange', sync)
    return () => { reduced.removeEventListener('change', sync); document.removeEventListener('visibilitychange', sync) }
  }, [motion])
  useEffect(() => {
    if (!active || status !== 'idle') return
    const timer = window.setInterval(() => setStep(value => (value + 1) % 16), 2600)
    return () => window.clearInterval(timer)
  }, [active, status])
  const moment = moments[Math.floor(step / 4)]
  const ambient = status === 'idle'
  const pose = active ? moment.poses[step % 4] : 'idle'
  useEffect(() => {
    if (active && ambient && pose === 'wink') winkCallback.current?.()
  }, [active, ambient, pose, step])
  return <span className={`home-xiaosi ${ambient ? `home-xiaosi-${moment.motion}` : ''} ${active ? '' : 'home-xiaosi-paused'}`}
    data-motion={ambient ? moment.motion : 'task'} style={{ width: size, height: size }}>
    <span className="home-xiaosi-body"><ResearchPet frontFacing size={size} status={status} motion={active} followPointer={false} pose={ambient ? pose : undefined} /></span>
  </span>
}
