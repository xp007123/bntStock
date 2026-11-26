import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { type Persona, type PersonaList, usePersonas } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import SubNav, { ASK_TABS } from '../../components/SubNav'
import { motionOff } from '../../lib/motion'
import Avatar from './Avatar'
import LineupPicker from './LineupPicker'
import './rooms.css'

/**
 * 角色页：让人一眼记住这些人，并且想点进去。细的（信条、方法）在各自的主页里，这里不铺开。
 * 顶上一张圆桌，自动播一段他们吵起来的样子；下面每人一张人物卡。
 */
export default function PersonasPage() {
  const personas = usePersonas()
  const data = personas.data
  return (
    <div className="personas">
      <SubNav items={ASK_TABS} />
      <header className="page-head fade-in">
        <h1>群里都有谁</h1>
        <p className="muted">{data ? `${data.items.length} 位` : '几位'}路子完全不同的投资人，加一个负责拱火的主持人。同一只股票，他们吵出来的才值得听。</p>
      </header>
      {personas.isLoading ? <div className="state">读取中…</div> : !data ? <div className="card state error">角色读取失败</div> : (
        <>
          <RoundTable data={data} />
          <div className="pc-head"><h2>认识一下</h2><span className="muted">详细的信条和方法在每个人的主页里</span></div>
          <div className="pc-deck stagger">{data.items.map(p => <Card key={p.id} p={p} data={data} />)}</div>
          <p className="muted pc-foot">{data.disclaimer}说的是看法和历史上的情况，不构成投资建议。{!data.available && '群聊还没开通，暂时只能看介绍。'}</p>
        </>
      )}
    </div>
  )
}

/**
 * 圆桌上轮播的两段对话。是示意，不是数据：话取自角色卡里的示例发言和线上真实聊过的内容，不带任何具体行情数字的结论。
 * 哪位角色被停用了，他的那句就跳过；一段里剩不到三句就整段不播。
 */
const SCENES: { topic: string; turns: [string, string][] }[] = [
  { topic: '一只刚涨停的票，明天怎么看？', turns: [
    ['xiaosi', '一天涨了一个板，可这仨月还跌着。老巴，你先说。'],
    ['buffett', '这东西十年后大家还得用，这点我信。但它能不能自己定价，我不信。'],
    ['yangjia', '老巴，您这套今天用不上。今天涨的不是护城河，是有人抢。'],
    ['livermore', '我不问它值多少钱。我只问：它现在往哪走，量跟不跟。'],
  ] },
  { topic: '跌了三成的好公司，能不能捡？', turns: [
    ['xiaosi', '比高点低了三成。爵士，这是你的菜吧？'],
    ['templeton', '这个位置我愿意多看两眼。但先告诉我：它是暂时难，还是真不行了？'],
    ['livermore', '接下落的刀，我试过，割手。等它自己走出来再说。'],
    ['lynch', '你们吵价格，我想知道的是三年后它的利润比现在多还是少。'],
  ] },
]

