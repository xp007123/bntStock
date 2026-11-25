import { useEffect, type ReactNode } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { setUnauthorizedHandler, useMe } from '../api/client'

/** 需要登录的页面。会话失效时（任何接口返回 401）回到登录页，并记住原来的地址。 */
export default function RequireAuth({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const me = useMe()
  const location = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const next = encodeURIComponent(location.pathname + location.search)

  useEffect(() => {
    setUnauthorizedHandler(() => {
      qc.removeQueries()
      navigate(`/login?next=${next}`, { replace: true })
    })
  }, [navigate, qc, next])

  if (me.isLoading) return <div className="state">正在进入…</div>
  if (!me.data) return <Navigate to={`/login?next=${next}`} replace />
  if (admin && !me.data.is_admin) return <Navigate to="/" replace />
  return <>{children}</>
}
