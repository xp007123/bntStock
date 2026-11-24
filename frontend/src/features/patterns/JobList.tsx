import { Link } from 'react-router-dom'
import type { JobListItem, JobStatus } from '../../api/client'

export const STATUS: Record<JobStatus, string> = {
  queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断',
}

export default function JobList({ jobs }: { jobs: JobListItem[] }) {
  return (
    <ul className="job-list">
      {jobs.map(j => (
        <li key={j.id}>
          <Link to={`/patterns/jobs/${j.id}`}>
            <div className="job-line">
              <b>{j.name}</b>
              <span className={`job-status s-${j.status}`}>{j.status === 'running' ? `${Math.round(j.progress)}%` : STATUS[j.status]}</span>
            </div>
            <div className="muted job-meta">
              {j.created.slice(5, 16)} · {j.conditions} 个条件
              {j.status === 'completed' && <> · {j.event_count.toLocaleString()} 个历史事件 · 今日 {j.selected_count} 只</>}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  )
}
