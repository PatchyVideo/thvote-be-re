<script setup lang="ts">
import { onMounted } from 'vue'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { useToast } from '@/composables/useToast'
import StatCard from '@/components/StatCard.vue'
import type { StatsResponse } from '@/api/types'

const { data, loading, run } = useAsync<StatsResponse>()
const { toast } = useToast()

function load(): void {
  run(() => adminApi.stats())
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
  </template>
</template>
