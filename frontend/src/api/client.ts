import { keepPreviousData, useQuery } from '@tanstack/react-query'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const query = params
    ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)])).toString()
    : ''
  const res = await fetch(`/api${path}${query}`)
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* 非 JSON 错误体 */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

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

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* 非 JSON 错误体 */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

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

export const useJobEvents = (id: string, page: number, sort: 'date' | 'return', horizon: number, pageSize = 20) =>
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
