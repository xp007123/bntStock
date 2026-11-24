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
