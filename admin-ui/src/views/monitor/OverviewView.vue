<script setup lang="ts">
import { onMounted } from 'vue'
import { monitorApi } from '@/api/monitor'
import { useAsync } from '@/composables/useAsync'
import DataTable from '@/components/DataTable.vue'
import StatCard from '@/components/StatCard.vue'
import type { OverviewResponse } from '@/api/types'
import type { Column } from '@/components/types'

const { data, loading, run } = useAsync<OverviewResponse>()
const dayCols: Column[] = [
  { key: 'date', label: '日期' },
  { key: 'count', label: '提交数' },
]
onMounted(() => run(() => monitorApi.overview()))
</script>

<template>
  <div class="h1">流量概览</div>
  <div v-if="loading && !data" class="card loading">加载中…</div>
  <template v-else-if="data">
    <div class="stats">
      <StatCard :value="data.distinct_ips" label="去重 IP" />
      <StatCard :value="data.distinct_devices" label="去重设备" />
      <StatCard
        v-for="(v, k) in data.category_totals"
        :key="k"
        :value="v"
        :label="k + ' 投票人'"
      />
    </div>
    <div class="h2">按天提交</div>
    <DataTable :columns="dayCols" :rows="data.submissions_by_day" empty-text="暂无提交" />
  </template>
</template>
