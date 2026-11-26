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
  market_version: string
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

// ---------------------------------------------------------------- 财务与估值

export type FinancialReport = {
  date: string; published: string; format: string | null; source: string
  values: Record<string, number | null>; yoy: Record<string, number | null>
}
export type Financials = {
  code: string; available: boolean; asof: string; data_version: string; price_date?: string; close?: number | null
  valuation: { total_mcap: number | null; float_mcap: number | null; pe_ttm: number | null; ttm_loss: boolean; pb: number | null
               debt_ratio: number | null; total_shares: number | null; float_shares: number | null } | null
  ttm_profit: number | null; annual_profit: number | null; reports: FinancialReport[]
  fields: Record<'income' | 'balance' | 'cashflow', { label: string; key: string; unit: string }[]>
}
export const useFinancials = (code: string) =>
  useQuery({ queryKey: ['financials', code], queryFn: () => get<Financials>(`/securities/${code}/financials`), retry: false, staleTime: 10 * 60_000 })

// ---------------------------------------------------------------- 问个股 / 问期权 / 我的判断

export type DistStats = {
  n: number; up_prob: number; mean: number; median: number; p10: number; p90: number
  breakeven_prob?: number; payoff_mean?: number; payoff_p10?: number; payoff_p90?: number
  zones: Record<string, number>
  histogram: { from: number; to: number; n: number }[]
}
export type AskKind = 'stock' | 'option' | 'index'
export type Answer = {
  kind: AskKind; code: string; name: string; horizon: number; fee: number | null; asof: string; close: number
  data_version: string; question: string; tone: 'good' | 'bad' | 'same'; price?: string
  verdict: { label: string; value: number; dots: number; plain: string; note: string }
  facts: { label: string; value: number; note: string }[]
  voice: string
  evidence: { role: string; text: string; source: string }[]
  pending_evidence: string[]
  analysis: {
    state: { r20: number; pos60: number; vol20: number; vol_percentile: number }
    sample_range: [string, string]; all: DistStats; similar: DistStats; similar_k: number; method: string
    /** 每个相似的起点：[日期, 之后 N 个交易日的涨跌]，按日期排序 */
    similar_points: [string, number][]
    /** 期权费 1%–15% 各自的回本比例（只有问期权时有） */
    fee_curve: { fee: number; similar: number; all: number; payoff_mean: number }[] | null
  }
}
export const useAsk = (kind: AskKind, code: string, horizon: number, fee?: number) =>
  useQuery({
    queryKey: ['ask', kind, code, horizon, fee],
    queryFn: () => get<Answer>(`/ask/${kind}`, { code, horizon, fee }),
    enabled: !!code && (kind !== 'option' || !!fee),
    retry: false,
    staleTime: 10 * 60_000,
  })

/** 封存时用户自己的看法：会涨（期权：能回本）/ 不会 / 听小四的 */
export type Stance = 'yes' | 'no' | 'follow'
export type Judgment = {
  id: number; kind: AskKind; code: string; name: string; horizon: number; fee: number | null; asof: string
  data_version: string; question: string; status: 'sealed' | 'settled'; due_estimate: string; created_at: string; settled_at: string | null
  prediction: { prob: number; base_prob: number; mean: number; p10: number; p90: number; median: number; plain: string; voice: string
                price?: string | null; close: number; similar_n: number; elapsed?: number; stance?: Stance | null }
  outcome: null | { done: boolean; return: number; hit: boolean; payoff: number | null; position: string; start_date: string; end_date: string
                    start_close: number; end_close: number; path: number[] }
}
export type JudgmentRecord = {
  settled: number; hits?: number; hit_rate?: number; expected_rate?: number
  /** 自己表过态的那些：我说对几次、同一批里小四的倾向对几次、意见不同几次、其中我对几次 */
  own?: { n: number; right: number; xiaosi_right: number; differ: number; differ_right: number }
}
export const sealJudgment = (body: { kind: AskKind; code: string; horizon: number; fee?: number; stance?: Stance }) => post<Judgment>('/judgments', body)
export const useJudgments = () =>
  useQuery({ queryKey: ['judgments'], queryFn: () => get<{ items: Judgment[]; record: JudgmentRecord }>('/judgments') })
export const useJudgment = (id: string) =>
  useQuery({ queryKey: ['judgment', id], queryFn: () => get<Judgment>(`/judgments/${id}`), retry: false })

export type Series = { code: string; name: string; dates: string[]; close: number[]; data_version: string }
export const useSeries = (code: string, index = false) =>
  useQuery({ queryKey: ['series', code, index], queryFn: () => get<Series>('/ask/series', { code, index: index ? 'true' : undefined }),
             enabled: !!code, staleTime: 10 * 60_000 })

