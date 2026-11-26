import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowUp, CandlestickChart, Plus, X } from 'lucide-react'
import { ApiError, askMinutes, continueRoom, getRoom, type Minutes, type Persona, type RoomDetail, type RoomEvent, type RoomMessage, sayInRoom, setRoomMembers, usePersonas } from '../../api/client'
import Avatar from './Avatar'
import DataCard from './DataCard'
import MinutesCard from './MinutesCard'
import RoomShareCard from './RoomShareCard'
import './rooms.css'

type Typing = { persona: string; name: string; text: string }
/** 不知道问什么的时候，点一下就发。都是问看法和风险，不问该不该买。 */
const QUICK = ['最坏会怎样？', '最大的风险是什么？', '谁愿意现在拿一个月？', '什么情况说明你看错了？']
const QUICK_DEEP = ['最坏会怎样？', '什么价格你才会感兴趣？', '什么情况说明你看错了？', '它和同行比怎么样？']

/**
 * 群聊页。演出在后台跑，这里只是“观看”：先读已有的消息，再用 SSE 接着收。
 * 刷新、断线都没关系：浏览器会自动重连，后端从断开的那条接着发。
 * 页面上没有报错状态：后端出的任何问题都已经变成台词或被跳过了。
 */
export default function RoomPage() {
  const { id = '' } = useParams()
  const personas = usePersonas()
  const qc = useQueryClient()
  const [room, setRoom] = useState<RoomDetail | null>(null)
  const [missing, setMissing] = useState(false)
  const [messages, setMessages] = useState<RoomMessage[]>([])
  const [members, setMembers] = useState<string[]>([])
  const [typing, setTyping] = useState<Typing | null>(null)
  const [playing, setPlaying] = useState(false)
  const [limit, setLimit] = useState(false)
  const [text, setText] = useState('')
  const [adding, setAdding] = useState(false)
  const [notice, setNotice] = useState('')
  const [sharing, setSharing] = useState<{ card: Minutes; date: string } | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  const cast = useMemo(() => {
    const map: Record<string, Persona> = {}
    if (personas.data) { map[personas.data.host.id] = personas.data.host; personas.data.items.forEach(p => { map[p.id] = p }) }
    return map
  }, [personas.data])

  useEffect(() => {
    let source: EventSource | null = null
    let alive = true
    setRoom(null); setMessages([]); setTyping(null); setMissing(false); setLimit(false)
    getRoom(id).then(r => {
      if (!alive) return
      setRoom(r); setMessages(r.messages); setMembers(r.members); setPlaying(r.playing)
      const after = r.messages.length ? r.messages[r.messages.length - 1].seq : 0
      source = new EventSource(`/api/rooms/${id}/stream?after=${after}`)
      source.onmessage = e => {
        let ev: RoomEvent
        try { ev = JSON.parse(e.data) } catch { return }
        if (ev.type === 'message') {
          const m = ev.message
          setMessages(list => (list.some(x => x.seq === m.seq) ? list : [...list, m]))
          setTyping(t => (t && (m.role === 'user' || t.persona === m.persona_id) ? null : t))
          if (m.action === 'limit') setLimit(true)
        } else if (ev.type === 'typing') { setTyping({ persona: ev.persona, name: ev.name, text: '' }); setPlaying(true) }
        else if (ev.type === 'delta') { const d = ev; setTyping(t => (t && t.persona === d.persona ? { ...t, text: t.text + d.text } : t)) }
        else if (ev.type === 'skipped') setTyping(null)
        else if (ev.type === 'status') setPlaying(ev.status === 'playing')
        else if (ev.type === 'scene_end') { setPlaying(false); setTyping(null); if (ev.limit) setLimit(true); qc.invalidateQueries({ queryKey: ['rooms'] }) }
        else if (ev.type === 'members') setMembers(ev.members)
      }
    }).catch(() => alive && setMissing(true))
    return () => { alive = false; source?.close() }
  }, [id, qc])

  // 新消息来了就滚到底（用户自己往上翻着看的时候不打扰）
  const count = messages.length + (typing ? 1 : 0) + (typing?.text.length ?? 0)
  const landed = useRef(false)
  useEffect(() => { landed.current = false }, [id])
  useEffect(() => {
    const el = bottom.current
    if (!el) return
    const gap = document.documentElement.scrollHeight - window.innerHeight - window.scrollY
    // 刚进群：直接到最新的一条；之后只有本来就在底部附近才跟着滚
    if (!landed.current || gap < 320) el.scrollIntoView({ block: 'end' })
    if (room) landed.current = true
  }, [count, room])

  if (missing) return <div className="state">没有这个群。<Link to="/rooms">看看聊过的</Link></div>
  if (!room) return <div className="state">正在进群…</div>

  const say = async (t: string, keep = false) => {
    setNotice('')
    try { await sayInRoom(id, t) } catch (e) { setNotice(e instanceof ApiError ? e.message : '没发出去，再试一次'); if (keep) setText(t) }
  }
  const send = async () => {
    const t = text.trim()
    if (!t) return
    setText('')
    await say(t, true)
  }
  const minutes = async () => { setNotice(''); setPlaying(true); try { await askMinutes(id) } catch (e) { setPlaying(false); setNotice(e instanceof ApiError ? e.message : '纪要没出成，再试一次') } }
  const more = async () => { setNotice(''); setPlaying(true); try { await continueRoom(id) } catch { setPlaying(false) } }
  const change = async (c: { add?: string; remove?: string }) => {
    setNotice(''); setAdding(false)
    try { setMembers((await setRoomMembers(id, c)).members) } catch (e) { setNotice(e instanceof ApiError ? e.message : String(e)) }
  }
  const mention = (name: string) => { setText(t => `${t}${t && !t.endsWith(' ') ? ' ' : ''}@${name} `); input.current?.focus() }
  const others = (personas.data?.items ?? []).filter(p => !members.includes(p.id))
  const bySeq = (seq: number | null) => (seq ? messages.find(m => m.seq === seq) : undefined)
  const quiet = !playing && messages.length === 0
  const deep = room.topic.mode === 'deep'
  const solo = deep ? cast[members[0]] : null
  const talked = messages.some(m => m.role === 'guest')
  const day = (m: RoomMessage) => (m.created_at ? new Date(m.created_at + 'Z') : new Date()).toLocaleDateString('sv-SE')

  return (
    <div className={`room ${deep ? 'deep' : ''}`}>
      <header className="room-head">
        <Link to="/rooms" className="back muted"><ArrowLeft size={15} />聊过的</Link>
        <div className="room-title">
          <h1>{deep && solo ? `和${solo.name}深聊 · ${room.title}` : room.title}</h1>
          <Link to={`/stocks/${room.topic.code}`} className="room-k"><CandlestickChart size={14} />K 线</Link>
          <Link to={`/ask/stock?code=${room.topic.code}&h=21`} className="room-k">小四的结论</Link>
        </div>
        {deep ? solo && (
          <div className="room-members"><Link to={`/personas/${solo.id}`} className="room-member"><Avatar persona={solo} size={26} />{solo.name} · {solo.lens}</Link>
            <span className="muted room-deep-note">一对一：他按自己的方法把这只票一步步聊透</span></div>
        ) : <div className="room-members">
          {members.map(pid => cast[pid] && (
            <span key={pid} className="room-member">
              <Avatar persona={cast[pid]} size={26} />{cast[pid].name}
              {members.length > 1 && <button aria-label={`把${cast[pid].name}请出群`} title="请出群" onClick={() => change({ remove: pid })}><X size={12} /></button>}
            </span>
          ))}
          {others.length > 0 && (
            <span className="room-add">
              <button className="room-member add" onClick={() => setAdding(v => !v)}><Plus size={13} />拉人</button>
              {adding && <span className="room-add-list">{others.map(p => <button key={p.id} onClick={() => change({ add: p.id })}><Avatar persona={p} size={24} />{p.name}<small>{p.lens}</small></button>)}</span>}
            </span>
          )}
        </div>}
        <p className="room-note muted">{personas.data?.disclaimer} 说的是看法和历史上的情况，不构成投资建议。</p>
      </header>

      <div className="room-flow">
        {quiet && <p className="room-quiet">{deep ? '他还没开口。说句话，或者点下面的“请他开始”。' : '群里现在很安静。说句话，或者点下面的“让他们聊起来”。'}</p>}
        {messages.map(m => {
          if (m.role === 'system') return <p key={m.seq} className="room-system">{m.text}</p>
          const mine = m.role === 'user'
          const p = m.persona_id ? cast[m.persona_id] : null
          const quoted = bySeq(m.reply_to)
          return (
            <div key={m.seq} className={`msg ${mine ? 'mine' : ''} ${m.role}`}>
              {!mine && <Avatar persona={p} name={m.name} size={38} />}
              <div className="msg-body">
                {!mine && <span className="msg-name">{m.name}{p && <i>{p.lens}</i>}{!deep && m.role === 'guest' &&
                  <button className="msg-at" onClick={() => mention(m.name)} title={`问${m.name}`}>@</button>}</span>}
                {quoted && quoted.name !== m.name && <span className="msg-quote">回 {quoted.name}：{quoted.text.replace(/\n/g, ' ').slice(0, 26)}{quoted.text.length > 26 ? '…' : ''}</span>}
                {m.text.split('\n').map((line, i) => <p key={i} className="bubble">{line}</p>)}
                {m.cards.map((c, i) => c.type === 'minutes'
                  ? <MinutesCard key={i} card={c as Minutes} cast={cast} onShare={() => setSharing({ card: c as Minutes, date: day(m) })} />
                  : <DataCard key={i} card={c} />)}
              </div>
            </div>
          )
        })}
        {typing && (
          <div className="msg typing">
            <Avatar persona={cast[typing.persona]} name={typing.name} size={38} />
            <div className="msg-body">
              <span className="msg-name">{typing.name}</span>
              {typing.text ? typing.text.split('\n').filter(Boolean).map((line, i) => <p key={i} className="bubble">{line}</p>)
                : <p className="bubble dots" aria-label={`${typing.name}正在输入`}><i /><i /><i /></p>}
            </div>
          </div>
        )}
        <div ref={bottom} />
      </div>

      <footer className="room-foot">
        {notice && <p className="room-error">{notice}</p>}
        {limit ? <p className="room-limit">今天聊到这儿了，明天接着来。记录都在，随时可以回来看。</p> : (
          <>
            <div className="room-ats">
              {!deep && <span className="muted">问</span>}
              {!deep && members.map(pid => cast[pid] && <button key={pid} onClick={() => mention(cast[pid].name)}>@{cast[pid].name}</button>)}
              {!deep && !playing && talked && <button className="room-minutes" onClick={minutes} title="让小四把每个人的看法记成一张卡，可以分享">出一份纪要</button>}
              {!playing && <button className="room-more" onClick={more}>{deep ? (talked ? '请他接着说' : '请他开始') : talked ? '让他们接着聊' : '让他们聊起来'}</button>}
              {playing && <span className="room-playing"><i />{deep ? '他在想，深聊要等十几秒' : '正在聊'}</span>}
            </div>
            {talked && !playing && !text && (
              <div className="room-quick" aria-label="一点就发的问题">
                {(deep ? QUICK_DEEP : QUICK).map(q => <button key={q} onClick={() => say(q)}>{q}</button>)}
              </div>
            )}
            <div className="room-input">
              <textarea ref={input} rows={1} value={text} maxLength={500} placeholder={deep ? '回答他的问题，或者接着问…' : '说点什么，或者 @ 某个人问一句…'} aria-label="在群里说话"
                        onChange={e => setText(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} />
              <button className="room-send" disabled={!text.trim()} onClick={send} aria-label="发送"><ArrowUp size={18} /></button>
            </div>
          </>
        )}
      </footer>
      {sharing && <RoomShareCard card={sharing.card} cast={cast} date={sharing.date} onClose={() => setSharing(null)} />}
    </div>
  )
}
