<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { monitorApi } from '@/api/monitor'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import { VOTE_CATEGORIES, type VoteRow, type VotesPage } from '@/api/types'
import type { Column } from '@/components/types'

const filters = reactive({
  category: 'character',
  vote_id: '',
  user_ip: '',
  device: '',
  invalidated: '',
})
const { data, loading, run } = useAsync<VotesPage>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } =
  usePagination(50)
const { toast } = useToast()

const cols: Column[] = [
  { key: 'vote_id', label: '账号' },
  { key: 'user_ip', label: 'IP' },
  { key: 'device', label: '设备' },
  { key: 'fill_duration_ms', label: '首投耗时' },
  { key: 'attempt', label: '改票' },
  { key: 'invalidated', label: '状态' },
  { key: 'created_at', label: '时间' },
  { key: 'actions', label: '操作', width: '84px' },
]

async function load(): Promise<void> {
  const inv =
    filters.invalidated === '' ? undefined : filters.invalidated === 'true'
  const r = await run(() =>
    monitorApi.votes({
      category: filters.category,
      vote_id: filters.vote_id,
      user_ip: filters.user_ip,
      device: filters.device,
      invalidated: inv,
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

async function toggle(row: VoteRow): Promise<void> {
  const action = row.invalidated ? '恢复' : '作废'
  if (!confirm(`确认${action}该投票 (id=${row.id})？仅记录标记,不即时影响排名(依赖 B-050)。`))
    return
  try {
    const r = row.invalidated
      ? await monitorApi.restore(filters.category, row.id)
      : await monitorApi.invalidate(filters.category, row.id)
    toast(action + '成功: ' + r.detail, 'success')
    load()
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="h1">投票浏览器</div>
  <FilterBar>
    <div>
      <label class="lbl">类别</label>
      <select class="field" v-model="filters.category" @change="search">
        <option v-for="c in VOTE_CATEGORIES" :key="c" :value="c">{{ c }}</option>
      </select>
    </div>
    <div>
      <label class="lbl">账号</label>
      <input class="field" v-model="filters.vote_id" @keyup.enter="search" />
    </div>
    <div>
      <label class="lbl">IP</label>
      <input class="field" v-model="filters.user_ip" @keyup.enter="search" />
    </div>
    <div>
      <label class="lbl">设备</label>
      <input class="field" v-model="filters.device" @keyup.enter="search" />
    </div>
    <div>
      <label class="lbl">作废</label>
      <select class="field" v-model="filters.invalidated" @change="search">
        <option value="">全部</option>
        <option value="true">仅作废</option>
        <option value="false">仅有效</option>
      </select>
    </div>
    <template #actions><button class="btn" @click="search">查询</button></template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="无投票"
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
    <template #cell-user_ip="{ value }"><span class="mono small">{{ value }}</span></template>
    <template #cell-device="{ value }">
      <span class="mono small">{{ value ? String(value).slice(0, 12) : '—' }}</span>
    </template>
    <template #cell-fill_duration_ms="{ value }">
      {{ value == null ? '—' : value + 'ms' }}
    </template>
    <template #cell-attempt="{ value }">{{ value ?? '—' }}</template>
    <template #cell-invalidated="{ value }">
      <span class="badge" :class="value ? 'bad' : 'ok'">{{ value ? '已作废' : '有效' }}</span>
    </template>
    <template #cell-created_at="{ value }">
      <span class="small mono">
        {{ value ? String(value).slice(0, 19).replace('T', ' ') : '—' }}
      </span>
    </template>
    <template #cell-actions="{ row }">
      <button class="icobtn" :class="{ danger: !row.invalidated }" @click="toggle(row)">
        {{ row.invalidated ? '恢复' : '作废' }}
      </button>
    </template>
  </DataTable>
</template>
