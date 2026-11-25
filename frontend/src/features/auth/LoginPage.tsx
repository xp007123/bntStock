import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, login, register, useMe } from '../../api/client'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import Seal from '../../components/Seal'
import './auth.css'

type Mode = 'login' | 'register'

/** 登录首页：左侧墨黑主视觉与小四，右侧登录 / 注册。注册后需管理员审核。不放任何示意数字。 */
export default function LoginPage() {
  const me = useMe()
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>(params.get('mode') === 'register' ? 'register' : 'login')
  const next = params.get('next') || '/'
  if (me.data) return <Navigate to={next} replace />

  return (
    <main className="landing">
      <section className="story">
        <header>
          <span className="brand"><span className="brand-mark on-night" aria-hidden="true"><i /><i /><i /><i /></span>四象智投</span>
          <span className="story-tag">私域内测 · 邀请制</span>
        </header>
        <div className="hero fade-in">
          <div className="hero-xiaosi"><HomeResearchPet size={140} /></div>
          <span className="hero-kicker">A 股投研 · 用历史数据算概率</span>
          <h1>心里有数，<br />再<em>出手</em>。</h1>
          <p className="lede">说出你的判断，小四用 2007 年以来的全部日线替你算一算：这种情况以前出现过多少次，后来是涨是跌，最坏会怎样。</p>
          <div className="asks">
            <div><b>问个股</b><span>这只票还能涨吗</span></div>
            <div><b>问期权</b><span>这个期权费值不值</span></div>
            <div><b>问方法</b><span>我这招到底灵不灵</span></div>
          </div>
        </div>
        <footer><span>数字来自历史统计，不构成投资建议</span><span>数据每个交易日收盘后更新</span></footer>
      </section>

      <aside className="side">
        <div className="auth-card fade-in">
          <h2>{mode === 'login' ? '欢迎回来' : '申请加入'}</h2>
          <div className="seg auth-tabs" role="tablist">
            <button role="tab" aria-selected={mode === 'login'} onClick={() => setMode('login')}>登录</button>
            <button role="tab" aria-selected={mode === 'register'} onClick={() => setMode('register')}>申请注册</button>
          </div>
          {mode === 'login' ? <LoginForm next={next} /> : <RegisterForm onDone={() => setMode('login')} />}
        </div>
        <div className="keeper fade-in">
          <Seal size={48}>已<br />封存</Seal>
          <p><b>小四</b>替你算概率，也替你保管每一个判断。到期那天，结果和当初的判断会一起摆在你面前。</p>
        </div>
      </aside>
    </main>
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
      <button className="btn primary lg" disabled={busy || !account || !password}>{busy ? '正在进入…' : '进入四象智投'}</button>
      <p className="auth-hint">用户名或手机号都能登录。忘了密码，找管理员重置就行。</p>
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
      <b>申请已提交</b>
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
      <button className="btn primary lg" disabled={busy || Object.values(form).some(v => !v)}>{busy ? '提交中…' : '提交注册'}</button>
      <p className="auth-hint">提交后由管理员审核，通过后就能登录。</p>
    </form>
  )
}
