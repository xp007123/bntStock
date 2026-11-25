import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, login, register, useMe } from '../../api/client'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import './auth.css'

type Mode = 'login' | 'register'

/** 登录首页：左侧介绍与小四，右侧登录 / 注册。注册后需管理员审核。 */
export default function LoginPage() {
  const me = useMe()
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>(params.get('mode') === 'register' ? 'register' : 'login')
  const next = params.get('next') || '/'
  if (me.data) return <Navigate to={next} replace />

  return (
    <div className="auth-page">
      <section className="auth-intro">
        <div className="auth-brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>四象智投</div>
        <div className="auth-pet"><HomeResearchPet size={150} /></div>
        <h1>用历史数据，<br />给你的判断算概率。</h1>
        <ul>
          <li><b>问个股</b>这只票未来上涨的概率有多大</li>
          <li><b>问期权</b>这个期限和费率的场外期权值不值</li>
          <li><b>问方法</b>你的买入方法在历史上灵不灵</li>
        </ul>
        <p className="auth-note">数字来自历史数据计算，不构成投资建议。</p>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-tabs" role="tablist">
            <button role="tab" aria-selected={mode === 'login'} onClick={() => setMode('login')}>登录</button>
            <button role="tab" aria-selected={mode === 'register'} onClick={() => setMode('register')}>注册</button>
          </div>
          {mode === 'login' ? <LoginForm next={next} /> : <RegisterForm onDone={() => setMode('login')} />}
        </div>
      </section>
    </div>
  )
}

function LoginForm({ next }: { next: string }) {
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  const navigate = useNavigate()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const me = await login(account.trim(), password)
      qc.setQueryData(['me'], me)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '登录失败，请稍后再试')
    } finally { setBusy(false) }
  }

  return (
    <form className="auth-form" onSubmit={submit}>
      <label><span>用户名或手机号</span>
        <input autoComplete="username" value={account} onChange={e => setAccount(e.target.value)} required autoFocus />
      </label>
      <label><span>密码</span>
        <input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
      </label>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <button className="btn primary" disabled={busy || !account || !password}>{busy ? '登录中…' : '登录'}</button>
      <p className="auth-hint">忘记密码？请联系管理员重置。</p>
    </form>
  )
}

function RegisterForm({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState({ username: '', phone: '', password: '', confirm: '' })
  const [error, setError] = useState<{ field?: string; message: string } | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (form.password !== form.confirm) { setError({ field: 'confirm', message: '两次输入的密码不一致' }); return }
    setBusy(true); setError(null)
    try {
      await register({ ...form, username: form.username.trim(), phone: form.phone.trim() })
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? { field: err.field, message: err.message } : { message: '注册失败，请稍后再试' })
    } finally { setBusy(false) }
  }

  if (done) return (
    <div className="auth-done">
      <b>注册已提交</b>
      <p>管理员审核通过后，就可以用用户名或手机号登录了。</p>
      <button className="btn primary" onClick={onDone}>返回登录</button>
    </div>
  )

  const err = (f: string) => error?.field === f ? <em>{error.message}</em> : null
  return (
    <form className="auth-form" onSubmit={submit} noValidate>
      <label><span>用户名</span>
        <input autoComplete="username" placeholder="2–20 位，中文、字母、数字" value={form.username} onChange={set('username')} required />
        {err('username')}
      </label>
      <label><span>手机号</span>
        <input inputMode="numeric" autoComplete="tel" maxLength={11} value={form.phone} onChange={set('phone')} required />
        {err('phone')}
      </label>
      <label><span>密码</span>
        <input type="password" autoComplete="new-password" placeholder="至少 6 位" value={form.password} onChange={set('password')} required />
        {err('password')}
      </label>
      <label><span>确认密码</span>
        <input type="password" autoComplete="new-password" value={form.confirm} onChange={set('confirm')} required />
        {err('confirm')}
      </label>
      {error && !['username', 'phone', 'password', 'confirm'].includes(error.field ?? '') && <p className="auth-error" role="alert">{error.message}</p>}
      <button className="btn primary" disabled={busy || Object.values(form).some(v => !v)}>{busy ? '提交中…' : '提交注册'}</button>
      <p className="auth-hint">提交后由管理员审核，通过后即可登录。</p>
    </form>
  )
}
