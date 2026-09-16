import { apiGet, apiSend, qs } from './client'

export interface VoteableRow {
  id: number
  name: string
  nameJp: string
  type: string
  firstAppearance: string | null
  workId: number | null
  workName: string | null
  workType: string | null
  /** 资源类字段（0019 后端下发 / 本页编辑） */
  imageUrl: string | null
  aliases: string[]
  /** 仅 category=music */
  musicUrl?: string | null
  include?: string[]
}

export interface VoteableListResponse {
  items: VoteableRow[]
  total: number
}

export interface ResourceUpdatePayload {
  category: string
  image_url?: string | null
  aliases?: string[]
  music_url?: string | null
  include?: string[]
}

export const voteablesApi = {
  list: (p: { category: string; q?: string; page: number; page_size: number }) =>
    apiGet<VoteableListResponse>('/admin/voteables' + qs(p)),

  updateResources: (id: number, body: ResourceUpdatePayload) =>
    apiSend<{ ok: boolean }>(`/admin/voteables/${id}/resources`, 'PUT', body),
}
