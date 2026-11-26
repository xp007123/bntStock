import { Link } from 'react-router-dom'
import { useJobs } from '../../api/client'
import JobList from '../patterns/JobList'
import SubNav, { PICK_TABS } from '../../components/SubNav'
import '../patterns/patterns.css'

/** 研究记录：目前包含形态研究；小四对话、期权分析与到期结算在后续阶段加入。 */
export default function RecordsPage() {
  const jobs = useJobs()
  return (
    <div className="pt-report">
      <SubNav items={PICK_TABS} />
      <header className="pt-head">
        <h1>我验证过的</h1>
        <p className="muted">你自己调过参数、跑过的方法都在这里。每条固定在当时的数据版本上，可以随时回看。</p>
      </header>
      <section className="card">
        {jobs.isLoading ? <div className="state">读取中…</div>
          : jobs.data?.length ? <JobList jobs={jobs.data} />
          : <p className="muted">还没有自己验证过的方法。去 <Link to="/patterns">方法库</Link> 挑一个，调成你习惯的参数再算一遍。</p>}
      </section>
    </div>
  )
}
