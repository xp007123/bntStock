import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Plus, RotateCcw } from 'lucide-react'
import { type AdminPersona, type AdminPersonaDetail, ApiError, configurePersona, type DeepPack, type DeepTry, getAdminPersona, getDeepPack, getPersonaVersion, savePersona,
         setDeepEnabled, switchPersonaVersion, tryDeep, tryPersona, useAdminPersonas } from '../../api/client'
import SubNav, { ADMIN_TABS } from '../../components/SubNav'
import Avatar from '../rooms/Avatar'
import '../rooms/rooms.css'
import './admin.css'

const when = (iso: string) => new Date(iso.endsWith('Z') ? iso : iso + 'Z').toLocaleString('zh-CN', { hour12: false })

/**
 * 管理端 · 角色管理。
 * 仓库里的角色卡是“出厂设置”；这里每保存一次，多一个版本，立刻生效。可以随时切回旧版或出厂设置。
 * 停用、是否默认进群、座次也在这里调。“试说一句”用正在编辑的草稿让角色开口，不用保存就能看效果。
 *
 * 深聊包（一对一深聊用的完整版资料）是另一套东西：它跟着代码走，取自社区的 Skill，原样保存。
 * 这里能看它从哪来、装配后的正文、带了哪些资料，能开关，能用真模型试聊一轮并看花了多少。内容本身不在这里改。
 */
