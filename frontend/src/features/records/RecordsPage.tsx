import { Link } from 'react-router-dom'
import { useJobs } from '../../api/client'
import JobList from '../patterns/JobList'
import '../patterns/patterns.css'

/** 研究记录：目前包含形态研究；小四对话、期权分析与到期结算在后续阶段加入。 */
export default function RecordsPage() {
  const jobs = useJobs()
  return (
    <div className="pt-report">
      <header className="pt-head">
        <h1>研究记录</h1>
        <p className="muted">每条研究固定在当时的数据版本上，可以随时回看。小四对话、期权分析和到期结算会在后续阶段加入这里。</p>
      </header>
      <section className="card">
        {jobs.isLoading ? <div className="state">读取中…</div>
          : jobs.data?.length ? <JobList jobs={jobs.data} />
          : <p className="muted">还没有研究记录。去 <Link to="/patterns">形态测试</Link> 选一个模板运行吧。</p>}
      </section>
    </div>
  )
}
