<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { adminApi } from '@/api/admin'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import type { UserAdminItem, UserListResponse } from '@/api/types'
import type { Column } from '@/components/types'

const cols: Column[] = [
  { key: 'id', label: 'ID' },
  { key: 'nickname', label: '昵称' },
  { key: 'email', label: '邮箱' },
  { key: 'phone', label: '手机' },
  { key: 'verified', label: '验证' },
  { key: 'register_date', label: '注册' },
  { key: 'status', label: '状态' },
  { key: 'actions', label: '操作', width: '96px' },
]

const filters = reactive({ email: '', phone: '' })
const { data, loading, run } = useAsync<UserListResponse>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } =
  usePagination(20)
const { toast } = useToast()

async function load(): Promise<void> {
  const r = await run(() =>
    adminApi.users({
      email: filters.email,
      phone: filters.phone,
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

async function toggleBan(u: UserAdminItem): Promise<void> {
  const action = u.removed ? '解封' : '封禁'
  if (!confirm(`确认${action}用户 ${u.id}？`)) return
  try {
    await (u.removed ? adminApi.unban(u.id) : adminApi.ban(u.id))
    toast(action + '成功', 'success')
    load()
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="h1">用户</div>
  <FilterBar>
    <div>
      <label class="lbl">邮箱</label>
      <input class="field" v-model="filters.email" @keyup.enter="search" />
    </div>
    <div>
      <label class="lbl">手机</label>
      <input class="field" v-model="filters.phone" @keyup.enter="search" />
    </div>
    <template #actions>
      <button class="btn" @click="search">搜索</button>
    </template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="无用户"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-nickname="{ value }">{{ value || '—' }}</template>
    <template #cell-email="{ value }">{{ value || '—' }}</template>
    <template #cell-phone="{ value }">{{ value || '—' }}</template>
    <template #cell-verified="{ row }">
      <span class="badge" :class="row.email_verified || row.phone_verified ? 'ok' : 'gray'">
        {{
          [row.email_verified ? '邮' : '', row.phone_verified ? '话' : '']
            .filter(Boolean)
            .join('/') || '未验证'
        }}
      </span>
    </template>
    <template #cell-register_date="{ value }">
      <span class="small mono">{{ value || '—' }}</span>
    </template>
    <template #cell-status="{ row }">
      <span class="badge" :class="row.removed ? 'bad' : 'ok'">
        {{ row.removed ? '已封' : '正常' }}
      </span>
    </template>
    <template #cell-actions="{ row }">
      <button class="icobtn" :class="{ danger: !row.removed }" @click="toggleBan(row)">
        {{ row.removed ? '解封' : '封禁' }}
      </button>
    </template>
  </DataTable>
</template>