export type AskComparison = { horizon: number; asof: string; data_version: string; items: [Answer, Answer]; question: string; voice: string; lead: string | null }
export const useAskCompare = (a: string, b: string, horizon: number) =>
  useQuery({ queryKey: ['ask-compare', a, b, horizon], queryFn: () => get<AskComparison>('/ask/compare', { a, b, horizon }),
             enabled: !!a && !!b, retry: false, staleTime: 10 * 60_000 })

// ---------------------------------------------------------------- 自选股

export type WatchItem = {
  code: string; name: string; date: string | null; close: number | null; change: number | null; horizon: number
  /** 和现在相似的时候，之后 horizon 个交易日在涨的比例；base_prob 是不挑时候的比例 */
  prob: number | null; base_prob: number | null; similar_n: number | null; note: string | null
}
export type WatchlistView = { items: WatchItem[]; horizon: number; data_end: string; data_version: string }
export const useWatchlist = () => useQuery({ queryKey: ['watchlist'], queryFn: () => get<WatchlistView>('/watchlist') })
export const addWatch = (code: string) => post<WatchlistView>(`/watchlist/${code}`, {})
export const removeWatch = (code: string) => post<WatchlistView>(`/watchlist/${code}/remove`, {})

// ---------------------------------------------------------------- 方法库（内置模板，系统统一算好）

export type Method = {
  index: number; name: string; description: string; conditions: number
  status: JobStatus | 'unavailable'; job?: string; progress?: number; data_end?: string; message?: string
  summary?: SummaryRow[]; years?: YearRow[]; events?: number; selected?: number
}
export const useMethods = () =>
  useQuery({
    queryKey: ['pattern-methods'], queryFn: () => get<{ methods: Method[] }>('/patterns/methods'),
    refetchInterval: q => (q.state.data?.methods.some(m => m.status === 'queued' || m.status === 'running') ? 3000 : false),
  })

// ---------------------------------------------------------------- 自选 × 方法库

export type SignalHit = {
  index: number; method: string; description: string; job: string; date: string; price: number; change: number
  reasons: Reason[]; history: SummaryRow | null; events: number | null
}
export type Signals = {
  items: { code: string; name: string; hits: SignalHit[] }[]; quiet: string[]; watch_count: number
  methods_total: number; methods_ready: number; data_end: string | null
}
export const useSignals = () =>
  useQuery({
    queryKey: ['watch-signals'], queryFn: () => get<Signals>('/watchlist/signals'),
    refetchInterval: q => (q.state.data && q.state.data.methods_ready < q.state.data.methods_total ? 5000 : false),
  })

// ---------------------------------------------------------------- 群聊（见 docs/群聊-需求与架构.md）

export type Persona = {
  id: string; name: string; title: string; lens: string; tagline: string; role: 'guest' | 'host'; color: string
  beliefs: string[]; asks: string[]; avoids: string[]; lines: string[]; version: number; disclaimer: string
}
export type PersonaList = { available: boolean; host: Persona; items: Persona[]; default: string[]; disclaimer: string }
export const usePersonas = () => useQuery({ queryKey: ['personas'], queryFn: () => get<PersonaList>('/personas'), staleTime: 60_000 })

/** 数据卡：角色查了数据时挂在消息下面，内容由后端按引擎结果给，不是模型写的 */
export type RoomCard = { type: 'outlook' | 'recent' | 'financials' | 'option' | 'compare' | 'methods' | 'picks' } & Record<string, any>
export type RoomMessage = {
  seq: number; role: 'host' | 'guest' | 'user' | 'system'; persona_id: string | null; name: string; text: string
  reply_to: number | null; cards: RoomCard[]; action?: string | null; created_at: string | null
}
export type RoomInfo = {
  id: number; title: string; topic: { kind: string; code: string; name: string }; members: string[]
  status: 'idle' | 'playing' | 'interrupted'; created_at: string; updated_at: string
}
export type RoomDetail = RoomInfo & { messages: RoomMessage[]; playing: boolean }
export type RoomListItem = RoomInfo & { last: { name: string; text: string } | null; count: number }
export type RoomEvent =
  | { type: 'message'; message: RoomMessage }
  | { type: 'typing'; persona: string; name: string }
  | { type: 'delta'; persona: string; text: string }
  | { type: 'skipped'; persona: string }
  | { type: 'status'; status: string }
  | { type: 'scene_end'; status: string; limit?: boolean }
  | { type: 'members'; members: string[] }

export const openRoom = (code: string, members?: string[]) => post<{ id: number }>('/rooms', { code, members })
export const useRooms = () => useQuery({ queryKey: ['rooms'], queryFn: () => get<{ items: RoomListItem[] }>('/rooms'), staleTime: 0 })
export const getRoom = (id: number | string) => get<RoomDetail>(`/rooms/${id}`)
export const sayInRoom = (id: number | string, text: string) => post<{ ok: boolean }>(`/rooms/${id}/say`, { text })
export const continueRoom = (id: number | string) => post<{ ok: boolean }>(`/rooms/${id}/continue`, {})
export const setRoomMembers = (id: number | string, change: { add?: string; remove?: string }) => post<{ members: string[] }>(`/rooms/${id}/members`, change)

