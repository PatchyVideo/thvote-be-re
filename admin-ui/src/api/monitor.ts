import { apiGet, apiSend, qs } from './client'
import type {
  AccountDetail,
  ActionResult,
  GroupsResponse,
  OverviewResponse,
  SuspectsResponse,
  VotesPage,
} from './types'

type Kind = 'ip' | 'device'

// B-049 监控端点(/api/v1/admin/monitor/*)。
export const monitorApi = {
  overview: () => apiGet<OverviewResponse>('/admin/monitor/overview'),

  groups: (kind: Kind, min_size: number, limit: number) =>
    apiGet<GroupsResponse>('/admin/monitor/groups' + qs({ kind, min_size, limit })),

  members: (kind: Kind, key: string) =>
    apiGet<string[]>(
      `/admin/monitor/groups/${kind}/${encodeURIComponent(key)}/members`,
    ),

  suspects: (page: number, page_size: number) =>
    apiGet<SuspectsResponse>('/admin/monitor/suspects' + qs({ page, page_size })),

  votes: (p: {
    category: string
    vote_id?: string
    user_ip?: string
    device?: string
    invalidated?: boolean
    page: number
    page_size: number
  }) => apiGet<VotesPage>('/admin/monitor/votes' + qs(p)),

  account: (voteId: string) =>
    apiGet<AccountDetail>(`/admin/monitor/account/${encodeURIComponent(voteId)}`),

  invalidate: (category: string, rowId: number) =>
    apiSend<ActionResult>(
      `/admin/monitor/vote/${category}/${rowId}/invalidate`,
      'PATCH',
    ),
  restore: (category: string, rowId: number) =>
    apiSend<ActionResult>(
      `/admin/monitor/vote/${category}/${rowId}/restore`,
      'PATCH',
    ),
  review: (voteId: string, body: { status: string; note: string }) =>
    apiSend<ActionResult>(
      `/admin/monitor/account/${encodeURIComponent(voteId)}/review`,
      'PATCH',
      body,
    ),
}
