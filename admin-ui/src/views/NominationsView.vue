<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { nominationsApi } from '@/api/nominations'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import type { NominationItem, Paged } from '@/api/types'
import type { Column } from '@/components/types'

const cols: Column[] = [
  { key: 'title', label: '标题' },
  { key: 'author', label: '作者' },
  { key: 'url', label: '链接' },
  { key: 'udid', label: 'UDID' },
  { key: 'publish_date', label: '发布' },
  { key: 'status', label: '状态' },
  { key: 'reject_reason', label: '驳回原因' },
  { key: 'actions', label: '操作', width: '120px' },
]

const filters = reactive({ status: 'pending' })
const { data, loading, run } = useAsync<Paged<NominationItem>>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } =
  usePagination(50)
const { toast } = useToast()

async function load(): Promise<void> {
  const r = await run(() =>
    nominationsApi.list({
      status: filters.status,
      page: page.value,
      page_size: size.value,
    }),
  )
  if (r) setTotal(r.total)
}
function search(): void {
  reset()
  load()
}
function goPrev(): void {
  prev()
  load()
}
function goNext(): void {
  next()
  load()
}
onMounted(load)

function statusClass(status: string): string {
  if (status === 'approved') return 'ok'
  if (status === 'rejected') return 'bad'
  return 'gray'
}

async function approveOne(item: NominationItem): Promise<void> {
  if (!confirm(`确认通过《${item.title}》？`)) return
  try {
    await nominationsApi.approve(item.id)
    toast('已通过', 'success')
    load()
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}
async function rejectOne(item: NominationItem): Promise<void> {
  const reason = prompt('驳回原因？')
  if (reason === null) return
  try {
    await nominationsApi.reject(item.id, reason || '')
    toast('已驳回', 'success')
    load()
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="h1">投稿审核</div>
  <FilterBar>
    <div>
      <label class="lbl">状态</label>
      <select class="field" v-model="filters.status" @change="search">
        <option value="pending">待审核</option>
        <option value="approved">已通过</option>
        <option value="rejected">已驳回</option>
        <option value="all">全部</option>
      </select>
    </div>
    <template #actions>
      <button class="btn" @click="search">刷新</button>
    </template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="无投稿"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-url="{ value }">
      <a :href="value" target="_blank">打开↗</a>
    </template>
    <template #cell-udid="{ value }">{{ value || '—' }}</template>
    <template #cell-publish_date="{ value }">
      {{ value ? String(value).slice(0, 10) : '—' }}
    </template>
    <template #cell-status="{ value }">
      <span class="badge" :class="statusClass(value)">{{ value }}</span>
    </template>
    <template #cell-reject_reason="{ value }">{{ value || '—' }}</template>
    <template #cell-actions="{ row }">
      <template v-if="row.status === 'pending'">
        <button class="icobtn" @click="approveOne(row)">通过</button>
        <button class="icobtn danger" @click="rejectOne(row)">驳回</button>
      </template>
      <span v-else class="muted small">—</span>
    </template>
  </DataTable>
</template>
