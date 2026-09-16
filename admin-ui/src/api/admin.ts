import { apiBare, apiGet, apiSend, qs } from './client'
import type {
  BanResponse,
  ReloadConfigResponse,
  StatsResponse,
  UserListResponse,
} from './types'

export interface CacheStatsResponse {
  counts: Record<string, number>
  scopes: string[]
}

export interface CacheFlushResponse {
  ok: boolean
  scope: string
  deleted: Record<string, number>
  total: number
}

// 现有 admin 端点(Phase 1 用到的子集:stats/users/封解封/快捷动作)。
export const adminApi = {
  stats: () => apiGet<StatsResponse>('/admin/stats'),

  users: (p: { email?: string; phone?: string; page: number; page_size: number }) =>
    apiGet<UserListResponse>('/admin/users' + qs(p)),

  ban: (id: string) =>
    apiSend<BanResponse>(`/admin/users/${encodeURIComponent(id)}/ban`, 'PATCH'),
  unban: (id: string) =>
    apiSend<BanResponse>(`/admin/users/${encodeURIComponent(id)}/unban`, 'PATCH'),

  computeResults: () =>
    apiSend<Record<string, unknown>>('/admin/compute-results', 'POST'),
  finalizeRanking: () =>
    apiSend<Record<string, unknown>>('/admin/finalize-ranking', 'POST'),

  cacheStats: () => apiGet<CacheStatsResponse>('/admin/cache/stats'),
  flushCache: (scope: string) =>
    apiSend<CacheFlushResponse>('/admin/cache/flush', 'POST', { scope }),

  // 裸端点(不带 /api/v1),见 client.apiBare。
  reloadConfig: () => apiBare<ReloadConfigResponse>('/admin/reload-config', 'POST'),
}