function RoundTable({ data }: { data: PersonaList }) {
  const cast = useMemo(() => {
    const map: Record<string, Persona> = { [data.host.id]: data.host }
    data.items.forEach(p => { map[p.id] = p })
    return map
  }, [data])
  const scenes = useMemo(() => SCENES.map(s => ({ ...s, turns: s.turns.filter(([who]) => cast[who]) })).filter(s => s.turns.length >= 3), [cast])
  const still = motionOff()
  const [at, setAt] = useState({ scene: 0, shown: still ? 99 : 1 })
  useEffect(() => {
    if (still || scenes.length === 0) return
    const s = scenes[at.scene % scenes.length]
    const done = at.shown >= s.turns.length
    const t = window.setTimeout(() => setAt(done ? { scene: (at.scene + 1) % scenes.length, shown: 1 } : { scene: at.scene, shown: at.shown + 1 }), done ? 4200 : 1900)
    return () => window.clearTimeout(t)
  }, [at, scenes, still])
  if (scenes.length === 0) return null
  const s = scenes[at.scene % scenes.length]
  const turns = s.turns.slice(0, at.shown)
  const speaking = turns[turns.length - 1]?.[0]
  const n = data.items.length
  return (
    <section className="rt fade-in">
      <div className="rt-ring" aria-hidden="true">
        {data.items.map((p, i) => {
          const a = (i / n) * Math.PI * 2 - Math.PI / 2
          return (
            <Link key={p.id} to={`/personas/${p.id}`} className={`rt-seat ${speaking === p.id ? 'on' : ''}`} tabIndex={-1}
                  style={{ left: `${50 + Math.cos(a) * 40.6}%`, top: `${50 + Math.sin(a) * 40.6}%` }}><Avatar persona={p} size={62} /></Link>
          )
        })}
        <span className="rt-host"><Avatar persona={data.host} size={84} /></span>
      </div>
      <div className="rt-talk">
        <small>他们坐在一起是这样的</small>
        <h2>{s.topic}</h2>
        <div className="rt-chat" aria-live="off">
          {turns.map(([who, text]) => (
            <div key={`${at.scene}-${who}-${text}`} className={`rt-say ${who === data.host.id ? 'host' : ''}`}>
              <Avatar persona={cast[who]} size={36} />
              <div><b>{cast[who].name}</b><p>{text}</p></div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/** 人物卡：色块上压着“看什么”的大字，头像骑在色块边上；一只会换话的气泡，三行短介绍，一排死对头。 */
function Card({ p, data }: { p: Persona; data: PersonaList }) {
  const lines = useMemo(() => [p.tagline && `${p.tagline}。`, ...p.lines].filter(Boolean) as string[], [p])
  const [n, setN] = useState(0)
  const timer = useRef(0)
  const [picking, setPicking] = useState(false)
  const [stock, setStock] = useState('')
  const hover = (on: boolean) => {
    window.clearInterval(timer.current)
    if (!on) return setN(0)
    if (motionOff() || lines.length < 2) return
    setN(1)
    timer.current = window.setInterval(() => setN(v => (v + 1) % lines.length), 2400)
  }
  useEffect(() => () => window.clearInterval(timer.current), [])
  const rivals = p.rivals.map(id => data.items.find(x => x.id === id)).filter(Boolean) as Persona[]
  const facts = [['一般拿多久', p.hold], ['开口先问', p.ask], ['打死不碰', p.never]].filter(f => f[1])
  return (
    <article className="pc card" style={{ '--who': p.color } as React.CSSProperties} onMouseEnter={() => hover(true)} onMouseLeave={() => hover(false)}>
      <Link to={`/personas/${p.id}`} className="pc-top" data-lens={p.lens} aria-label={`${p.name}的主页`}>
        <span className="pc-lens">{p.lens}</span>
      </Link>
      <Link to={`/personas/${p.id}`} className="pc-face" tabIndex={-1} aria-hidden="true"><Avatar persona={p} size={108} /></Link>
      <div className="pc-body">
        <div className="pc-name"><h2><Link to={`/personas/${p.id}`}>{p.name}</Link></h2><span>{p.title}</span></div>
        <p key={n} className={`pc-bubble ${n ? 'swap' : ''}`}>{lines[n] ?? p.tagline}</p>
        {facts.length > 0 && <ul className="pc-facts">{facts.map(([k, v]) => <li key={k}><b>{k}</b><span>{v}</span></li>)}</ul>}
        {rivals.length > 0 && (
          <div className="pc-rivals"><i>VS</i><span>最爱跟他吵的</span>
            {rivals.map(r => <Link key={r.id} to={`/personas/${r.id}`} title={r.name}><Avatar persona={r} size={30} /></Link>)}</div>
        )}
        <div className="pc-acts">
          {picking ? (
            <StockSearch onPick={code => { setStock(code); setPicking(false) }} placeholder={`和${p.name}聊哪只？代码或名称`} />
          ) : data.available && <button className="btn dark" onClick={() => setPicking(true)}>拉 {p.name} 聊聊</button>}
          <Link className="btn" to={`/personas/${p.id}`}>他的主页</Link>
        </div>
      </div>
      {stock && <LineupPicker code={stock} name="这只股票" preset={[p.id]} onClose={() => setStock('')} />}
    </article>
  )
}