export default function PersonaAdminPage() {
  const list = useAdminPersonas()
  const qc = useQueryClient()
  const [detail, setDetail] = useState<AdminPersonaDetail | null>(null)
  const [creating, setCreating] = useState(false)
  const [content, setContent] = useState('')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [tryCode, setTryCode] = useState('贵州茅台')
  const [tried, setTried] = useState<{ text: string; data?: string[]; stock?: string; note?: string } | null>(null)
  const [trying, setTrying] = useState(false)
  const [pack, setPack] = useState<{ p: AdminPersona; d: DeepPack } | null>(null)
  const [deepCode, setDeepCode] = useState('比亚迪')
  const [deepSay, setDeepSay] = useState('')
  const [deepTried, setDeepTried] = useState<DeepTry | null>(null)
  const [deepTrying, setDeepTrying] = useState(false)

  const refresh = () => { qc.invalidateQueries({ queryKey: ['admin-personas'] }); qc.invalidateQueries({ queryKey: ['personas'] }) }
  const fail = (e: unknown) => setMsg(e instanceof ApiError ? e.message : String(e))
  const show = (d: AdminPersonaDetail, text = '') => { setDetail(d); setContent(d.content); setCreating(false); setNote(''); setTried(null); setMsg(text) }

  const open = async (id: string) => { setMsg(''); try { show(await getAdminPersona(id)) } catch (e) { fail(e) } }
  const startNew = () => { setDetail(null); setCreating(true); setContent(list.data?.template ?? ''); setNote(''); setTried(null); setMsg('') }
  const save = async () => {
    setBusy(true); setMsg('')
    try { const d = await savePersona(creating ? null : detail!.id, content, note); show(d, `已保存为第 ${d.version} 版，立刻生效`); refresh() }
    catch (e) { fail(e) } finally { setBusy(false) }
  }
  const use = async (version: number | null) => {
    if (!detail) return
    setMsg('')
    try { const d = await switchPersonaVersion(detail.id, version); show(d, version == null ? '已回到出厂设置' : `已切到第 ${version} 版`); refresh() } catch (e) { fail(e) }
  }
  const peek = async (version: number) => {
    if (!detail) return
    try { setContent((await getPersonaVersion(detail.id, version)).content); setMsg(version ? `编辑框里现在是第 ${version} 版的内容（还没启用）` : '编辑框里现在是出厂设置的内容（还没启用）') } catch (e) { fail(e) }
  }
  const configure = async (p: AdminPersona, s: { enabled?: boolean; in_default?: boolean; sort?: number }) => {
    setMsg('')
    try { const d = await configurePersona(p.id, s); if (detail?.id === p.id) setDetail({ ...d, content: detail.content }); refresh() } catch (e) { fail(e) }
  }
  const tryOut = async () => {
    setTrying(true); setTried(null); setMsg('')
    try { const r = await tryPersona(content, tryCode); setTried(r.ok ? r : { text: '', note: r.note }) } catch (e) { fail(e) } finally { setTrying(false) }
  }

  const openPack = async (p: AdminPersona) => { setMsg(''); setDeepTried(null); try { setPack({ p, d: await getDeepPack(p.id) }) } catch (e) { fail(e) } }
  const toggleDeep = async (p: AdminPersona, enabled: boolean) => {
    setMsg('')
    try { const d = await setDeepEnabled(p.id, enabled); if (pack?.p.id === p.id) setPack({ p, d }); setMsg(enabled ? `${p.name}的深聊已开放` : `${p.name}的深聊已关闭，用户看不到入口了（已经开始的还能接着聊）`); refresh() } catch (e) { fail(e) }
  }
  const tryDeepOut = async () => {
    if (!pack) return
    setDeepTrying(true); setDeepTried(null); setMsg('')
    try { setDeepTried(await tryDeep(pack.p.id, deepCode, deepSay)) } catch (e) { fail(e) } finally { setDeepTrying(false) }
  }

  const editing = creating || !!detail
  const dirty = creating ? content !== (list.data?.template ?? '') : !!detail && content !== detail.content

  return (
    <div className="admin persona-admin">
      <SubNav items={ADMIN_TABS} />
      <header className="pt-head">
        <h1>角色管理</h1>
        <p className="muted">群聊里的每个人都是一张“角色卡”。改完保存就是新的一版，正在聊的群下一句话就会用上；改坏了可以切回旧版或出厂设置。</p>
      </header>
      {list.data && !list.data.available && <p className="warn">服务器上还没配置模型密钥（SIXIANG_LLM_API_KEY），用户看不到群聊入口，“试说一句”也用不了。角色卡可以先改。</p>}

      <section className="card">
        <div className="card-title">所有角色 <button className="btn" onClick={startNew}><Plus size={14} />新建角色</button></div>
        {list.isLoading ? <div className="state">读取中…</div> : (
          <div className="table-wrap">
            <table className="admin-table persona-table">
              <thead><tr><th>角色</th><th>看什么</th><th>现在用的</th><th>可用</th><th>默认进群</th><th>座次</th><th>深聊</th><th></th></tr></thead>
              <tbody>
                {(list.data?.items ?? []).map(p => (
                  <tr key={p.id} className={detail?.id === p.id ? 'on' : ''}>
                    <td><span className="persona-cell"><Avatar persona={p} size={30} /><b>{p.name}</b><span className="muted num">{p.id}</span></span></td>
                    <td>{p.role === 'host' ? <span className="tag">主持人</span> : p.lens}</td>
                    <td>{p.custom ? <span className="tag">第 {p.version} 版</span> : <span className="tag plain">出厂设置 v{p.version}</span>}
                      {p.saved_versions > 0 && <span className="muted"> · 存过 {p.saved_versions} 版</span>}</td>
                    <td>{p.role === 'host' ? <span className="muted">一直在</span>
                      : <button className="btn" aria-pressed={p.enabled} onClick={() => configure(p, { enabled: !p.enabled })}>{p.enabled ? '可用' : '已停用'}</button>}</td>
                    <td>{p.role === 'guest' && <button className="btn" aria-pressed={p.in_default} disabled={!p.enabled} onClick={() => configure(p, { in_default: !p.in_default })}>{p.in_default ? '默认进群' : '不默认'}</button>}</td>
                    <td>{p.role === 'guest' && <input type="number" className="persona-sort" defaultValue={p.sort} min={0} max={999} aria-label={`${p.name} 的座次`}
                                                      onBlur={e => { const v = Number(e.target.value); if (Number.isFinite(v) && v !== p.sort) configure(p, { sort: v }) }} />}</td>
                    <td>{p.role === 'guest' && (p.deep_pack ? (
                      <span className="deep-cell">
                        <button className="btn" aria-pressed={p.deep_pack.enabled} onClick={() => toggleDeep(p, !p.deep_pack!.enabled)}>{p.deep_pack.enabled ? '开放中' : '已关闭'}</button>
                        <button className="btn" onClick={() => openPack(p)}>看深聊包</button>
                      </span>
                    ) : <span className="muted">没装</span>)}</td>
                    <td className="ops"><button className="btn primary" onClick={() => open(p.id)}>改人设</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted footnote">座次：数字小的先发言。默认进群的角色里，挨着坐的最容易吵起来。停用后不能再被拉进群，已有的聊天记录不受影响。深聊：装了深聊包的角色才能一对一深聊；关闭后用户看不到入口。</p>
      </section>

      {msg && <p className="admin-msg">{msg}</p>}

      {pack && (
        <div className="persona-edit">
          <section className="card">
            <div className="card-title">深聊包 · {pack.p.name}
              <span className="muted">{pack.d.style === 'persona' ? '人物型：包里就是他完整的人设' : '方法型：口吻用左边表格里的角色卡，方法用包里的框架'}</span>
              <button className="btn" onClick={() => setPack(null)}>收起</button>
            </div>
            <dl className="deep-meta">
              <dt>来自</dt><dd>{pack.d.source.repo ? <a href={`${pack.d.source.repo}${pack.d.source.path ? `/tree/main/${pack.d.source.path}` : ''}`} target="_blank" rel="noreferrer">{pack.d.source.repo.replace('https://github.com/', '')}{pack.d.source.path ? ` · ${pack.d.source.path}` : ''}</a> : '没有记录'}</dd>
              <dt>版本</dt><dd className="num">{pack.d.source.version ?? '—'}（{pack.d.source.fetched ?? '—'} 取回）</dd>
              <dt>许可</dt><dd>{pack.d.source.license ?? '—'}</dd>
              <dt>正文</dt><dd>{pack.d.chars.toLocaleString()} 字，{pack.d.sections.length} 个小节：{pack.d.sections.slice(0, 8).join('、')}{pack.d.sections.length > 8 ? '…' : ''}</dd>
              <dt>资料</dt><dd>{pack.d.references.length ? pack.d.references.map(r => `${r.name}（${r.chars.toLocaleString()} 字）`).join('、') : '没有'}<span className="muted">　不每次带上，他需要时自己去翻</span></dd>
            </dl>
            <textarea className="persona-content deep-body" value={pack.d.body ?? ''} readOnly spellCheck={false} aria-label="装配后进提示词的正文" />
            <p className="muted footnote">这是装配后真正交给模型的正文（已去掉上游的头部元数据、链接清单和买卖结论模板）。深聊包跟着代码走、原样取自上游，不在这里改；要换内容就换一版文件再部署。不管包里怎么写，这几条以我们的规矩为准：只聊眼前这只票、数字只来自数据工具、一次最多反问两个问题、不替用户做买卖决定。</p>
          </section>

          <aside className="persona-aside">
            <section className="card">
              <div className="card-title">试聊一轮 <span className="muted">真的调用模型</span></div>
              <div className="persona-try deep-try">
                <input type="text" value={deepCode} onChange={e => setDeepCode(e.target.value)} placeholder="股票代码或名称" aria-label="用哪只股票试聊" />
                <input type="text" value={deepSay} onChange={e => setDeepSay(e.target.value)} placeholder="替用户说一句（选填），比如：最坏会怎样" aria-label="替用户说一句" />
                <button className="btn dark" disabled={deepTrying || !list.data?.available} onClick={tryDeepOut}>{deepTrying ? '他在想，要等十几秒到半分钟…' : `让${pack.p.name}开场`}</button>
              </div>
              {deepTried && (deepTried.ok ? (
                <div className="persona-tried">
                  <span className="muted">聊 {deepTried.stock}：</span>
                  {deepTried.turns?.map((t, i) => (
                    <div key={i} className={`deep-turn ${t.role}`}>
                      <b>{t.name}</b>
                      {t.text.split('\n').map((l, j) => <p key={j} className="bubble">{l}</p>)}
                      {t.data.map((d, j) => <p key={j} className="persona-tried-data">查到的数据：{d}</p>)}
                    </div>
                  ))}
                  {deepTried.usage && <p className="deep-usage num">用时 {deepTried.usage.seconds} 秒 · 调用模型 {deepTried.usage.calls} 次 · 输入 {deepTried.usage.prompt_tokens.toLocaleString()} token（其中 {deepTried.usage.cached_tokens.toLocaleString()} 命中缓存）· 输出 {deepTried.usage.completion_tokens.toLocaleString()} token</p>}
                </div>
              ) : <p className="muted">{deepTried.note}</p>)}
              <p className="muted footnote">看三件事：像不像他、有没有老实去查数据、有没有说出“建议买入卖出”这类话。每次说的不一样，多试几只不同的票。</p>
            </section>
          </aside>
        </div>
      )}

      {editing && (
        <div className="persona-edit">
          <section className="card">
            <div className="card-title">{creating ? '新建角色' : <>改人设 · {detail!.name}</>}
              <span className="muted">{creating ? '把 id 和 name 改成你要的；id 定了以后不能改' : detail!.custom ? `现在用的是第 ${detail!.version} 版` : `现在用的是出厂设置 v${detail!.version}`}</span>
            </div>
            <textarea className="persona-content" value={content} spellCheck={false} onChange={e => setContent(e.target.value)} aria-label="角色卡内容" />
            <div className="persona-save">
              <input type="text" value={note} maxLength={200} placeholder="这一版改了什么（选填，方便以后回头找）" onChange={e => setNote(e.target.value)} />
              <button className="btn primary lg" disabled={busy || !dirty} onClick={save}>{busy ? '保存中…' : creating ? '创建角色' : '保存为新的一版'}</button>
            </div>
            <p className="muted footnote">头部两行 --- 之间是给程序读的：名字、看什么、颜色、爱用的数据（tools）、天然的对手（rivals）。下面的小节是给模型读的人设，“示例发言”最管用，模型主要靠它学口气。</p>
          </section>

          <aside className="persona-aside">
            <section className="card">
              <div className="card-title">试说一句 <span className="muted">用左边的草稿，不用先保存</span></div>
              <div className="persona-try">
                <input type="text" value={tryCode} onChange={e => setTryCode(e.target.value)} placeholder="股票代码或名称" aria-label="用哪只股票试" />
                <button className="btn dark" disabled={trying || !list.data?.available} onClick={tryOut}>{trying ? '正在想…' : '让 TA 开口'}</button>
              </div>
              {tried && (tried.text ? (
                <div className="persona-tried">
                  <span className="muted">聊 {tried.stock}：</span>
                  {tried.text.split('\n').map((l, i) => <p key={i} className="bubble">{l}</p>)}
                  {tried.data?.map((d, i) => <p key={i} className="persona-tried-data">查到的数据：{d}</p>)}
                </div>
              ) : <p className="muted">{tried.note}</p>)}
              <p className="muted footnote">会真的调用一次模型，要等几秒。每次说的不一样，多试几次看口气稳不稳。</p>
            </section>

            {detail && (
              <section className="card">
                <div className="card-title">历史版本</div>
                <ul className="persona-versions">
                  {detail.versions.map(v => (
                    <li key={v.version} className={detail.custom && detail.version === v.version ? 'on' : ''}>
                      <div><b>第 {v.version} 版</b><span className="muted">{when(v.created_at)}{v.note ? ` · ${v.note}` : ''}</span></div>
                      <button className="btn" onClick={() => peek(v.version)}>看内容</button>
                      {detail.custom && detail.version === v.version ? <span className="tag">正在用</span> : <button className="btn" onClick={() => use(v.version)}>启用</button>}
                    </li>
                  ))}
                  {detail.builtin && (
                    <li className={!detail.custom ? 'on' : ''}>
                      <div><b>出厂设置</b><span className="muted">仓库里的角色卡 v{detail.builtin_version}</span></div>
                      <button className="btn" onClick={() => peek(0)}>看内容</button>
                      {!detail.custom ? <span className="tag">正在用</span> : <button className="btn" onClick={() => use(null)}><RotateCcw size={13} />回到出厂</button>}
                    </li>
                  )}
                  {detail.versions.length === 0 && !detail.builtin && <li><span className="muted">还没有版本</span></li>}
                </ul>
              </section>
            )}

            <section className="card">
              <div className="card-title">可以写进 tools 的数据</div>
              <ul className="persona-tools">{(list.data?.tools ?? []).map(t => <li key={t.name}><code>{t.name}</code><span className="muted">{t.description.split('：')[0].replace(/^查/, '')}</span></li>)}</ul>
              <p className="muted footnote">tools 只是“爱用的”，不是限制：所有角色都能查所有数据。</p>
            </section>
          </aside>
        </div>
      )}
    </div>
  )
}
