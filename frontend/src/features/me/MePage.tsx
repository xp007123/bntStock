import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { FlaskConical, LogOut, MessagesSquare, Shield, Stamp, Star } from 'lucide-react'
import { logout, useJobs, useJudgments, useMe, useRooms, useWatchlist } from '../../api/client'
import SubNav, { ME_TABS } from '../../components/SubNav'
import '../picks/picks.css'

const maskPhone = (p: string) => (p.length >= 7 ? `${p.slice(0, 3)}****${p.slice(-4)}` : p)

/** 我的：账户，以及属于我自己的东西（封存的判断、自选、聊过的群、验证过的方法）。 */
export default function MePage() {
  const me = useMe()
  const judgments = useJudgments()
  const watch = useWatchlist()
  const rooms = useRooms()
  const jobs = useJobs()
  const qc = useQueryClient()
  const navigate = useNavigate()
  if (!me.data) return <div className="state">读取中…</div>
  const items = judgments.data?.items ?? []
  const sealed = items.filter(j => j.status === 'sealed').length

  return (
    <div className="me">
      <SubNav items={ME_TABS} />
      <section className="card me-card fade-in">
        <span className="me-face" aria-hidden="true">{me.data.username.slice(0, 1).toUpperCase()}</span>
        <div>
          <h2>{me.data.username}{me.data.is_admin && <span className="tag night">管理员</span>}</h2>
          <p className="muted num">手机 {maskPhone(me.data.phone)}</p>
        </div>
        <button className="btn" onClick={async () => { await logout(); qc.clear(); navigate('/login', { replace: true }) }}><LogOut size={15} />退出登录</button>
      </section>

      <div className="me-links">
        <Link to="/judgments" className="card me-link">
          <span><Stamp size={16} />我的判断</span>
          <b className="num">{sealed}<i>个封存中</i></b>
          <small>{items.length > sealed ? `已揭晓 ${items.length - sealed} 个。` : ''}封存的想法到期自动揭晓</small>
        </Link>
        <Link to="/watch" className="card me-link">
          <span><Star size={16} />我的自选</span>
          <b className="num">{watch.data?.items.length ?? 0}<i>只</i></b>
          <small>每只都能看小四今天怎么看</small>
        </Link>
        <Link to="/rooms" className="card me-link">
          <span><MessagesSquare size={16} />聊过的群</span>
          <b className="num">{rooms.data?.items.length ?? 0}<i>个</i></b>
          <small>随时回去接着聊</small>
        </Link>
        <Link to="/records" className="card me-link">
          <span><FlaskConical size={16} />我验证过的方法</span>
          <b className="num">{jobs.data?.length ?? 0}<i>个</i></b>
          <small>自己调过参数、跑过的方法</small>
        </Link>
        {me.data.is_admin && (
          <Link to="/admin" className="card me-link">
            <span><Shield size={16} />管理后台</span>
            <small>用户审核、数据同步、角色管理</small>
          </Link>
        )}
      </div>
    </div>
  )
}
