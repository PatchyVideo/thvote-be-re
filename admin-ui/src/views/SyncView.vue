<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { SYNC_COLLECTIONS, syncApi } from '@/api/sync'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import StatCard from '@/components/StatCard.vue'
import type { Paged, SyncHistoryItem, SyncStatus } from '@/api/types'
import type { Column } from '@/components/types'

const historyCols: Column[] = [
  { key: 'run_id', label: 'Run ID' },
  { key: 'started_at', label: '开始' },
  { key: 'completed_at', label: '结束' },
  { key: 'status', label: '状态' },
  { key: 'collections', label: '集合' },
  { key: 'inserted', label: '插入' },
  { key: 'skipped', label: '跳过' },
  { key: 'errors', label: '错误' },
  { key: 'initiated_by', label: '发起' },
  { key: 'actions', label: '操作', width: '84px' },
]

const batchSize = ref(500)
const selected = ref<string[]>([])
const status = ref<SyncStatus | null>(null)
// 记录上一次的 run_id:status() 永远不返回 completed/failed,只能靠
// run_id 从非空变回 null(running → idle)推断"本轮已结束"。
const prevRunId = ref<string | null>(null)
const {
  data: history,
  loading: historyLoading,
  run: runHistory,
} = useAsync<Paged<SyncHistoryItem>>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev } =
  usePagination(20)
const { toast } = useToast()

let timer: number | undefined

async function loadHistory(): Promise<void> {
  const r = await runHistory(() => syncApi.history(page.value, size.value))
  if (r) setTotal(r.total)
}
function goPrev(): void {
  prev()
  loadHistory()
}
function goNext(): void {
  next()
  loadHistory()
}

async function pollStatus(): Promise<void> {
  try {
    const s = await syncApi.status()
    if (prevRunId.value !== null && s.run_id === null) {
      loadHistory()
    }
    prevRunId.value = s.run_id
    status.value = s
  } catch {
    // 轮询失败是瞬时的(网络抖动等),忽略即可,不打扰用户
  }
}

onMounted(() => {
  loadHistory()
  pollStatus()
  timer = window.setInterval(pollStatus, 2000)
})
onUnmounted(() => {
  if (timer !== undefined) window.clearInterval(timer)
})

async function startSync(): Promise<void> {
  if (!confirm('开始全量同步？')) return
  try {
    const r = await syncApi.start(selected.value, batchSize.value)
    toast('已启动: ' + r.run_id, 'success')
    loadHistory()
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}

async function cancelSync(): Promise<void> {
  try {
    await syncApi.cancel()
    toast('已发送取消信号', 'success')
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}

async function retry(row: SyncHistoryItem): Promise<void> {
  if (!confirm(`从断点重试此运行 (${row.run_id.slice(0, 8)})？`)) return
  try {
    await syncApi.retry(row.run_id)
    toast('已重新启动', 'success')
    loadHistory()
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}

function statusBadge(s: string): string {
  if (s === 'completed') return 'ok'
  if (s === 'failed') return 'bad'
  return 'gray'
}

// LIVE 卡片:status() 永远不返回 completed/failed,只能靠 run_id 是否非空判断是否运行中。
function liveBadgeClass(s: SyncStatus): string {
  return s.run_id !== null ? 'upcoming' : 'gray'
}
function liveBadgeText(s: SyncStatus): string {
  return s.run_id !== null ? '运行中' : '空闲'
}
</script>

<template>
  <div class="h1">数据同步</div>

  <div class="card">
    <div class="h2">控制</div>
    <div class="row">
      <div>
        <label class="lbl">批次大小</label>
        <input class="field" type="number" v-model.number="batchSize" style="width: 100px" />
      </div>
      <button class="btn" @click="startSync">开始同步</button>
      <button class="btn danger" @click="cancelSync">取消</button>
    </div>

    <div class="row" style="margin-top: 0.6rem">
      <label v-for="c in SYNC_COLLECTIONS" :key="c">
        <input type="checkbox" :value="c" v-model="selected" />
        {{ c }}
      </label>
    </div>
    <div class="muted small">不选=全部同步</div>

    <template v-if="status">
      <div class="row" style="margin-top: 1rem">
        <span>
          状态: <span class="badge" :class="liveBadgeClass(status)">{{ liveBadgeText(status) }}</span>
        </span>
        <span class="muted small">当前集合: {{ status.current_collection || '—' }}</span>
      </div>
      <progress
        :value="status.processed"
        :max="Math.max(status.total, 1)"
        style="width: 100%; margin-top: 0.6rem"
      ></progress>
      <div class="stats" style="margin-top: 0.6rem">
        <StatCard :value="`${status.processed}/${status.total}`" label="进度" />
        <StatCard :value="status.inserted" label="插入" />
        <StatCard :value="status.skipped" label="跳过" />
        <StatCard :value="status.errors" label="错误" />
      </div>
    </template>
  </div>

  <div class="h2">历史记录</div>
  <DataTable
    :columns="historyCols"
    :rows="history?.items || []"
    :loading="historyLoading"
    empty-text="暂无记录"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-run_id="{ value }"><span class="mono small">{{ value }}</span></template>
    <template #cell-started_at="{ value }">
      <span class="small mono">{{ String(value).slice(0, 19) }}</span>
    </template>
    <template #cell-completed_at="{ value }">
      <span class="small mono">{{ value ? String(value).slice(0, 19) : '—' }}</span>
    </template>
    <template #cell-status="{ value }">
      <span class="badge" :class="statusBadge(value)">{{ value }}</span>
    </template>
    <template #cell-collections="{ value }">{{ (value || []).join(', ') || '—' }}</template>
    <template #cell-actions="{ row }">
      <button class="icobtn" @click="retry(row)">重试</button>
    </template>
  </DataTable>
</template>
