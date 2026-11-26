import { useEffect, useState } from 'react'
import { Download, X } from 'lucide-react'
import type { Judgment } from '../api/client'
import { displayCode, fmtPct } from '../lib/format'
import { PALETTE as P } from '../lib/palette'
import { mineRight, stanceText } from '../lib/stance'
import { horizonText } from '../features/ask/horizons'
import { blankCard, font, footer, fontsReady, ON, ON_LINE, ON_MUTED, PAD, roundRect, W, wrap } from './shareCanvas'
import './ShareCard.css'

/**
 * 分享卡：竖版 3:4，一个大数字。封存时一张（“我封存了一个判断”），揭晓后一张（当时 vs 实际）。
 * 只画历史统计和已经发生的结果，不出现任何收益承诺；数字全部来自这条判断本身。
 */
function draw(j: Judgment): HTMLCanvasElement {
  const { canvas, c } = blankCard()
  const option = j.kind === 'option'
  const done = !!j.outcome?.done

  // 印章
  c.save(); c.translate(W - PAD - 100, PAD + 96); c.rotate(-8 * Math.PI / 180)
  c.shadowColor = 'rgba(251,94,13,.6)'; c.shadowBlur = 60; c.shadowOffsetY = 20
  c.fillStyle = P.accent; roundRect(c, -100, -100, 200, 200, 56); c.fill()
  c.shadowColor = 'transparent'
  c.strokeStyle = 'rgba(255,255,255,.45)'; c.lineWidth = 4; c.setLineDash([12, 10]); roundRect(c, -86, -86, 172, 172, 44); c.stroke(); c.setLineDash([])
  c.fillStyle = '#ffffff'; c.font = font(700, 52); c.textAlign = 'center'
  c.fillText('已', 0, -10); c.fillText(done ? '揭晓' : '封存', 0, 52)
  c.restore(); c.textAlign = 'left'

  // 这是什么
  let y = PAD + 210
  c.fillStyle = ON_MUTED; c.font = font(500, 34)
  c.fillText(`${option ? '问期权' : '问个股'} · ${j.asof} 封存`, PAD, y)
  y += 96
  c.fillStyle = ON; c.font = font(700, 84); c.fillText(j.name, PAD, y)
  const nameW = c.measureText(j.name).width
  c.fillStyle = ON_MUTED; c.font = font(400, 36); c.fillText(displayCode(j.code), PAD + nameW + 24, y)
  y += 70
  c.fillStyle = ON_MUTED; c.font = font(400, 38)
  y = wrap(c, j.question, PAD, y, W - PAD * 2, 56, 2) + 30

  const probLabel = option ? '回本概率' : `${horizonText(j.horizon)}后在涨的概率`
  const prob = Math.round(j.prediction.prob * 100)
  const stance = stanceText(j.prediction.stance, option)

  if (!done || !j.outcome) {
    // 封存：一个大数字
    c.fillStyle = ON_MUTED; c.font = font(500, 34); c.fillText(`小四翻历史算出来的${probLabel}`, PAD, y + 20)
    c.fillStyle = ON; c.font = font(600, 400); c.fillText(String(prob), PAD - 14, y + 370)
    const w = c.measureText(String(prob)).width
    c.fillStyle = P.accent; c.font = font(500, 150); c.fillText('%', PAD + w + 4, y + 370)
    y += 450
    c.fillStyle = ON_MUTED; c.font = font(400, 36); c.fillText(`不挑时候的话是 ${Math.round(j.prediction.base_prob * 100)}%`, PAD, y)
    y += 70
    c.strokeStyle = ON_LINE; c.lineWidth = 2; c.beginPath(); c.moveTo(PAD, y); c.lineTo(W - PAD, y); c.stroke()
    y += 84
    c.fillStyle = ON; c.font = font(600, 50)
    c.fillText(stance ? `我的看法：${stance}` : '我把这个判断交给小四保管了', PAD, y)
    y += 74
    c.fillStyle = P.accent; c.font = font(600, 44); c.fillText(`约 ${j.due_estimate} 揭晓，到时候见分晓`, PAD, y)
  } else {
    // 揭晓：当时 vs 实际
    const half = (W - PAD * 2 - 32) / 2, top = y + 10, boxH = 380
    c.fillStyle = 'rgba(255,248,242,.07)'; roundRect(c, PAD, top, half, boxH, 44); c.fill()
    c.fillStyle = ON; roundRect(c, PAD + half + 32, top, half, boxH, 44); c.fill()
    c.fillStyle = ON_MUTED; c.font = font(500, 32); c.fillText('当时的判断', PAD + 40, top + 76)
    c.fillStyle = ON; c.font = font(600, 170); c.fillText(String(prob), PAD + 34, top + 250)
    const w = c.measureText(String(prob)).width
    c.fillStyle = P.accent; c.font = font(500, 70); c.fillText('%', PAD + 40 + w, top + 250)
    c.fillStyle = ON_MUTED; c.font = font(400, 28); c.fillText(probLabel, PAD + 40, top + 320)

    const rx = PAD + half + 32 + 40
    c.fillStyle = P.muted; c.font = font(500, 32); c.fillText('实际结果', rx, top + 76)
    const ret = fmtPct(j.outcome.return, 1)
    c.fillStyle = j.outcome.return > 0 ? P.up : j.outcome.return < 0 ? P.down : P.ink
    let size = 150; c.font = font(600, size)
    while (c.measureText(ret).width > half - 80 && size > 80) { size -= 6; c.font = font(600, size) }
    c.fillText(ret, rx - 6, top + 250)
    c.fillStyle = P.muted; c.font = font(400, 28)
    c.fillText(option ? (j.outcome.hit ? '超过期权费，回本了' : '没超过期权费，没回本') : (j.outcome.hit ? '涨了' : '没涨'), rx, top + 320)

    y = top + boxH + 96
    const right = mineRight(j)
    c.fillStyle = ON; c.font = font(600, 50)
    c.fillText(stance && right != null ? `我当时说${stance}：${right ? '说对了' : '这次没说对'}` : stance ? `我当时：${stance}` : '当初的判断和结果，放在一起看', PAD, y)
    y += 74
    c.fillStyle = ON_MUTED; c.font = font(400, 36)
    y = wrap(c, `实际涨跌${j.outcome.position}。${j.outcome.start_date} 封存，${j.outcome.end_date} 揭晓。`, PAD, y, W - PAD * 2, 54, 2)
  }

  footer(c, '心里有数，再出手', '数字来自历史统计，不构成投资建议')
  return canvas
}

/** 弹出分享卡：可以下载；手机上长按图片保存。 */
export default function ShareCard({ j, onClose }: { j: Judgment; onClose: () => void }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let alive = true
    fontsReady().then(() => { if (alive) setUrl(draw(j).toDataURL('image/png')) })
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => { alive = false; document.removeEventListener('keydown', esc) }
  }, [j, onClose])
  const done = !!j.outcome?.done
  return (
    <div className="share-modal" role="dialog" aria-modal="true" aria-label="分享卡" onClick={onClose}>
      <div className="share-box" onClick={e => e.stopPropagation()}>
        <button className="share-close" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        {url ? <img src={url} alt={`${j.name} ${done ? '揭晓' : '封存'}分享卡`} /> : <div className="share-wait">正在画…</div>}
        <div className="share-actions">
          <a className={`btn primary lg ${url ? '' : 'disabled'}`} href={url || undefined} download={`四象智投-${j.name}-${done ? '揭晓' : '封存'}.png`}><Download size={16} />保存图片</a>
          <span className="muted">手机上长按图片也能保存。卡片上只有历史统计和已经发生的结果。</span>
        </div>
      </div>
    </div>
  )
}
