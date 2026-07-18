<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { logsApi } from '@/api/logs'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import type { ActivityLogItem, Paged } from '@/api/types'
import type { Column } from '@/components/types'

const cols: Column[] = [
  { key: 'created_at', label: '时间' },
  { key: 'event_type', label: '事件' },
  { key: 'user_id', label: '用户' },
  { key: 'requester_ip', label: 'IP' },
]

const filters = reactive({ user_id: '', action: '', since: '' })
const { data, loading, run } = useAsync<Paged<ActivityLogItem>>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } =
  usePagination(50)

async function load(): Promise<void> {
  const r = await run(() =>
    logsApi.list({
      user_id: filters.user_id,
      action: filters.action,
      since: filters.since,
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
</script>

<template>
  <div class="h1">操作日志</div>
  <FilterBar>
    <div>
      <label class="lbl">用户ID</label>
      <input class="field" v-model="filters.user_id" @keyup.enter="search" />
    </div>
    <div>
      <label class="lbl">事件类型</label>
      <input class="field" v-model="filters.action" @keyup.enter="search" />
    </div>
    <div>
      <label class="lbl">起始时间</label>
      <input
        class="field"
        v-model="filters.since"
        placeholder="ISO 如 2026-07-01T00:00:00Z"
        @keyup.enter="search"
      />
    </div>
    <template #actions>
      <button class="btn" @click="search">搜索</button>
    </template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="无日志"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-created_at="{ value }">
      <span class="small mono">{{ value ? String(value).slice(0, 19) : '—' }}</span>
    </template>
    <template #cell-user_id="{ value }">
      <span class="mono small">{{ value ? String(value).slice(0, 16) : '—' }}</span>
    </template>
    <template #cell-requester_ip="{ value }">{{ value || '—' }}</template>
  </DataTable>
</template>
