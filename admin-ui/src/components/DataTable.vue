<script setup lang="ts">
import type { Column } from './types'

// 通用表格 + 可选分页页脚。cell-<key> 具名插槽自定义单元格;传 pageCount 才显示分页。
defineProps<{
  columns: Column[]
  // 通用表格:行为任意对象数组(具体类型由 view 保证);cell 插槽拿 row/value。
  rows: any[]
  loading?: boolean
  emptyText?: string
  page?: number
  pageCount?: number
  total?: number
  hasPrev?: boolean
  hasNext?: boolean
}>()
const emit = defineEmits<{ (e: 'prev'): void; (e: 'next'): void }>()
</script>

<template>
  <div class="card">
    <div class="tbl-wrap">
      <table class="tbl">
        <thead>
          <tr>
            <th
              v-for="c in columns"
              :key="c.key"
              :style="c.width ? { width: c.width } : undefined"
            >
              {{ c.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td v-for="c in columns" :key="c.key">
              <slot :name="'cell-' + c.key" :row="row" :value="row[c.key]">
                {{ row[c.key] }}
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="loading" class="loading">加载中…</div>
    <div v-else-if="!rows.length" class="empty">{{ emptyText || '无数据' }}</div>

    <div v-if="pageCount !== undefined" class="row" style="margin-top: 0.6rem">
      <span class="muted small">
        共 {{ total ?? rows.length }} 条 · 第 {{ page }} / {{ pageCount }} 页
      </span>
      <span class="spacer" />
      <button class="btn ghost" :disabled="!hasPrev" @click="emit('prev')">
        上一页
      </button>
      <button class="btn ghost" :disabled="!hasNext" @click="emit('next')">
        下一页
      </button>
    </div>
  </div>
</template>
