<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { monitorApi } from '@/api/monitor'
import { useAsync } from '@/composables/useAsync'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import Modal from '@/components/Modal.vue'
import type { GroupsResponse } from '@/api/types'
import type { Column } from '@/components/types'

const kind = ref<'ip' | 'device'>('ip')
const minSize = ref(2)
const { data, loading, run } = useAsync<GroupsResponse>()

const cols: Column[] = [
  { key: 'key', label: 'IP / 设备' },
  { key: 'voter_count', label: '账号数', width: '110px' },
  { key: 'actions', label: '', width: '110px' },
]

function load(): void {
  run(() => monitorApi.groups(kind.value, minSize.value, 200))
}
onMounted(load)

const membersOpen = ref(false)
const membersKey = ref('')
const membersList = ref<string[]>([])
const membersLoading = ref(false)

async function showMembers(key: string): Promise<void> {
  membersKey.value = key
  membersOpen.value = true
  membersLoading.value = true
  membersList.value = []
  try {
    membersList.value = await monitorApi.members(kind.value, key)
  } catch {
    membersList.value = []
  } finally {
    membersLoading.value = false
  }
}
</script>

<template>
  <div class="h1">IP · 设备聚类</div>
  <FilterBar>
    <div>
      <label class="lbl">维度</label>
      <select class="field" v-model="kind">
        <option value="ip">IP</option>
        <option value="device">设备</option>
      </select>
    </div>
    <div>
      <label class="lbl">最小账号数</label>
      <input
        class="field"
        type="number"
        min="1"
        style="width: 90px"
        v-model.number="minSize"
      />
    </div>
    <template #actions><button class="btn" @click="load">查询</button></template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="无达到阈值的分组"
  >
    <template #cell-key="{ value }"><span class="mono">{{ value }}</span></template>
    <template #cell-actions="{ row }">
      <button class="icobtn" @click="showMembers(row.key)">查看成员</button>
    </template>
  </DataTable>

  <Modal
    v-if="membersOpen"
    :title="'组成员 · ' + membersKey"
    @close="membersOpen = false"
  >
    <div v-if="membersLoading" class="loading">加载中…</div>
    <div v-else>
      <div class="muted small" style="margin-bottom: 0.5rem">
        {{ membersList.length }} 个账号 · 点击进入钻取
      </div>
      <div class="row" style="gap: 0.4rem">
        <RouterLink
          v-for="id in membersList"
          :key="id"
          class="badge gray mono"
          :to="'/monitor/account/' + id"
          @click="membersOpen = false"
        >
          {{ id }}
        </RouterLink>
      </div>
    </div>
  </Modal>
</template>
