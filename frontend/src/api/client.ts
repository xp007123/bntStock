import { keepPreviousData, useQuery } from '@tanstack/react-query'

export class ApiError extends Error {
  constructor(public status: number, message: string, public field?: string) { super(message) }
}

/** 会话失效（401）时的全局处理，由应用设置为跳转登录页。 */
let onUnauthorized: (() => void) | null = null
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn }

async function request<T>(method: 'GET' | 'POST', path: string, params?: Record<string, string | number | undefined>, body?: unknown): Promise<T> {
  const query = params
    ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)])).toString()
    : ''
  const res = await fetch(`/api${path}${query}`, {
    method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let message = res.statusText
    let field: string | undefined
    try {
      const detail = (await res.json()).detail
      if (typeof detail === 'string') message = detail
      else if (detail?.message) { message = detail.message; field = detail.field }
    } catch { /* 非 JSON 错误体 */ }
    if (res.status === 401 && !path.startsWith('/auth/')) onUnauthorized?.()
    throw new ApiError(res.status, message, field)
  }
  return res.json() as Promise<T>
}

const get = <T,>(path: string, params?: Record<string, string | number | undefined>) => request<T>('GET', path, params)
const post = <T,>(path: string, body: unknown) => request<T>('POST', path, undefined, body)

// ---------------------------------------------------------------- 账号

export type Me = { id: number; username: string; phone: string; status: string; is_admin: boolean }

export const useMe = () =>
  useQuery({ queryKey: ['me'], queryFn: () => get<Me>('/auth/me'), retry: false, staleTime: 5 * 60_000 })

export const login = (account: string, password: string) => post<Me>('/auth/login', { account, password })
export const register = (body: { username: string; phone: string; password: string; confirm: string }) =>
  post<{ status: string; message: string }>('/auth/register', body)
export const logout = () => post<{ ok: boolean }>('/auth/logout', {})

export type AdminUser = {
  id: number; username: string; phone: string; status: 'pending' | 'active' | 'rejected' | 'disabled'; is_admin: boolean
  created_at: string; reviewed_at: string | null; review_note: string | null; last_login_at: string | null
}
export const useAdminUsers = (status?: string) =>
  useQuery({ queryKey: ['admin-users', status], queryFn: () => get<{ counts: Record<string, number>; items: AdminUser[] }>('/admin/users', { status }) })
export const setUserStatus = (id: number, status: 'active' | 'rejected' | 'disabled', note?: string) =>
  post<Me>(`/admin/users/${id}/status`, { status, note })
export const resetUserPassword = (id: number, password: string) => post<{ ok: boolean }>(`/admin/users/${id}/password`, { password })

export type SyncStatus = {
  state: 'never' | 'running' | 'ok' | 'check_failed' | 'error' | 'busy'
  schedule: string | null; started_at?: string; finished_at?: string; message?: string
  result?: { status: string; id?: string; data_end?: string; counts?: Record<string, number>; elapsed?: number }
}
export const useSyncStatus = () =>
  useQuery({ queryKey: ['sync-status'], queryFn: () => get<SyncStatus>('/admin/data/sync-status'),
             refetchInterval: q => (q.state.data?.state === 'running' ? 3000 : false) })
export const runSync = () => post<{ state: string }>('/admin/data/sync', {})

export type DataVersion = {
  id: string
  data_end: string
  created_at: string
  source: string
  counts: Record<string, number>
  adjustment: string
}

export type SecurityHit = { code: string; name: string; sector: string | null; last_date: string }
export type Security = SecurityHit & { exchange: string; first_date: string; rows: number; data_version: string }

export type Bar = {
  date: string
  open: number
  high: number
  low: number
  close: number
  prev_close?: number
  volume: number
  amount: number
}
export type Adjust = 'qfq' | 'hfq' | 'none'
export type DailyResponse = { code: string; name: string; adjust?: Adjust; data_version: string; bars: Bar[] }
export type IndexQuote = { code: string; name: string; close: number; date: string; change: number | null }

export const useDataVersion = () =>
  useQuery({ queryKey: ['data-version'], queryFn: () => get<DataVersion>('/data/version'), staleTime: 60_000 })

export const useSecuritySearch = (q: string) =>
  useQuery({
    queryKey: ['securities', q],
    queryFn: () => get<SecurityHit[]>('/securities', { q, limit: 12 }),
    enabled: q.trim().length > 0,
    placeholderData: keepPreviousData,
  })

export const useSecurity = (code: string) =>
  useQuery({ queryKey: ['security', code], queryFn: () => get<Security>(`/securities/${code}`), retry: false })

export const useDaily = (code: string, adjust: Adjust, limit?: number) =>
  useQuery({
    queryKey: ['daily', code, adjust, limit],
    queryFn: () => get<DailyResponse>(`/securities/${code}/daily`, { adjust, limit }),
    placeholderData: keepPreviousData,
    retry: false,
  })

export const useIndices = () => useQuery({ queryKey: ['indices'], queryFn: () => get<IndexQuote[]>('/indices') })

export const useIndexDaily = (code: string, limit?: number) =>
  useQuery({
    queryKey: ['index-daily', code, limit],
    queryFn: () => get<DailyResponse>(`/indices/${code}/daily`, { limit }),
    placeholderData: keepPreviousData,
  })

// ---------------------------------------------------------------- 形态测试

