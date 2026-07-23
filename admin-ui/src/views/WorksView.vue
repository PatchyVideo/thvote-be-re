<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import Modal from '@/components/Modal.vue'
import { listWorks, createWork, updateWork, deleteWork, type WorkRow } from '@/api/works'

const toast = useToast()

// ── filters ──
const search = ref('')
const typeFilter = ref('')
const typeOptions = [
  { label: '全部', value: '' },
  { label: '游戏旧作', value: 'old' },
  { label: '游戏新作', value: 'new' },
  { label: 'CD', value: 'CD' },
  { label: '书籍', value: 'book' },
  { label: '其他', value: 'others' },
]

// ── data ──
const { page, pageSize, resetPage } = usePagination()
const { execute, loading, error, data } = useAsync(async () => {
  return listWorks({ q: search.value || undefined, type: typeFilter.value || undefined, page: page.value, pageSize: pageSize.value })
}, { immediate: true })

watch([search, typeFilter], () => { resetPage(); execute() })
watch([page, pageSize], () => { execute() })

const works = computed<WorkRow[]>(() => data.value?.items ?? [])
const total = computed(() => data.value?.total ?? 0)

// ── modal ──
const modalOpen = ref(false)
const editingId = ref<number | null>(null)
const formName = ref('')
const formType = ref('new')
const formSubmitting = ref(false)

function openCreate() {
  editingId.value = null
  formName.value = ''
  formType.value = 'new'
  modalOpen.value = true
}

function openEdit(w: WorkRow) {
  editingId.value = w.workId
  formName.value = w.name
  formType.value = w.type
  modalOpen.value = true
}

async function saveWork() {
  const name = formName.value.trim()
  if (!name) { toast.error('作品名不能为空'); return }
  formSubmitting.value = true
  try {
    if (editingId.value) {
      await updateWork(editingId.value, { name, type: formType.value })
      toast.success('已更新')
    } else {
      await createWork({ name, type: formType.value })
      toast.success('已创建')
    }
    modalOpen.value = false
    execute()
  } catch (e: any) {
    toast.error(e?.detail ?? String(e))
  } finally {
    formSubmitting.value = false
  }
}

async function confirmDelete(w: WorkRow) {
  const refs = w.characterCount + w.musicCount
  if (refs > 0) {
    toast.error(`无法删除: ${w.name} 有 ${refs} 个关联的投票对象`)
    return
  }
  if (!confirm(`确定删除作品「${w.name}」吗？此操作不可恢复。`)) return
  try {
    await deleteWork(w.workId)
    toast.success('已删除')
    execute()
  } catch (e: any) {
    toast.error(e?.detail ?? String(e))
  }
}

// ── columns ──
const columns = [
  { key: 'workId', label: 'ID', width: '80px' },
  { key: 'name', label: '作品名' },
  { key: 'typeTag', label: '类型' },
  { key: 'characterCount', label: '关联角色', width: '90px' },
  { key: 'musicCount', label: '关联音乐', width: '90px' },
  { key: 'actions', label: '操作', width: '120px' },
]

const typeLabels: Record<string, string> = { old: '旧作', new: '新作', CD: 'CD', book: '书籍', others: '其他' }

function rowMapper(w: WorkRow) {
  return {
    ...w,
    typeTag: typeLabels[w.type] ?? w.type,
  }
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">作品管理</h1>
    <FilterBar>
      <input
        v-model="search"
        type="text"
        placeholder="搜索作品名..."
        class="px-3 py-1.5 border rounded text-sm"
      />
      <select v-model="typeFilter" class="px-3 py-1.5 border rounded text-sm">
        <option v-for="o in typeOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <button class="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700" @click="openCreate">
        新增作品
      </button>
    </FilterBar>

    <DataTable
      :columns="columns"
      :rows="works.map(rowMapper)"
      :loading="loading"
      :error="error"
      :page="page"
      :page-size="pageSize"
      :total="total"
      @update:page="(p: number) => page = p"
      @update:page-size="(ps: number) => pageSize = ps"
    >
      <template #cell-typeTag="{ value }">
        <span class="px-1.5 py-0.5 rounded text-xs" :class="{
          'bg-amber-100 text-amber-800': value === '旧作',
          'bg-green-100 text-green-800': value === '新作',
          'bg-blue-100 text-blue-800': value === 'CD',
          'bg-purple-100 text-purple-800': value === '书籍',
          'bg-gray-100 text-gray-600': value === '其他',
        }">{{ value }}</span>
      </template>
      <template #cell-actions="{ row }">
        <button class="text-blue-600 hover:text-blue-800 text-sm mr-2" @click="openEdit(row)">编辑</button>
        <button class="text-red-600 hover:text-red-800 text-sm" @click="confirmDelete(row)">删除</button>
      </template>
    </DataTable>

    <Modal v-if="modalOpen" @close="modalOpen = false">
      <h2 class="text-lg font-medium mb-4">{{ editingId ? '编辑作品' : '新增作品' }}</h2>
      <div class="space-y-3">
        <div>
          <label class="block text-sm text-gray-600 mb-1">作品名</label>
          <input v-model="formName" class="w-full px-3 py-1.5 border rounded text-sm" placeholder="如：东方红魔乡" />
        </div>
        <div>
          <label class="block text-sm text-gray-600 mb-1">类型</label>
          <select v-model="formType" class="w-full px-3 py-1.5 border rounded text-sm">
            <option value="old">游戏旧作</option>
            <option value="new">游戏新作</option>
            <option value="CD">CD</option>
            <option value="book">书籍</option>
            <option value="others">其他</option>
          </select>
        </div>
        <div class="flex justify-end space-x-2 pt-2">
          <button class="px-3 py-1.5 border rounded text-sm" @click="modalOpen = false">取消</button>
          <button
            class="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            :disabled="formSubmitting"
            @click="saveWork"
          >
            {{ formSubmitting ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </Modal>
  </div>
</template>
