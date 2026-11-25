import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { type AdminUser, ApiError, resetUserPassword, runSync, setUserStatus, useAdminUsers, useMe, useSyncStatus } from '../../api/client'
import './admin.css'

const TABS = [
  { id: 'pending', label: '待审核' }, { id: 'active', label: '已通过' }, { id: 'rejected', label: '已拒绝' }, { id: 'disabled', label: '已停用' },
] as const
const fmt = (iso: string | null | undefined) => (iso ? new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').toLocaleString('zh-CN', { hour12: false }) : '—')

/** 管理后台：用户审核、重置密码、行情同步状态。 */
export default function AdminPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('pending')
  const users = useAdminUsers(tab)
  const me = useMe()
  const qc = useQueryClient()
  const [msg, setMsg] = useState('')

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setMsg('')
    try { await fn(); setMsg(done); qc.invalidateQueries({ queryKey: ['admin-users'] }) }
    catch (e) { setMsg(e instanceof ApiError ? e.message : String(e)) }
  }
  const reset = (u: AdminUser) => {
    const pw = window.prompt(`为 ${u.username} 设置新密码（至少 6 位），设置后请告诉用户：`, u.phone.slice(-6))
    if (pw) act(() => resetUserPassword(u.id, pw), `已重置 ${u.username} 的密码`)
  }

  return (
    <div className="admin">
      <header className="pt-head"><h1>管理后台</h1><p className="muted">审核注册用户；用户忘记密码时在这里重置。</p></header>

      <section className="card">
        <div className="card-title">
          用户
          <div className="seg" role="tablist">
            {TABS.map(t => (
              <button key={t.id} aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>
                {t.label}{users.data?.counts[t.id] ? ` ${users.data.counts[t.id]}` : ''}
              </button>
            ))}
          </div>
        </div>
        {msg && <p className="admin-msg">{msg}</p>}
        {users.isLoading ? <div className="state">读取中…</div> : !users.data?.items.length ? <p className="muted state">没有{TABS.find(t => t.id === tab)?.label}的用户</p> : (
          <div className="table-wrap">
            <table className="admin-table">
              <thead><tr><th>用户名</th><th>手机号</th><th>注册时间</th><th>最近登录</th><th>操作</th></tr></thead>
              <tbody>
                {users.data.items.map(u => (
                  <tr key={u.id}>
                    <td><b>{u.username}</b>{u.is_admin && <span className="tag">管理员</span>}</td>
                    <td className="num">{u.phone}</td>
                    <td className="num muted">{fmt(u.created_at)}</td>
                    <td className="num muted">{fmt(u.last_login_at)}</td>
                    <td className="ops">
                      {u.id === me.data?.id ? <span className="muted">当前账号</span> : <>
                        {u.status !== 'active' && <button className="btn primary" onClick={() => act(() => setUserStatus(u.id, 'active'), `已通过 ${u.username}`)}>{u.status === 'pending' ? '通过' : '恢复'}</button>}
                        {u.status === 'pending' && <button className="btn" onClick={() => act(() => setUserStatus(u.id, 'rejected'), `已拒绝 ${u.username}`)}>拒绝</button>}
                        {u.status === 'active' && <button className="btn" onClick={() => act(() => setUserStatus(u.id, 'disabled'), `已停用 ${u.username}`)}>停用</button>}
                        {u.status === 'active' && <button className="btn" onClick={() => reset(u)}>重置密码</button>}
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <SyncCard />
    </div>
  )
}

const SYNC_STATE: Record<string, string> = { never: '尚未运行', running: '同步中', ok: '成功', check_failed: '核对未通过，未发布', error: '失败', busy: '同步中' }

function SyncCard() {
  const status = useSyncStatus()
  const qc = useQueryClient()
  const s = status.data
  return (
    <section className="card">
      <div className="card-title">
        行情同步 <span className="muted">{s?.schedule ? `每个工作日 ${s.schedule} 自动同步` : '未开启每日自动同步'}</span>
      </div>
      {s && (
        <dl className="sync-kv">
          <dt>最近一次</dt><dd>{SYNC_STATE[s.state] ?? s.state}{s.finished_at ? ` · ${fmt(s.finished_at)}` : ''}</dd>
          {s.result?.data_end && <><dt>数据截至</dt><dd>{s.result.data_end}（版本 {s.result.id}）</dd></>}
          {s.message && <><dt>原因</dt><dd className="up">{s.message}</dd></>}
        </dl>
      )}
      <button className="btn" disabled={s?.state === 'running'}
              onClick={async () => { await runSync(); setTimeout(() => qc.invalidateQueries({ queryKey: ['sync-status'] }), 800) }}>
        <RefreshCw size={14} />{s?.state === 'running' ? '同步中…' : '立即同步'}
      </button>
      <p className="muted footnote">同步约需 5–10 分钟；末日交叉核对不通过时不会发布新数据。</p>
    </section>
  )
}
