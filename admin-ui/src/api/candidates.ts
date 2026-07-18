import { apiGet, apiSend, qs } from './client'
import type {
  CandidateAdminItem,
  CandidateField,
  CandidateImportResult,
  MergeItem,
  Paged,
} from './types'

export const candidatesApi = {
  list: (p: {
    category: string
    vote_year?: number
    q?: string
    page: number
    page_size: number
  }) => apiGet<Paged<CandidateAdminItem>>('/admin/candidates' + qs(p)),

  fields: (category: string) =>
    apiGet<{ category: string; fields: CandidateField[] }>(
      '/admin/candidates/fields' + qs({ category }),
    ),

  import: (body: {
    vote_year: number
    category: string
    format: string
    content: string
    dry_run: boolean
  }) => apiSend<CandidateImportResult>('/admin/candidates/import', 'POST', body),

  update: (id: number, category: string, fields: Record<string, string>) =>
    apiSend<{ ok: boolean }>(`/admin/candidates/${id}`, 'PUT', { category, fields }),

  remove: (id: number, category: string) =>
    apiSend<{ ok: boolean }>(`/admin/candidates/${id}` + qs({ category }), 'DELETE'),

  merges: (category: string, vote_year?: number) =>
    apiGet<{ items: MergeItem[] }>(
      '/admin/candidates/merges' + qs({ category, vote_year }),
    ),

  mergeInto: (id: number, targetId: number, category: string) =>
    apiSend<{ ok: boolean }>(
      `/admin/candidates/${id}/merge-into/${targetId}` + qs({ category }),
      'POST',
    ),

  unmerge: (id: number, category: string) =>
    apiSend<{ ok: boolean }>(
      `/admin/candidates/${id}/unmerge` + qs({ category }),
      'POST',
    ),
}
