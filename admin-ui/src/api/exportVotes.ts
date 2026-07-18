import { apiRaw, qs } from './client'

// 导出投票 CSV(StreamingResponse)→ 触发浏览器下载。
export const exportApi = {
  async votes(vote_year: number, category: string): Promise<void> {
    const r = await apiRaw('/admin/export/votes' + qs({ vote_year, category }))
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `votes_${vote_year}_${category}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}
