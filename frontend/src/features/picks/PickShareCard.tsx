import { useEffect, useState } from 'react'
import { Download, X } from 'lucide-react'
import { type PickReport, usePickReport } from '../../api/client'
import { fmtPct } from '../../lib/format'
import { PALETTE as P } from '../../lib/palette'
import { blankCard, DOWN_ON_NIGHT, font, fontsReady, footer, ON, ON_MUTED, ON_SOFT, PAD, roundRect, UP_ON_NIGHT, W, wrap } from '../../components/shareCanvas'
import '../../components/ShareCard.css'

const valueColor = (v: number | null) => (v == null || v === 0 ? ON : v > 0 ? UP_ON_NIGHT : DOWN_ON_NIGHT)

/** 一行股票：名次、名字、标签、右边的涨幅 */
function row(c: CanvasRenderingContext2D, x: PickReport['stars'][number], top: number, h: number, big = false) {
  const size = big ? 46 : 38
  c.fillStyle = ON_SOFT; roundRect(c, PAD, top, W - PAD * 2, h, 20); c.fill()
  const base = top + h / 2 + size / 3
  c.fillStyle = ON_MUTED; c.font = font(500, 30); c.textAlign = 'center'; c.fillText(String(x.rank), PAD + 44, base - 1); c.textAlign = 'left'
  c.fillStyle = ON; c.font = font(600, size); c.fillText(x.name, PAD + 88, base)
  if (x.tag) {
    const left = PAD + 88 + c.measureText(x.name).width + 18
    const hot = x.tag === '封板'
    c.font = font(600, 26)
    const w = c.measureText(x.tag).width + 32
    c.fillStyle = hot ? 'rgba(255,107,126,.2)' : 'rgba(255,248,242,.12)'; roundRect(c, left, base - 34, w, 44, 22); c.fill()
    c.fillStyle = hot ? UP_ON_NIGHT : ON_MUTED; c.fillText(x.tag, left + 16, base - 3)
  }
  c.fillStyle = valueColor(x.value); c.font = font(600, size); c.textAlign = 'right'
  c.fillText(fmtPct(x.value, 1), W - PAD - 28, base); c.textAlign = 'left'
}

/**
 * 选股战报图：竖版 3:4。收盘后讲当天最亮的那件事（一个大数字 + 几只票）；还没收盘就是当天的名单。
 * 讲什么由后端按策略决定，这里只管画。图上只有当天已经发生的结果和历史统计，不出现任何收益承诺。
 */
function draw(r: PickReport, host: string): HTMLCanvasElement {
  const { canvas, c } = blankCard()
  c.fillStyle = ON_MUTED; c.font = font(500, 34); c.textAlign = 'right'; c.fillText(r.asof ?? r.date ?? '', W - PAD, PAD + 44); c.textAlign = 'left'

  let y = PAD + 176
  c.fillStyle = ON; c.font = font(600, 44); c.fillText(r.strategy.name, PAD, y)
  const nameW = c.measureText(r.strategy.name).width
  const kind = r.mode === 'list' ? '名单' : '战报'
  c.fillStyle = ON_MUTED; c.font = font(400, 34)
  c.fillText(`${r.strategy.alias} · ${r.is_today ? '今日' : ''}${kind}`, PAD + nameW + 20, y)

  let rows = r.stars, rowH = 64, step = 74
  if (r.mode === 'list' || !r.big) {
    // 名单：一句标题 + 整份名单
    y += 118
    c.fillStyle = ON; c.font = font(700, 84); c.fillText(`${r.is_today ? '今日' : ''}${r.title}`, PAD, y)
    y += 58
    c.fillStyle = ON_MUTED; c.font = font(400, 32); c.fillText(r.sub, PAD, y)
    y += 40
    rows = rows.slice(0, 10); rowH = 58; step = 66
  } else {
    // 战报：一个大数字
    y += 250
    c.fillStyle = ON; c.font = font(600, 260); c.fillText(r.big.num, PAD - 10, y)
    const w = c.measureText(r.big.num).width
    c.fillStyle = P.accent; c.font = font(600, 96); c.fillText(r.big.unit, PAD + w + 6, y)
    y += 84
    c.fillStyle = ON; c.font = font(600, 52); wrap(c, r.big.label, PAD, y, W - PAD * 2, 60, 1)
    y += 56
    c.fillStyle = ON_MUTED; c.font = font(400, 32); c.fillText(r.sub, PAD, y)
    y += 44
    rows = rows.slice(0, 5)
    if (rows.length <= 3) { rowH = 88; step = 102 }   // 票少的时候每行大一点，不留一大片空
  }
  rows.forEach((x, i) => row(c, x, y + i * step, rowH, rowH > 80))
  y += rows.length * step

  // 累计的数：最多两句，放得下几句画几句
  const room = 1440 - PAD - 86 - 24 - y
  const facts = r.facts.slice(0, Math.max(0, Math.min(2, Math.floor((room - 30) / 56))))
  // 贴着底部那条线往上排，中间空多少都不难看
  y = 1440 - PAD - 86 - 48 - (facts.length - 1) * 56
  facts.forEach((f, i) => {
    c.fillStyle = P.accent; roundRect(c, PAD, y - 18 + i * 56, 10, 10, 5); c.fill()
    c.fillStyle = ON; c.font = font(500, 36); c.fillText(f, PAD + 28, y + i * 56)
  })

  footer(c, `每个交易日 ${r.strategy.publish_at} 出名单`, host)
  return canvas
}

/** 弹出战报图：可以下载；手机上长按图片保存。 */
export default function PickShareCard({ strategy, date, onClose }: { strategy: string; date?: string | null; onClose: () => void }) {
  const q = usePickReport(strategy, date)
  const [url, setUrl] = useState('')
  const r = q.data
  useEffect(() => {
    let alive = true
    if (r && r.mode !== 'empty') fontsReady().then(() => { if (alive) setUrl(draw(r, window.location.host).toDataURL('image/png')) })
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => { alive = false; document.removeEventListener('keydown', esc) }
  }, [r, onClose])
  const kind = r?.mode === 'list' ? '名单' : '战报'
  return (
    <div className="share-modal" role="dialog" aria-modal="true" aria-label="战报图" onClick={onClose}>
      <div className="share-box" onClick={e => e.stopPropagation()}>
        <button className="share-close" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        {url ? <img src={url} alt={`${r?.strategy.name} ${r?.asof ?? r?.date} ${kind}图`} />
          : <div className="share-wait">{q.isError || r?.mode === 'empty' ? '这一天没有可以画的内容' : '正在画…'}</div>}
        <div className="share-actions">
          <a className={`btn primary lg ${url ? '' : 'disabled'}`} href={url || undefined} download={`四象智投-${r?.strategy.name ?? ''}-${r?.asof ?? r?.date ?? ''}.png`}><Download size={16} />保存图片</a>
          <span className="muted">手机上长按图片也能保存。图上只有当天已经发生的结果和历史统计。{r?.note}</span>
        </div>
      </div>
    </div>
  )
}