// ---- 管理端 · 角色管理
export type AdminPersona = Persona & { enabled: boolean; in_default: boolean; sort: number; builtin: boolean; custom: boolean; saved_versions: number }
export type AdminPersonaDetail = AdminPersona & {
  content: string; builtin_version: number | null
  versions: { version: number; note: string | null; created_at: string; created_by: number | null }[]
}
export type AdminPersonaList = { items: AdminPersona[]; tools: { name: string; description: string }[]; template: string; available: boolean }
export const useAdminPersonas = () => useQuery({ queryKey: ['admin-personas'], queryFn: () => get<AdminPersonaList>('/admin/personas'), staleTime: 0 })
export const getAdminPersona = (id: string) => get<AdminPersonaDetail>(`/admin/personas/${id}`)
export const getPersonaVersion = (id: string, version: number) => get<{ version: number; content: string }>(`/admin/personas/${id}/versions/${version}`)
export const savePersona = (id: string | null, content: string, note: string) =>
  post<AdminPersonaDetail>(id ? `/admin/personas/${id}/versions` : '/admin/personas', { content, note })
export const switchPersonaVersion = (id: string, version: number | null) => post<AdminPersonaDetail>(`/admin/personas/${id}/use`, { version })
export const configurePersona = (id: string, s: { enabled?: boolean; in_default?: boolean; sort?: number }) => post<AdminPersonaDetail>(`/admin/personas/${id}/settings`, s)
export const tryPersona = (content: string, code: string, cue = '') =>
  post<{ ok: boolean; text: string; note?: string; data?: string[]; stock?: string; seconds?: number }>('/admin/personas/try', { content, code, cue })

// ---------------------------------------------------------------- 选股名单

export type PickStrategy = { id: string; name: string; alias: string; publish_at: string; tagline: string; rules: string[] }
export type PickHeadline = {
  days: number; start: string; end: string; sealed_rate: number; market_sealed_rate: number | null; any_sealed_rate: number; intraday_mean: number
}
export type PickItem = {
  rank: number; code: string; name: string; board: string | null; auction_pct: number | null; limit_price: number | null
  open: number | null; close: number | null; open_pct: number | null; day_pct: number | null; intraday: number | null
  sealed: boolean | null; touched: boolean | null; next_open_ret: number | null; next_date: string | null; settled: boolean
}
export type PickDay = {
  strategy: PickStrategy; date: string | null; items: PickItem[]; days: string[]; data_end: string; today: string; is_today: boolean; settled: boolean
}
export type PickBlock = {
  n: number; sealed_rate: number; touched_rate: number; open_pct_median: number; intraday_mean: number; intraday_median: number
  intraday_win: number; day_up_rate: number; next_open_mean: number | null; next_open_win: number | null
}
export type PickBase = { n: number; sealed_rate: number; touched_rate: number; intraday_mean: number; intraday_win: number }
export type PickStats = {
  strategy: PickStrategy
  range: { start: string; end: string; days: number; n: number } | null
  overall: PickBlock
  recent: (PickBlock & { days: number; start: string }) | null
  per_day: { any_sealed_rate: number; sealed_mean: number; up_day_rate: number }
  by_rank: (PickBlock & { label: string })[]
  by_board: (PickBlock & { label: string })[]
  by_month: (PickBlock & { label: string })[]
  baseline: { market: PickBase | null; same_gap: PickBase | null }
}
export type StockPick = { strategy: string; name: string; alias: string; date: string; rank: number; auction_pct: number | null; headline: PickHeadline | null }

export const usePickStrategies = () =>
  useQuery({ queryKey: ['picks'], queryFn: () => get<{ items: (PickStrategy & { latest_date: string | null; headline: PickHeadline | null })[] }>('/picks'), staleTime: 60_000 })
export const usePickDay = (strategy: string, date?: string) =>
  useQuery({ queryKey: ['picks', strategy, 'day', date ?? 'latest'], queryFn: () => get<PickDay>(`/picks/${strategy}`, { date }),
             placeholderData: keepPreviousData, staleTime: 30_000 })
export const usePickStats = (strategy: string) =>
  useQuery({ queryKey: ['picks', strategy, 'stats'], queryFn: () => get<PickStats>(`/picks/${strategy}/stats`), staleTime: 5 * 60_000 })
export const useStockPick = (code: string) =>
  useQuery({ queryKey: ['picks', 'stock', code], queryFn: () => get<{ pick: StockPick | null }>(`/picks/stock/${code}`), staleTime: 60_000 })
