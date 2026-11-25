// 设计样板：示意数据
(function () {
  const NS = 'http://www.w3.org/2000/svg'
  const el = (t, a = {}, p) => { const n = document.createElementNS(NS, t); for (const k in a) n.setAttribute(k, a[k]); if (p) p.appendChild(n); return n }
  const tip = document.getElementById('tip')

  // 固定种子的示意分布
  let seed = 20261125
  const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296
  const gauss = () => Math.sqrt(-2 * Math.log(rnd() || 1e-9)) * Math.cos(2 * Math.PI * rnd())
  const BE = 7.5, step = 2.5, lo = -40, hi = 60, N = 4312
  const bins = []
  for (let x = lo; x < hi; x += step) bins.push({ a: x, b: x + step, n: 0 })
  for (let i = 0; i < N; i++) {
    const r = 0.5 + 14 * gauss()
    bins[Math.floor((Math.min(Math.max(r, lo), hi - .01) - lo) / step)].n++
  }

  const W = 712, H = 200, pl = 0, pr = 0, pt = 6, pb = 24
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': '63 个交易日涨跌幅分布，示意数据' })
  const max = Math.max(...bins.map(b => b.n))
  const x = v => pl + (v - lo) / (hi - lo) * (W - pl - pr)
  const y = v => pt + (1 - v / max) * (H - pt - pb)
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n)
  bins.forEach(b => {
    const color = b.b <= 0 ? css('--down') : b.a >= BE ? css('--up') : css('--flat')
    const x0 = x(b.a) + 1.5, w = x(b.b) - x(b.a) - 3, h = y(0) - y(b.n)
    if (h > 0) el('rect', { x: x0, y: y(b.n), width: w, height: h, fill: color, opacity: .88 }, svg)
    const hit = el('rect', { x: x(b.a), y: pt, width: x(b.b) - x(b.a), height: H - pt - pb, fill: 'transparent' }, svg)
    hit.addEventListener('mousemove', e => {
      tip.textContent = `涨跌 ${b.a}% ~ ${b.b}% · ${(b.n / N * 100).toFixed(1)}%（${b.n} 次）`
      tip.style.opacity = 1; tip.style.left = e.clientX + 12 + 'px'; tip.style.top = e.clientY - 30 + 'px'
    })
    hit.addEventListener('mouseleave', () => { tip.style.opacity = 0 })
  })
  el('line', { x1: 0, x2: W, y1: y(0), y2: y(0), stroke: css('--ink'), 'stroke-width': 1 }, svg)
  el('line', { x1: x(BE), x2: x(BE), y1: pt - 6, y2: y(0), stroke: css('--ink'), 'stroke-dasharray': '3 3' }, svg)
  el('text', { x: x(BE) + 8, y: pt + 6, class: 'axis', fill: css('--ink') }, svg).textContent = '回本线 +7.5%'
  for (let v = -40; v <= 60; v += 20) {
    el('text', { x: x(v), y: H - 6, 'text-anchor': v === -40 ? 'start' : v === 60 ? 'end' : 'middle', class: 'axis' }, svg).textContent = (v > 0 ? '+' : '') + v + '%'
  }
  document.getElementById('hist').appendChild(svg)

  // 三段占比（与直方图同一组数据）
  const down = bins.filter(b => b.b <= 0).reduce((t, b) => t + b.n, 0)
  const gain = bins.filter(b => b.a >= BE).reduce((t, b) => t + b.n, 0)
  const zones = [
    { n: down, color: css('--down'), label: '下跌' },
    { n: N - down - gain, color: css('--flat'), label: '涨了，但没回本' },
    { n: gain, color: css('--up'), label: '回本' },
  ]
  const zEl = document.getElementById('zones'), zl = document.getElementById('zoneLabels')
  zones.forEach(z => {
    const w = (z.n / N * 100).toFixed(1) + '%'
    const bar = document.createElement('i'); bar.style.width = w; bar.style.background = z.color; zEl.appendChild(bar)
    const lab = document.createElement('span'); lab.style.width = w
    lab.innerHTML = `<b class="num">${Math.round(z.n / N * 100)}%</b>${z.label}`; zl.appendChild(lab)
  })

  // 百点图：31 个回本
  const dots = document.getElementById('dots')
  for (let i = 0; i < 100; i++) { const d = document.createElement('i'); if (i < 31) d.className = 'on'; dots.appendChild(d) }

  // 封存：盖章
  const keep = document.getElementById('keep'), seal = document.getElementById('seal')
  document.getElementById('sealBtn').addEventListener('click', () => {
    seal.classList.remove('ghost'); seal.innerHTML = '已<br>封存'; seal.classList.add('stamp'); keep.classList.add('sealed')
  })
})()
