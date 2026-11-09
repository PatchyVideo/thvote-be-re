import { apiRaw, qs } from './client'

export type CatalogCategory = 'work' | 'character' | 'music'

const filenames: Record<CatalogCategory, string> = {
  work: 'works.json',
  character: 'characters.json',
  music: 'music.json',
}

export async function downloadCatalog(category: CatalogCategory): Promise<void> {
  const response = await apiRaw('/admin/export/catalog' + qs({ category }))
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filenames[category]
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
