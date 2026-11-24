// 视觉样板：示意数据，仅用于比较风格
(function () {
  const root = document.documentElement
  const tip = document.getElementById('tip')
  const NS = 'http://www.w3.org/2000/svg'
  const el = (tag, attrs = {}, parent) => {
    const n = document.createElementNS(NS, tag)
    for (const k in attrs) n.setAttribute(k, attrs[k])
    if (parent) parent.appendChild(n)
    return n
  }
  const showTip = (e, html) => { tip.innerHTML = html; tip.style.opacity = 1; tip.style.left = e.clientX + 14 + 'px'; tip.style.top = e.clientY - 34 + 'px' }
  const hideTip = () => { tip.style.opacity = 0 }

  // 固定种子随机数，保证每次一样
  let seed = 20261124
  const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296
  const gauss = () => Math.sqrt(-2 * Math.log(rnd() || 1e-9)) * Math.cos(2 * Math.PI * rnd())

  // ---- 63 日涨跌幅分布直方图 ----
  ;(function hist() {
    const BE = 7.5, step = 2.5, lo = -40, hi = 60
    const bins = []
    for (let x = lo; x < hi; x += step) bins.push({ a: x, b: x + step, n: 0 })
    const N = 4312
    for (let i = 0; i < N; i++) {
      const r = 0.5 + 14 * gauss()
      const k = Math.floor((Math.min(Math.max(r, lo), hi - 0.01) - lo) / step)
      bins[k].n++
    }
    const W = 640, H = 200, pl = 36, pr = 8, pt = 8, pb = 26
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': '63 个交易日涨跌幅分布，示意数据' })
    const max = Math.max(...bins.map(b => b.n / N))
    const ymax = Math.ceil(max * 100 / 2) * 2 / 100
    const x = v => pl + (v - lo) / (hi - lo) * (W - pl - pr)
    const y = v => pt + (1 - v / ymax) * (H - pt - pb)
    for (let t = 0; t <= ymax + 1e-9; t += ymax / 2) {
      el('line', { x1: pl, x2: W - pr, y1: y(t), y2: y(t), class: 'grid' }, svg)
      el('text', { x: pl - 6, y: y(t) + 4, 'text-anchor': 'end', class: 'axis' }, svg).textContent = Math.round(t * 100) + '%'
    }
    for (let v = -40; v <= 60; v += 20) el('text', { x: x(v), y: H - 8, 'text-anchor': 'middle', class: 'axis' }, svg).textContent = (v > 0 ? '+' : '') + v + '%'
    const bw = x(step) - x(0)
    bins.forEach(b => {
      const p = b.n / N
      const color = b.b <= 0 ? 'var(--down)' : b.a >= BE ? 'var(--up)' : 'var(--flat)'
      const h = Math.max(0, y(0) - y(p))
      if (h > 0) {
        const r = Math.min(4, h, (bw - 2) / 2)
        const x0 = x(b.a) + 1, x1 = x(b.b) - 1, yb = y(0), yt = yb - h
        el('path', { d: `M${x0},${yb}V${yt + r}Q${x0},${yt} ${x0 + r},${yt}H${x1 - r}Q${x1},${yt} ${x1},${yt + r}V${yb}Z`, fill: color }, svg)
      }
      const hit = el('rect', { x: x(b.a), y: pt, width: bw, height: H - pt - pb, class: 'hit' }, svg)
      hit.addEventListener('mousemove', e => showTip(e, `涨跌幅 ${b.a}% ~ ${b.b}%<br>占比 ${(p * 100).toFixed(1)}%（${b.n} 次）`))
      hit.addEventListener('mouseleave', hideTip)
    })
    el('line', { x1: x(BE), x2: x(BE), y1: pt, y2: y(0), stroke: 'var(--ink)', 'stroke-width': 1.5, 'stroke-dasharray': '4 3' }, svg)
    el('text', { x: x(BE) + 6, y: pt + 12, class: 'axis', fill: 'var(--ink)' }, svg).textContent = '回本线 +7.5%'
    el('line', { x1: pl, x2: W - pr, y1: y(0), y2: y(0), stroke: 'var(--muted)' }, svg)
    document.getElementById('hist').appendChild(svg)
  })()

  // ---- 日 K 线 ----
  ;(function kline() {
    const n = 80, rows = []
    let c = 100
    for (let i = 0; i < n; i++) {
      const o = c * (1 + 0.006 * gauss())
      const cl = o * (1 + 0.018 * gauss() + 0.0015)
      const hgh = Math.max(o, cl) * (1 + Math.abs(0.008 * gauss()))
      const low = Math.min(o, cl) * (1 - Math.abs(0.008 * gauss()))
      rows.push([o, hgh, low, cl]); c = cl
    }
    const k = 286.4 / rows[n - 1][3]
    rows.forEach(r => r.forEach((v, j) => (r[j] = v * k)))
    const day = i => { const d = new Date(2026, 10, 18); let left = n - 1 - i; while (left > 0) { d.setDate(d.getDate() - 1); if (d.getDay() % 6) left-- } return `${d.getMonth() + 1}-${d.getDate()}` }
    const W = 320, H = 170, pl = 4, pr = 34, pt = 6, pb = 16
    const hi = Math.max(...rows.map(r => r[1])), lo = Math.min(...rows.map(r => r[2]))
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': '近 80 日日 K 线，示意数据' })
    const cw = (W - pl - pr) / n
    const y = v => pt + (hi - v) / (hi - lo) * (H - pt - pb)
    ;[hi, (hi + lo) / 2, lo].forEach(v => {
      el('line', { x1: pl, x2: W - pr, y1: y(v), y2: y(v), class: 'grid' }, svg)
      el('text', { x: W - pr + 4, y: y(v) + 4, class: 'axis' }, svg).textContent = v.toFixed(0)
    })
    rows.forEach(([o, h, l, cl], i) => {
      const up = cl >= o, col = up ? 'var(--up)' : 'var(--down)', cx = pl + cw * (i + 0.5)
      el('line', { x1: cx, x2: cx, y1: y(h), y2: y(l), stroke: col }, svg)
      const top = y(Math.max(o, cl)), bh = Math.max(1, Math.abs(y(o) - y(cl)))
      el('rect', { x: cx - cw * 0.35, y: top, width: cw * 0.7, height: bh, fill: up ? 'var(--surface)' : col, stroke: col, 'stroke-width': 1 }, svg)
    })
    const cross = el('line', { y1: pt, y2: H - pb, stroke: 'var(--muted)', 'stroke-dasharray': '2 2', opacity: 0 }, svg)
    const hit = el('rect', { x: pl, y: pt, width: W - pl - pr, height: H - pt - pb, class: 'hit' }, svg)
    hit.addEventListener('mousemove', e => {
      const b = svg.getBoundingClientRect(), vx = (e.clientX - b.left) / b.width * W
      const i = Math.min(n - 1, Math.max(0, Math.floor((vx - pl) / cw)))
      const [o, h, l, cl] = rows[i], prev = i ? rows[i - 1][3] : o, chg = (cl / prev - 1) * 100
      const cx = pl + cw * (i + 0.5)
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('opacity', 1)
      showTip(e, `${day(i)}　开 ${o.toFixed(2)} 高 ${h.toFixed(2)}<br>低 ${l.toFixed(2)} 收 ${cl.toFixed(2)}　${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`)
    })
    hit.addEventListener('mouseleave', () => { hideTip(); cross.setAttribute('opacity', 0) })
    document.getElementById('kline').appendChild(svg)
  })()
})()
