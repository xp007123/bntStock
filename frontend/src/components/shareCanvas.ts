import { PALETTE as P } from '../lib/palette'

/** 分享图的公共画法：竖版 3:4（1080×1440），墨黑底 + 两团橙色光 + 左上角品牌。判断分享卡和选股战报图共用。 */
export const W = 1080, H = 1440, PAD = 88
export const NIGHT = '#190300', ON = '#fff8f2', ON_MUTED = 'rgba(255,248,242,.62)', ON_LINE = 'rgba(255,248,242,.16)', ON_SOFT = 'rgba(255,248,242,.07)'
/** 深色底上的红涨绿跌：比浅底上的亮一档，保证看得清 */
export const UP_ON_NIGHT = '#ff6b7e', DOWN_ON_NIGHT = '#4fd3a0'
export const font = (weight: number, size: number) => `${weight} ${size}px ${P.sans}`

export function roundRect(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath()
}

/** 中文按字折行，返回画完后的 y */
export function wrap(c: CanvasRenderingContext2D, text: string, x: number, y: number, maxW: number, lineH: number, maxLines = 3) {
  let line = '', n = 0
  for (const ch of text) {
    if (c.measureText(line + ch).width > maxW) {
      n += 1
      if (n === maxLines) { c.fillText(line.slice(0, -1) + '…', x, y); return y + lineH }
      c.fillText(line, x, y); y += lineH; line = ch
    } else line += ch
  }
  c.fillText(line, x, y)
  return y + lineH
}

/** 一张画好底色和品牌的空卡 */
export function blankCard() {
  const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H
  const c = canvas.getContext('2d')!
  c.textBaseline = 'alphabetic'
  c.fillStyle = NIGHT; c.fillRect(0, 0, W, H)
  for (const [x, y, r, a] of [[W, 0, 900, .45], [0, H, 760, .22]] as const) {
    const g = c.createRadialGradient(x, y, 0, x, y, r)
    g.addColorStop(0, `rgba(251,94,13,${a})`); g.addColorStop(1, 'rgba(251,94,13,0)')
    c.fillStyle = g; c.fillRect(0, 0, W, H)
  }
  const m = 26, gap = 9
  ;[[0, 0, ON], [1, 0, P.accent], [0, 1, P.accent], [1, 1, ON]].forEach(([cx, cy, color]) => {
    c.fillStyle = color as string; roundRect(c, PAD + (cx as number) * (m + gap), PAD + (cy as number) * (m + gap), m, m, 8); c.fill()
  })
  c.fillStyle = ON; c.font = font(700, 44); c.fillText('四象智投', PAD + 2 * m + gap + 24, PAD + 46)
  return { canvas, c }
}

/** 底部一条线：左边一句话，右边一行小字 */
export function footer(c: CanvasRenderingContext2D, left: string, right: string) {
  c.strokeStyle = ON_LINE; c.lineWidth = 2; c.beginPath(); c.moveTo(PAD, H - PAD - 86); c.lineTo(W - PAD, H - PAD - 86); c.stroke()
  c.fillStyle = ON; c.font = font(600, 38); c.textAlign = 'left'; c.fillText(left, PAD, H - PAD - 20)
  c.fillStyle = ON_MUTED; c.font = font(400, 28); c.textAlign = 'right'
  c.fillText(right, W - PAD, H - PAD - 22); c.textAlign = 'left'
}

/** 等数字字体就绪再画，否则大数字会用系统字体 */
export const fontsReady = () =>
  document.fonts?.load ? Promise.all([document.fonts.load(font(600, 100), '0'), document.fonts.ready]).catch(() => null) : Promise.resolve(null)
