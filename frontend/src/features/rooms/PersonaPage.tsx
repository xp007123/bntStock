import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { ApiError, openRoom, usePersonaRecent, usePersonas, useSecurity, type Persona } from '../../api/client'
import StockSearch from '../../components/StockSearch'
import SubNav, { ASK_TABS } from '../../components/SubNav'
import Avatar from './Avatar'
import LineupPicker from './LineupPicker'
import './rooms.css'

type Turn = NonNullable<Persona['home']>['talk']['turns'][number]

/** 把连着的几句同一个人的话并成一组，好画成一个头像带几个气泡 */
function grouped(turns: Turn[]) {
  const out: { who: string; texts: string[] }[] = []
  for (const t of turns) {
    const last = out[out.length - 1]
    if (last && last.who === t.who) last.texts.push(t.text)
    else out.push({ who: t.who, texts: [t.text] })
  }
  return out
}

/**
 * 角色的个人页。回答三个问题：他凭什么值得听（三件真事）、我什么时候该找他、和他聊是什么感觉（一段真实对话）。
 * 内容写在角色卡的“## 主页：”几节里，后台可以改。信条、顺序这些方法论收在最底下的折叠区。
 */
export default function PersonaPage() {
  const { id = '' } = useParams()
  const personas = usePersonas()
  const recent = usePersonaRecent(id)
  const [code, setCode] = useState('')
  const [lineup, setLineup] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const askRef = useRef<HTMLDivElement>(null)
  const sec = useSecurity(code || 'sh600519')
  const navigate = useNavigate()
  const data = personas.data
  const p = data?.items.find(x => x.id === id)
  if (personas.isLoading) return <div className="state">读取中…</div>
  if (!data || !p) return <div className="state">没有这个角色。<Link to="/personas">看看都有谁</Link></div>
  const others = data.items.filter(x => x.id !== id)
  const byId = (pid: string) => data.items.find(x => x.id === pid)
  const deep = async () => {
    setBusy(true); setError('')
    try { navigate(`/rooms/${(await openRoom(code, [p.id], 'deep')).id}`) }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(false) }
  }
  const toAsk = () => {
    askRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    window.setTimeout(() => askRef.current?.querySelector('input')?.focus(), 350)
  }
  const said = recent.data?.items ?? []
  const home = p.home
  const talk = home?.talk
  return (
    <div className="persona-page" style={{ '--who': p.color } as React.CSSProperties}>
      <SubNav items={ASK_TABS} />
      <Link to="/personas" className="pp-back"><ChevronLeft size={14} />全部角色</Link>

      <section className="pp-hero fade-in">
        <Avatar persona={p} size={128} />
        <div className="pp-who">
          <span className="pp-lens">{p.lens}</span>{p.deep && <span className="pp-lens deep">可以深聊</span>}
          <h1>{p.name}</h1>
          <p className="pp-title">{p.title}</p>
          <p className="pp-tagline">“{p.tagline}”</p>
          {p.bio && <p className="pp-bio">{p.bio}</p>}
        </div>
        {data.available && (
          <div className="pp-ask" ref={askRef}>
            <b>和 {p.name} 聊一只股票</b>
            {!code ? <StockSearch onPick={setCode} placeholder="输入代码或名称" /> : (
              <>
                <span className="pp-stock"><b>{sec.data?.name ?? '…'}</b><button aria-label="换一只" onClick={() => { setCode(''); setError('') }}>换一只</button></span>
                {p.deep && <button className="btn primary" disabled={busy} onClick={deep}>{busy ? '正在开始…' : '一对一深聊'}</button>}
                <button className={`btn ${p.deep ? '' : 'dark'}`} disabled={busy} onClick={() => setLineup(true)}>拉进群里聊</button>
              </>
            )}
            <small>{p.deep ? '深聊：只有他一个人，按他的方法把这只票一步步聊透，他会反问你。群聊：几个人短兵相接。' : '选好股票后可以再挑几位和他对着聊。'}</small>
            {error && <small className="pp-error">{error}</small>}
          </div>
        )}
      </section>

      {home && home.deeds.length > 0 && (
        <section>
          <h2 className="pp-h">他凭什么值得听</h2>
          <p className="pp-sub">不讲道理，讲三件真事</p>
          <div className="pp-deeds">
            {home.deeds.map(d => (
              <article key={d.title} className="card pp-deed">
                <div className={`pp-year ${/^\d+$/.test(d.when) ? '' : 'word'}`}>{d.when}</div>
                <h3>{d.title}</h3>
                <p>{d.story}</p>
                {d.lesson && <p className="pp-lesson"><b>这件事里的道理</b>{d.lesson}</p>}
              </article>
            ))}
          </div>
          <p className="pp-punch">所以他说：{p.tagline}。<small>这句话是从上面这些事里来的，不是一句口号。</small></p>
        </section>
      )}

      {home && (home.yes.length > 0 || home.no.length > 0) && (
        <section>
          <h2 className="pp-h">什么时候该找他</h2>
          <p className="pp-sub">每个人只擅长回答一类问题。问对了人，才有用</p>
          <div className="pp-when">
            <div className="card yes">
              <h3><i>✓</i>这些问题，找他</h3>
              <ul>{home.yes.map(x => <li key={x.q}><b>{x.q}</b><span>{x.a}</span></li>)}</ul>
            </div>
            <div className="card no">
              <h3><i>–</i>这些问题，别找他</h3>
              <ul>
                {home.no.map(x => {
                  const to = byId(x.to)
                  return (
                    <li key={x.q}>
                      <div><b>{x.q}</b><span>{x.a}</span></div>
                      {to && <Link className="pp-goto" to={`/personas/${to.id}`}><Avatar persona={to} size={26} />问{to.name}</Link>}
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        </section>
      )}

      {talk && talk.turns.length > 0 && (
        <section>
          <h2 className="pp-h">和他聊是什么感觉</h2>
          <p className="pp-sub">一段真实对话的节选{talk.where && `：${talk.where}`}</p>
          <div className="card pp-talk">
            {grouped(talk.turns).map((g, i) => {
              if (g.who === 'user') return <div key={i} className="pp-msg me"><div>{g.texts.map(t => <p key={t} className="pp-bubble">{t}</p>)}</div></div>
              const who = g.who === 'me' ? p : byId(g.who)
              return (
                <div key={i} className={`pp-msg ${g.who === 'me' ? 'host' : 'guest'}`}>
                  {who && <Avatar persona={who} size={38} />}
                  <div><span className="pp-name">{who?.name ?? g.who}</span>{g.texts.map(t => <p key={t} className="pp-bubble">{t}</p>)}</div>
                </div>
              )
            })}
            {talk.notes.length > 0 && <div className="pp-notes">{talk.notes.map(n => <div key={n.title}><b>{n.title}</b>{n.text}</div>)}</div>}
            {data.available && (
              <div className="pp-cta">
                <button className="btn primary" onClick={toAsk}>拿我的股票和他聊</button>
                <span>{p.deep ? '深聊时只有他一个人，一次要等十几秒' : '挑几位和他对着聊，更容易听出差别'}</span>
              </div>
            )}
          </div>
        </section>
      )}

      <section>
        <h2 className="pp-h">他在你这儿的记录</h2>
        <p className="pp-sub">只算你自己的群。说得准不准，要等记录攒够了再显示，现在不编</p>
        <div className="pp-record">
          <div className="card"><b>{recent.data?.said ?? '…'}</b><span>次在你的群里发言</span></div>
          <div className="card"><b>{recent.data?.stocks ?? '…'}</b><span>只股票，他和你聊过</span></div>
          <div className="card later"><b>—</b><span>说得准不准（记录还不够，暂不显示）</span></div>
        </div>
        {said.length > 0 && (
          <div className="card pp-card pp-recent">
            <h2>他最近在你的群里说过</h2>
            <ul className="pp-said">
              {said.map(m => (
                <li key={`${m.room_id}-${m.seq}`}>
                  <Link to={`/rooms/${m.room_id}`}>
                    <span className="pp-said-head"><b>聊{m.title}</b><small>{m.created_at?.slice(5, 10)}</small></span>
                    <p>{m.text.replace(/\n/g, ' ')}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <details className="card pp-method" open={!home}>
        <summary>他的方法（想细看的话）</summary>
        <div className="pp-cols">
          <div><h4>他信什么</h4><ul>{p.beliefs.map(b => <li key={b}>{b}</li>)}</ul></div>
          <div><h4>看一只股票的顺序</h4><ol>{p.asks.map(b => <li key={b}>{b}</li>)}</ol></div>
          {p.avoids.length > 0 && <div><h4>他不碰什么</h4><ul>{p.avoids.map(b => <li key={b}>{b}</li>)}</ul></div>}
        </div>
      </details>

      <section className="pp-others">
        <h2>其他人</h2>
        <div>{others.map(o => <Link key={o.id} to={`/personas/${o.id}`}><Avatar persona={o} size={44} /><span><b>{o.name}</b><small>{o.lens}</small></span></Link>)}</div>
      </section>
      <p className="muted pp-note">{data.disclaimer}说的是看法和历史上的情况，不构成投资建议。</p>

      {lineup && <LineupPicker code={code} name={sec.data?.name ?? '这只股票'} preset={[p.id]} onClose={() => setLineup(false)} />}
    </div>
  )
}