export type Expr = number | { field: string } | { fn: string; x?: Expr; y?: Expr; n?: number; k?: number }
export type Condition = { label: string; left: Expr; op: string; right: Expr }
export type Rule = {
  name: string
  description?: string
  conditions: Condition[]
  cooldown?: number
  min_bars?: number
  exclude_st?: boolean
  markets?: string[]
  horizons?: number[]
  start?: string
  asof?: string
}
export type Templates = { templates: Rule[]; defaults: Partial<Rule>; fields: string[]; functions: string[]; operators: string[] }
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
export type Job = {
  id: string
  name: string
  status: JobStatus
  progress: number
  done: number
  total: number
  selected_count: number
  event_count: number
  message: string
  created: string
  elapsed?: number
  data_version: string
  data_end: string
  rule: Rule
  rule_hash: string
  reused?: boolean
  comparison_base?: string
  comparison_change?: { action: 'add' | 'remove'; index?: number; condition: Condition }
  rerun_of?: string
  library_save?: { conditions_added: number; warnings: string[] }
}
export type JobListItem = Omit<Job, 'rule'> & { conditions: number }
export type SummaryRow = {
  horizon: number; valid: number; unavailable: number; win_rate: number | null; mean: number | null; median: number | null
  p10: number | null; p90: number | null; excess_mean: number | null; excess_n: number
}
export type YearRow = { year: string; horizon: number; valid: number; mean: number | null; win_rate: number | null }
export type Reason = { label: string; op: string; left: number | null; right: number | null; passed?: boolean }
export type Selected = { code: string; name: string; sector: string; date: string; price: number; change: number; amount: number; reasons: Reason[] }
export type StudyEvent = { code: string; name: string; date: string; price: number; returns: Record<string, number | null> }
export type StudyResult = {
  data_version: string; rule: Rule; summary: SummaryRow[]; years: YearRow[]; selected: Selected[]; errors: { code: string; error: string }[]
  raw_signals: number; deduplicated_events: number; stocks: number; scanned: number; elapsed: number; event_total: number
  method: string; reference: string; limitations: string[]
}
export type Explain = { code: string; signal_dates: string[]; date: string; conditions: Reason[]; eligible: boolean; passed: boolean }

export const useTemplates = () =>
  useQuery({ queryKey: ['pattern-templates'], queryFn: () => get<Templates>('/patterns/templates'), staleTime: Infinity })

export const useJobs = () =>
  useQuery({
    queryKey: ['pattern-jobs'],
    queryFn: () => get<JobListItem[]>('/patterns/jobs'),
    refetchInterval: q => (q.state.data?.some(j => j.status === 'queued' || j.status === 'running') ? 1500 : false),
  })

export const useJob = (id: string) =>
  useQuery({
    queryKey: ['pattern-job', id],
    queryFn: () => get<Job>(`/patterns/jobs/${id}`),
    refetchInterval: q => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 1000 : false),
    retry: false,
  })

export const useJobResult = (id: string, enabled: boolean) =>
  useQuery({ queryKey: ['pattern-result', id], queryFn: () => get<StudyResult>(`/patterns/jobs/${id}/result`), enabled, staleTime: Infinity })

export type EventSort = 'date' | 'typical' | 'best' | 'worst'
export const useJobEvents = (id: string, page: number, sort: EventSort, horizon: number, pageSize = 20) =>
  useQuery({
    queryKey: ['pattern-events', id, page, sort, horizon],
    queryFn: () => get<{ total: number; items: StudyEvent[] }>(`/patterns/jobs/${id}/events`, { offset: page * pageSize, limit: pageSize, sort, horizon }),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })

export const useExplain = (id: string, code: string | null, date?: string) =>
  useQuery({
    queryKey: ['pattern-explain', id, code, date],
    queryFn: () => get<Explain>(`/patterns/jobs/${id}/explain/${code}`, { date }),
    enabled: !!code,
    retry: false,
    staleTime: Infinity,
  })

export const submitJob = (rule: Rule) => post<Job>('/patterns/jobs', { rule })
export const cancelJob = (id: string) => post<Job>(`/patterns/jobs/${id}/cancel`, {})

// ---------------------------------------------------------------- 增减条件、对比、条件库

export type LibraryModule = { key: string; name: string; category: string; condition: Condition; note: string; aliases: string[] }
export type Library = {
  categories: string[]
  modules: LibraryModule[]
  conditions: { id: number; name: string; condition: Condition; source_job: string | null }[]
  patterns: { id: number; name: string; rule: Rule; last_job: string | null; updated_at: string }[]
}
export const useLibrary = () => useQuery({ queryKey: ['pattern-library'], queryFn: () => get<Library>('/patterns/library') })
export const removeLibraryItem = (kind: 'conditions' | 'patterns', id: number) => post<Library>(`/patterns/library/${kind}/${id}/remove`, {})

export type VariantChange = { action: 'remove'; index: number } | { action: 'add'; condition: Condition }
export const variantJob = (id: string, change: VariantChange) => post<Job>(`/patterns/jobs/${id}/variant`, change)
export const rerunJob = (id: string) => post<Job>(`/patterns/jobs/${id}/rerun`, {})

export type CompareSide = {
  id: string; name: string; rule: Rule; data_version: string; data_end: string; summary: SummaryRow[]; years: YearRow[]
  events: number; stocks: number; selected: number; change?: Job['comparison_change']
}
export type Comparison = {
  left: CompareSide; right: CompareSide; comparable: boolean; differences: string[]
  common_conditions: Condition[]; only_left: Condition[]; only_right: Condition[]
  overlap: { common: number; only_left: number; only_right: number }; note: string
}
export const useCompare = (left: string, right: string) =>
  useQuery({ queryKey: ['pattern-compare', left, right], queryFn: () => get<Comparison>('/patterns/compare', { left, right }),
             enabled: !!left && !!right, retry: false, staleTime: Infinity })
