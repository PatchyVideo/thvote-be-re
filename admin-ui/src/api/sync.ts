import { apiGet, apiSend } from './client'
import type { Paged, SyncHistoryItem, SyncStartResult, SyncStatus } from './types'

// 合法 collection 名(runner COLLECTION_CONFIG);start 传 [] = 全部。
export const SYNC_COLLECTIONS = [
  'voters',
  'raw_character',
  'raw_music',
  'raw_cp',
  'raw_work',
  'raw_paper',
  'raw_dojin',
  'final_ranking_char',
  'final_ranking_music',
  'chars',
  'musics',
] as const

export const syncApi = {
  start: (collections: string[], batch_size: number) =>
    apiSend<SyncStartResult>('/admin/sync/start', 'POST', { collections, batch_size }),
  status: () => apiGet<SyncStatus>('/admin/sync/status'),
  history: () => apiGet<Paged<SyncHistoryItem>>('/admin/sync/history'),
  cancel: () => apiSend<{ ok: boolean }>('/admin/sync/cancel', 'POST'),
  retry: (runId: string) =>
    apiSend<SyncStartResult>(
      `/admin/sync/retry/${encodeURIComponent(runId)}`,
      'POST',
    ),
}
