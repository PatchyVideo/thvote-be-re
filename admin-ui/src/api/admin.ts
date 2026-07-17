import { apiBare, apiGet, apiSend, qs } from './client'
import type {
  BanResponse,
  ReloadConfigResponse,
  StatsResponse,
  UserListResponse,
} from './types'

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

  // 裸端点(不带 /api/v1),见 client.apiBare。
  reloadConfig: () => apiBare<ReloadConfigResponse>('/admin/reload-config', 'POST'),
}
