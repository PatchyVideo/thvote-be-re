<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ApiError } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import Modal from '@/components/Modal.vue'
import type { Column } from '@/components/types'
import {
  listWorks,
  createWork,
  updateWork,
  deleteWork,
  type WorkListResponse,
  type WorkRow,
} from '@/api/works'

const { toast } = useToast()

const TYPE_OPTIONS = [
  { label: '全部', value: '' },
  { label: '游戏旧作', value: 'old' },
  { label: '游戏新作', value: 'new' },
  { label: 'CD', value: 'CD' },
  { label: '书籍', value: 'book' },
  { label: '其他', value: 'others' },
] as const

const TYPE_LABELS: Record<string, string> = {
  old: '旧作',
  new: '新作',
  CD: 'CD',
  book: '书籍',
  others: '其他',
}

const cols: Column[] = [
  { key: 'workId', label: 'ID', width: '80px' },
  { key: 'name', label: '作品名' },
  { key: 'typeLabel', label: '类型', width: '110px' },
  { key: 'characterCount', label: '关联角色', width: '90px' },
  { key: 'musicCount', label: '关联音乐', width: '90px' },
  { key: 'actions', label: '操作', width: '120px' },
]

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.detail : (e as Error).message
}

const filters = reactive<{ q: string; type: string }>({ q: '', type: '' })
const { data, loading, run } = useAsync<WorkListResponse>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } =
  usePagination(50)

async function load(): Promise<void> {
  const r = await run(() =>
    listWorks({
      q: filters.q || undefined,
      type: filters.type || undefined,
      page: page.value,
      pageSize: size.value,
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

const works = computed<WorkRow[]>(() => data.value?.items ?? [])

// ── 新增 / 编辑 ───────────────────────────────────────────────────────────
const modalOpen = ref(false)
const editingId = ref<number | null>(null)
const formName = ref('')
const formType = ref('new')
const submitting = ref(false)

function openCreate(): void {
  editingId.value = null
  formName.value = ''
  formType.value = 'new'
  modalOpen.value = true
}
function openEdit(w: WorkRow): void {
  editingId.value = w.workId
  formName.value = w.name
  formType.value = w.type
  modalOpen.value = true
}
async function saveWork(): Promise<void> {
  const name = formName.value.trim()
  if (!name) {
    toast('作品名不能为空', 'error')
    return
  }
  submitting.value = true
  try {
    if (editingId.value) {
      await updateWork(editingId.value, { name, type: formType.value })
      toast('已更新', 'success')
    } else {
      await createWork({ name, type: formType.value })
      toast('已创建', 'success')
    }
    modalOpen.value = false
    load()
  } catch (e) {
    toast(errMsg(e), 'error')
  } finally {
    submitting.value = false
  }
}
async function confirmDelete(w: WorkRow): Promise<void> {
  const refs = w.characterCount + w.musicCount
  if (refs > 0) {
    toast(`无法删除：${w.name} 有 ${refs} 个关联的投票对象`, 'error')
    return
  }
  if (!confirm(`确定删除作品「${w.name}」吗？此操作不可恢复。`)) return
  try {
    await deleteWork(w.workId)
    toast('已删除', 'success')
    load()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}
</script>

<template>
  <div class="h1">作品管理</div>
  <FilterBar>
    <div>
      <label class="lbl">作品名</label>
      <input class="field" v-model="filters.q" @keyup.enter="search" />
    </div>
    <div>
      <label class="lbl">类型</label>
      <select class="field" v-model="filters.type" @change="search">
        <option v-for="o in TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
    </div>
    <template #actions>
      <button class="btn" @click="search">搜索</button>
      <button class="btn" @click="openCreate">新增作品</button>
    </template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="works"
    :loading="loading"
    empty-text="无作品"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-typeLabel="{ value }">
      <span class="badge">{{ TYPE_LABELS[value] ?? value ?? '—' }}</span>
    </template>
    <template #cell-actions="{ row }">
      <button class="icobtn" @click="openEdit(row)">编辑</button>
      <button class="icobtn danger" @click="confirmDelete(row)">删除</button>
    </template>
  </DataTable>

  <Modal v-if="modalOpen" :title="editingId ? '编辑作品' : '新增作品'" @close="modalOpen = false">
    <div style="margin-bottom: 0.7rem">
      <label class="lbl">作品名</label>
      <input class="field" style="width: 100%" v-model="formName" placeholder="如：东方红魔乡" />
    </div>
    <div style="margin-bottom: 0.7rem">
      <label class="lbl">类型</label>
      <select class="field" style="width: 100%" v-model="formType">
        <option value="old">游戏旧作</option>
        <option value="new">游戏新作</option>
        <option value="CD">CD</option>
        <option value="book">书籍</option>
        <option value="others">其他</option>
      </select>
    </div>
    <div class="row" style="margin-top: 1rem">
      <button class="btn" :disabled="submitting" @click="saveWork">
        {{ submitting ? '保存中…' : '保存' }}
      </button>
      <span class="spacer" />
      <button class="btn ghost" @click="modalOpen = false">取消</button>
    </div>
  </Modal>
</template>
