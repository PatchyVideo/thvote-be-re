<script setup lang="ts">
import { onMounted } from 'vue'
import { monitorApi } from '@/api/monitor'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import DataTable from '@/components/DataTable.vue'
import type { SuspectsResponse } from '@/api/types'
import type { Column } from '@/components/types'

const { data, loading, run } = useAsync<SuspectsResponse>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev } =
  usePagination(50)

const cols: Column[] = [
  { key: 'vote_id', label: '账号' },
  { key: 'score', label: '可疑分', width: '90px' },
  { key: 'reasons', label: '命中原因' },
]

async function load(): Promise<void> {
  const r = await run(() => monitorApi.suspects(page.value, size.value))
  if (r) setTotal(r.total)
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
  <div class="h1">可疑名单</div>
  <div
    v-if="data?.truncated"
    class="card small"
    style="color: var(--warn)"
  >
    候选账号超过上限,名单已截断(仅评分部分候选)。
  </div>
  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="暂无可疑账号"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-vote_id="{ value }">
      <RouterLink class="mono" :to="'/monitor/account/' + value">{{ value }}</RouterLink>
    </template>
    <template #cell-score="{ value }">
      <span class="badge score">{{ value }}</span>
    </template>
    <template #cell-reasons="{ value }">
      <span class="small">{{ (value || []).join('；') }}</span>
    </template>
  </DataTable>
</template>
