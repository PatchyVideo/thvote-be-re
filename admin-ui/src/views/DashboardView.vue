<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminApi, type CacheStatsResponse } from '@/api/admin'
import { ApiError } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { useToast } from '@/composables/useToast'
import StatCard from '@/components/StatCard.vue'
import type { StatsResponse } from '@/api/types'

const { data, loading, run } = useAsync<StatsResponse>()
const { toast } = useToast()

const cache = ref<CacheStatsResponse | null>(null)
const cacheBusy = ref(false)

const CACHE_SCOPES: Array<{ key: string; label: string }> = [
  { key: 'vote_objects', label: '投票对象' },
  { key: 'questionnaire', label: '问卷结构' },
  { key: 'autocomplete', label: '自动补全' },
  { key: 'nominations', label: '已通过提名' },
]

async function loadCache(): Promise<void> {
  try {
    cache.value = await adminApi.cacheStats()
  } catch {
    cache.value = null
  }
}

function load(): void {
  run(() => adminApi.stats())
  loadCache()
}
onMounted(load)

async function quick(kind: 'compute' | 'finalize' | 'reload'): Promise<void> {
  const msg =
    kind === 'compute'
      ? '触发排名计算？'
      : kind === 'finalize'
        ? '归档最终排名？'
        : '热更新配置？'
  if (!confirm(msg)) return
  try {
    const r =
      kind === 'compute'
        ? await adminApi.computeResults()
        : kind === 'finalize'
          ? await adminApi.finalizeRanking()
          : await adminApi.reloadConfig()
    toast('完成: ' + JSON.stringify(r).slice(0, 100), 'success')
    load()
  } catch (e) {
    if (e instanceof ApiError && (e.status === 403 || e.status === 401)) return
    toast(e instanceof ApiError ? e.detail : (e as Error).message, 'error')
  }
}

async function flush(scope: string): Promise<void> {
  const label = scope === 'all' ? '全部缓存' : CACHE_SCOPES.find((s) => s.key === scope)?.label ?? scope
  if (!confirm(`确定刷新「${label}」吗？下次请求会重新查库。`)) return
  cacheBusy.value = true
  try {
    const r = await adminApi.flushCache(scope)
    toast(`已清理 ${r.total} 个缓存键`, 'success')
    await loadCache()
  } catch (e) {
    if (e instanceof ApiError && (e.status === 403 || e.status === 401)) return
    toast(e instanceof ApiError ? e.detail : (e as Error).message, 'error')
  } finally {
    cacheBusy.value = false
  }
}
</script>

<template>
  <div class="h1">仪表盘</div>
  <div v-if="loading && !data" class="card loading">加载中…</div>
  <template v-else-if="data">
    <div class="stats">
      <StatCard :value="data.vote_year" label="投票年份" />
      <StatCard :value="data.total_users" label="总用户" />
      <StatCard
        v-for="(v, k) in data.submissions"
        :key="k"
        :value="v"
        :label="k + ' 提交'"
      />
      <StatCard value="" label="投票窗口">
        <template #value>
          <span class="badge" :class="data.vote_window.status">
            {{ data.vote_window.status }}
          </span>
        </template>
      </StatCard>
    </div>
    <div class="card">
      <div class="h2">操作</div>
      <div class="row">
        <button class="btn" @click="quick('compute')">Compute Results</button>
        <button class="btn" @click="quick('finalize')">Finalize Ranking</button>
        <button class="btn ghost" @click="quick('reload')">Reload Config</button>
      </div>
      <div class="muted small" style="margin-top: 0.5rem">
        窗口: {{ data.vote_window.start }} → {{ data.vote_window.end }}
      </div>
    </div>

    <div class="card">
      <div class="h2">缓存</div>
      <div class="muted small" style="margin-bottom: 0.5rem">
        投票对象/问卷/自动补全/提名列表都由 Redis 缓存，管理端写入会自动失效；
        这里可手动强制刷新。结果页榜单是计票产物，请用上方 Compute Results 重建。
      </div>
      <div class="row" style="flex-wrap: wrap; gap: 0.5rem">
        <button
          v-for="s in CACHE_SCOPES"
          :key="s.key"
          class="btn ghost"
          :disabled="cacheBusy"
          @click="flush(s.key)"
        >
          {{ s.label }}<span v-if="cache" class="muted">（{{ cache.counts[s.key] ?? 0 }}）</span>
        </button>
        <button class="btn" :disabled="cacheBusy" @click="flush('all')">
          全部刷新
        </button>
        <button class="btn ghost" :disabled="cacheBusy" @click="loadCache">刷新计数</button>
      </div>
    </div>
  </template>
</template>
