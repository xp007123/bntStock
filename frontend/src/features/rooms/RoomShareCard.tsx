import { useEffect, useState } from 'react'
import { Download, X } from 'lucide-react'
import type { Minutes, Persona } from '../../api/client'
import { displayCode } from '../../lib/format'
import { PALETTE as P } from '../../lib/palette'
import { blankCard, DOWN_ON_NIGHT, font, fontsReady, footer, H, ON, ON_MUTED, ON_SOFT, PAD, roundRect, UP_ON_NIGHT, W, wrap } from '../../components/shareCanvas'
import { faceUrl } from './faces'
import '../../components/ShareCard.css'

type Faces = Record<string, HTMLImageElement>

/** 把要用到的卡通头像先加载成图片，画布上才能直接画。加载不出来的就退回“颜色圆 + 首字”。 */
function loadFaces(card: Minutes, cast: Record<string, Persona>): Promise<Faces> {
  const out: Faces = {}
  return Promise.all(card.stances.map(s => new Promise<void>(done => {
    const url = faceUrl(s.persona_id, cast[s.persona_id]?.color ?? '#7d6b62')
    if (!url) return done()
    const img = new Image()
    img.onload = () => { out[s.persona_id] = img; done() }
    img.onerror = () => done()
    img.src = url
  }))).then(() => out)
}

/** 立场标签：红涨绿跌，“再等等”是灰的 */
function pill(c: CanvasRenderingContext2D, text: string, x: number, base: number) {
  const up = text === '看多', down = text === '看空'
  c.font = font(600, 26)
  const w = c.measureText(text).width + 32
  c.fillStyle = up ? 'rgba(255,107,126,.2)' : down ? 'rgba(79,211,160,.18)' : 'rgba(255,248,242,.12)'
  roundRect(c, x, base - 32, w, 44, 22); c.fill()
  c.fillStyle = up ? UP_ON_NIGHT : down ? DOWN_ON_NIGHT : ON_MUTED; c.fillText(text, x + 16, base - 1)
}

/**
 * 群聊纪要图：竖版 3:4。谁在聊哪只股票、每个人什么立场和他的一句原话、分歧在哪、一条查到的数据。
 * 引用的话和数据都是原文；角落写明角色是 AI 演绎的。
 */
function draw(card: Minutes, cast: Record<string, Persona>, date: string, faces: Faces): HTMLCanvasElement {
  const { canvas, c } = blankCard()
  c.fillStyle = ON_MUTED; c.font = font(500, 34); c.textAlign = 'right'; c.fillText(date, W - PAD, PAD + 44); c.textAlign = 'left'

  let y = PAD + 172
  c.fillStyle = ON_MUTED; c.font = font(500, 36); c.fillText(`${card.stances.length} 位高手聊`, PAD, y)
  y += 96
  c.fillStyle = ON; c.font = font(700, 88); c.fillText(card.name, PAD, y)
  const nameW = c.measureText(card.name).width
  c.fillStyle = ON_MUTED; c.font = font(400, 34); c.fillText(displayCode(card.code), PAD + nameW + 22, y)
  y += 52

  // 底部往上：数据（最多两行）、分歧（最多两行）。先量好要占多少，剩下的给名单
  const floor = H - PAD - 86 - 34
  const dataH = card.data ? 96 : 0
  const splitH = card.split ? 150 : 0
  const room = floor - dataH - splitH - y
  const people = card.stances.slice(0, 6)
  const step = Math.min(164, Math.floor(room / people.length))
  const two = step >= 160                             // 放得下就每人两行原话
  people.forEach((s, i) => {
    const top = y + i * step, inner = step - 14
    c.fillStyle = ON_SOFT; roundRect(c, PAD, top, W - PAD * 2, inner, 24); c.fill()
    const r = 38, cx = PAD + 30 + r, cy = top + inner / 2
    if (faces[s.persona_id]) c.drawImage(faces[s.persona_id], cx - r, cy - r, r * 2, r * 2)
    else {
      c.fillStyle = cast[s.persona_id]?.color ?? P.muted; c.beginPath(); c.arc(cx, cy, r, 0, Math.PI * 2); c.fill()
      c.fillStyle = '#ffffff'; c.font = font(600, 30); c.textAlign = 'center'; c.fillText(s.name.slice(0, 1), cx, cy + 11); c.textAlign = 'left'
    }
    const left = PAD + 30 + r * 2 + 20
    const base = two ? top + 52 : top + inner / 2 - 8
    c.fillStyle = ON; c.font = font(600, 36); c.fillText(s.name, left, base)
    if (s.stance) pill(c, s.stance, left + c.measureText(s.name).width + 16, base)
    c.fillStyle = ON_MUTED; c.font = font(400, 31)
    wrap(c, `“${s.quote}”`, left, base + 44, W - PAD - 28 - left, 42, two ? 2 : 1)
  })

  y = floor - dataH - splitH + 30
  if (card.split) {
    c.fillStyle = P.accent; c.font = font(600, 30); c.fillText('分歧', PAD, y + 30)
    c.fillStyle = ON; c.font = font(600, 38); wrap(c, card.split, PAD + 84, y + 32, W - PAD * 2 - 84, 52, 2)
    y += splitH
  }
  if (card.data) {
    c.fillStyle = ON_MUTED; c.font = font(400, 27); wrap(c, `〔数据〕${card.data}`, PAD, y + 20, W - PAD * 2, 38, 2)
  }
  footer(c, window.location.host, '角色由 AI 按公开资料演绎，不代表本人')
  return canvas
}

/** 弹出纪要图：可以下载；手机上长按图片保存。 */
export default function RoomShareCard({ card, cast, date, onClose }: { card: Minutes; cast: Record<string, Persona>; date: string; onClose: () => void }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let alive = true
    Promise.all([fontsReady(), loadFaces(card, cast)]).then(([, faces]) => { if (alive) setUrl(draw(card, cast, date, faces).toDataURL('image/png')) })
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => { alive = false; document.removeEventListener('keydown', esc) }
  }, [card, cast, date, onClose])
  return (
    <div className="share-modal" role="dialog" aria-modal="true" aria-label="纪要图" onClick={onClose}>
      <div className="share-box" onClick={e => e.stopPropagation()}>
        <button className="share-close" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        {url ? <img src={url} alt={`${card.name} 群聊纪要图`} /> : <div className="share-wait">正在画…</div>}
        <div className="share-actions">
          <a className={`btn primary lg ${url ? '' : 'disabled'}`} href={url || undefined} download={`四象智投-${card.name}-纪要-${date}.png`}><Download size={16} />保存图片</a>
          <span className="muted">手机上长按图片也能保存。图上每个人的话都是他在群里的原话，说的是看法，不构成投资建议。</span>
        </div>
      </div>
    </div>
  )
}
