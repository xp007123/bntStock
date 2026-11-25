import { useEffect, useId, useRef, useState } from 'react'
import { BotEngine } from './research-pet/bloub/engine'
import { EXPRESSIONS } from './research-pet/bloub/expressions'
import { mixHex } from './research-pet/bloub/skins'
import type { StateId } from './research-pet/bloub/states'

export type PetStatus = 'idle' | 'thinking' | 'researching' | 'waiting' | 'complete' | 'error'
const states: Record<PetStatus, StateId> = {
  idle: 'idle', thinking: 'thinking', researching: 'orbit', waiting: 'notify', complete: 'wink', error: 'alert',
}
export const statusLabels: Record<PetStatus, string> = {
  idle: '随时开始', thinking: '正在理解问题', researching: '正在研究', waiting: '等待你的确认', complete: '研究已完成', error: '研究已暂停',
}
const ink = '#fb5e0d'
const frontExpression = { ...EXPRESSIONS[0], gaze: { yaw: 0, pitch: 0, roll: 0 } }

/** React adapter for the pinned bloub engine. Animation is driven only by UI status. */
export default function ResearchPet({ status = 'idle', size = 160, motion = true, pose, followPointer = true, frontFacing = false }: {
  status?: PetStatus; size?: number; motion?: boolean; pose?: StateId; followPointer?: boolean; frontFacing?: boolean
}) {
  const uid = `pet-${useId().replace(/:/g, '')}`
  const [engine] = useState(() => new BotEngine(100, states[status], null, frontFacing ? frontExpression : null))
  const [frame, setFrame] = useState(() => engine.sample(0))
  const clock = useRef(0)
  const svg = useRef<SVGSVGElement>(null)
  const desired = useRef(status)
  desired.current = status

  useEffect(() => {
    engine.setExpression(frontFacing ? frontExpression : null, clock.current)
    engine.setState(pose || states[status], clock.current)
    setFrame(engine.sample(clock.current + (motion && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1)))
    if (status === 'complete' && !pose) {
      const settle = window.setTimeout(() => engine.setState('idle', clock.current), 1400)
      return () => window.clearTimeout(settle)
    }
  }, [status, engine, motion, pose, frontFacing])

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    let raf = 0
    let last = 0
    let lastPaint = 0
    const draw = (ms: number) => {
      clock.current += last ? Math.min((ms - last) / 1000, 0.064) : 0
      last = ms
      if (ms - lastPaint > 32) {
        setFrame(engine.sample(clock.current))
        lastPaint = ms
      }
      raf = requestAnimationFrame(draw)
    }
    const sync = () => {
      cancelAnimationFrame(raf)
      last = 0
      if (motion && !media.matches && !document.hidden) raf = requestAnimationFrame(draw)
      else setFrame(engine.sample(clock.current + 1))
    }
    const look = (event: PointerEvent) => {
      if (!followPointer || !motion || media.matches || event.pointerType === 'touch' || !['idle', 'waiting'].includes(desired.current)) return
      const box = svg.current?.getBoundingClientRect()
      if (!box?.width) return
      engine.setLook({
        yaw: Math.max(-38, Math.min(38, (event.clientX - box.left - box.width / 2) / window.innerWidth * 90)),
        // Screen Y grows downward; bloub's positive pitch looks upward.
        pitch: Math.max(-25, Math.min(25, (box.top + box.height / 2 - event.clientY) / window.innerHeight * 60)),
        mix: 1, spin: 0, wander: 0,
      }, clock.current)
    }
    const release = () => engine.setLook(null, clock.current)
    sync()
    media.addEventListener('change', sync)
    document.addEventListener('visibilitychange', sync)
    document.addEventListener('pointermove', look)
    document.documentElement.addEventListener('pointerleave', release)
    return () => {
      cancelAnimationFrame(raf)
      engine.setLook(null, clock.current)
      media.removeEventListener('change', sync)
      document.removeEventListener('visibilitychange', sync)
      document.removeEventListener('pointermove', look)
      document.documentElement.removeEventListener('pointerleave', release)
    }
  }, [engine, motion, followPointer])

  useEffect(() => { if (status !== 'idle' && status !== 'waiting') engine.setLook(null, clock.current) }, [engine, status])
  const dots = frame.dots.map((dot, i) => {
    const fill = dot.color ?? (dot.depth === undefined ? ink : mixHex('#fafaf8', ink, dot.depth))
    return dot.d
      ? <path key={i} d={dot.d} transform={`translate(${dot.x} ${dot.y}) rotate(${dot.rot ?? 0}) scale(100)`} fill={fill} opacity={dot.opacity} />
      : <circle key={i} cx={dot.x} cy={dot.y} r={dot.r} fill={fill} opacity={dot.opacity} />
  })
  return <svg ref={svg} width={size} height={size} viewBox="-158 -158 316 316" role="img" aria-label={`小四：${statusLabels[status]}`} className="rh-pet">
    <defs>
      <mask id={uid} maskUnits="userSpaceOnUse" x="-158" y="-158" width="316" height="316">
        <path d={frame.bodyPath} fill="white" />
        {frame.eyes.map((eye, i) => <path key={i} d={eye.d} transform={eye.matrix} opacity={eye.alpha} fill="black" />)}
        {frame.notch && <circle cx={frame.notch.x} cy={frame.notch.y} r={frame.notch.r} fill="black" />}
      </mask>
      {frame.arcs.map(arc => <linearGradient key={arc.id} id={`${uid}-${arc.id}`} gradientUnits="userSpaceOnUse" x1={arc.grad.x1} y1={arc.grad.y1} x2={arc.grad.x2} y2={arc.grad.y2}>
        {arc.grad.stops.map((color, i) => <stop key={i} offset={i / (arc.grad.stops.length - 1)} stopColor={color} />)}
      </linearGradient>)}
    </defs>
    <g fill="none" strokeLinecap="round">{frame.arcs.map(arc => <path key={arc.id} d={arc.back} stroke={`url(#${uid}-${arc.id})`} strokeWidth={arc.width} opacity={arc.opacity} />)}</g>
    {frame.dotsBehind && dots}
    <g opacity={frame.bodyAlpha}>
      <path d={frame.bodyPath} fill="#fafaf8" />
      <path d={frame.bodyPath} fill={ink} mask={`url(#${uid})`} />
    </g>
    {!frame.dotsBehind && dots}
    {frame.notif && <circle cx={frame.notif.x} cy={frame.notif.y} r={frame.notif.r} fill="#923b2c" />}
    <g fill="none" strokeLinecap="round">{frame.arcs.map(arc => <path key={arc.id} d={arc.front} stroke={`url(#${uid}-${arc.id})`} strokeWidth={arc.width} opacity={arc.opacity} />)}</g>
  </svg>
}
