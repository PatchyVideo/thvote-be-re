import { apiGet, apiSend, qs } from './client'
import type { NominationItem, Paged } from './types'

export const nominationsApi = {
  list: (p: { status: string; page: number; page_size: number }) =>
    apiGet<Paged<NominationItem>>('/admin/nominations' + qs(p)),
  approve: (id: number) =>
    apiSend<{ ok: boolean }>(`/admin/nominations/${id}/approve`, 'PATCH'),
  reject: (id: number, reason: string) =>
    apiSend<{ ok: boolean }>(`/admin/nominations/${id}/reject`, 'PATCH', { reason }),
}
