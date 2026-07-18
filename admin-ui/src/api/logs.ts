import { apiGet, qs } from './client'
import type { ActivityLogItem, Paged } from './types'

export const logsApi = {
  list: (p: {
    user_id?: string
    action?: string
    since?: string
    page: number
    page_size: number
  }) => apiGet<Paged<ActivityLogItem>>('/admin/activity-logs' + qs(p)),
}
