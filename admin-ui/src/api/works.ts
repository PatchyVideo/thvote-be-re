import { apiGet, apiSend, qs } from './client'

export interface WorkRow {
  workId: number
  name: string
  type: string
  characterCount: number
  musicCount: number
  createdAt: string | null
}

export interface WorkListResponse {
  items: WorkRow[]
  total: number
}

export async function listWorks(params: {
  q?: string
  type?: string
  page?: number
  pageSize?: number
}): Promise<WorkListResponse> {
  return apiGet<WorkListResponse>(`/admin/works${qs(params)}`)
}

export async function createWork(data: { name: string; type: string }): Promise<{ workId: number }> {
  return apiSend<{ workId: number }>('/admin/works', 'POST', data)
}

export async function updateWork(
  id: number,
  data: { name?: string; type?: string },
): Promise<{ ok: boolean }> {
  return apiSend<{ ok: boolean }>(`/admin/works/${id}`, 'POST', data)
}

export async function deleteWork(id: number): Promise<{ ok: boolean }> {
  return apiSend<{ ok: boolean }>(`/admin/works/${id}`, 'DELETE')
}
