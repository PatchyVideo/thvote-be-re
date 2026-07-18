<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { candidatesApi } from '@/api/candidates'
import { ApiError } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import Modal from '@/components/Modal.vue'
import type {
  CandidateAdminItem,
  CandidateField,
  CandidateImportResult,
  MergeItem,
  Paged,
} from '@/api/types'
import type { Column } from '@/components/types'

const CATEGORIES: Array<{ value: string; label: string }> = [
  { value: 'character', label: '角色' },
  { value: 'music', label: '音乐' },
]

const cols: Column[] = [
  { key: 'id', label: 'ID', width: '70px' },
  { key: 'name', label: '名称' },
  { key: 'name_jp', label: '日文名' },
  { key: 'type', label: '类型' },
  { key: 'origin_album', label: '出处/专辑' },
  { key: 'first_appearance', label: '首次登场' },
  { key: 'actions', label: '操作', width: '110px' },
]

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.detail : (e as Error).message
}

// ── list ─────────────────────────────────────────────────────────────────

const filters = reactive<{ category: string; q: string; vote_year: number | undefined }>({
  category: 'character',
  q: '',
  vote_year: new Date().getFullYear(),
})
const { data, loading, run } = useAsync<Paged<CandidateAdminItem>>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } =
  usePagination(50)
const { toast } = useToast()

async function load(): Promise<void> {
  const r = await run(() =>
    candidatesApi.list({
      category: filters.category,
      vote_year: filters.vote_year || undefined,
      q: filters.q || undefined,
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

async function deleteRow(row: CandidateAdminItem): Promise<void> {
  if (!confirm('确认删除此候选项？')) return
  try {
    await candidatesApi.remove(row.id, filters.category)
    toast('已删除', 'success')
    load()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// ── edit modal (field-spec driven) ───────────────────────────────────────

const specCache = new Map<string, CandidateField[]>()

const editOpen = ref(false)
const editRow = ref<CandidateAdminItem | null>(null)
const editSpec = ref<CandidateField[]>([])
const editValues = reactive<Record<string, string>>({})

function fieldValue(row: CandidateAdminItem, name: string): string {
  const v = (row as unknown as Record<string, string | number | null | undefined>)[name]
  return v == null ? '' : String(v)
}

async function openEdit(row: CandidateAdminItem): Promise<void> {
  let spec = specCache.get(filters.category)
  if (!spec) {
    try {
      const r = await candidatesApi.fields(filters.category)
      spec = r.fields
      specCache.set(filters.category, spec)
    } catch (e) {
      toast(errMsg(e), 'error')
      return
    }
  }
  if (!spec) return
  editRow.value = row
  editSpec.value = spec
  for (const k of Object.keys(editValues)) delete editValues[k]
  for (const f of spec) editValues[f.name] = fieldValue(row, f.name)
  editOpen.value = true
}

async function saveEdit(): Promise<void> {
  if (!editRow.value) return
  const fields: Record<string, string> = {}
  for (const f of editSpec.value) fields[f.name] = editValues[f.name] ?? ''
  try {
    await candidatesApi.update(editRow.value.id, filters.category, fields)
    toast('已保存', 'success')
    editOpen.value = false
    load()
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) toast('该名称已存在', 'error')
    else if (e instanceof ApiError && e.status === 404) toast('候选不存在', 'error')
    else toast(errMsg(e), 'error')
  }
}

async function deleteFromEdit(): Promise<void> {
  if (!editRow.value) return
  if (!confirm('确认删除此候选项？')) return
  try {
    await candidatesApi.remove(editRow.value.id, filters.category)
    toast('已删除', 'success')
    editOpen.value = false
    load()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// ── import modal ─────────────────────────────────────────────────────────

const importOpen = ref(false)
const importFormat = ref<'auto' | 'csv' | 'json'>('auto')
const importContent = ref('')
const importBusy = ref(false)
const importResult = ref<CandidateImportResult | null>(null)

function openImport(): void {
  importFormat.value = 'auto'
  importContent.value = ''
  importResult.value = null
  importOpen.value = true
}

function importPayload(dryRun: boolean) {
  return {
    vote_year: filters.vote_year || 2026,
    category: filters.category,
    format: importFormat.value,
    content: importContent.value,
    dry_run: dryRun,
  }
}

async function previewImport(): Promise<void> {
  importBusy.value = true
  importResult.value = null
  try {
    importResult.value = await candidatesApi.import(importPayload(true))
  } catch (e) {
    toast(errMsg(e), 'error')
  } finally {
    importBusy.value = false
  }
}

async function commitImport(): Promise<void> {
  importBusy.value = true
  try {
    const r = await candidatesApi.import(importPayload(false))
    toast('成功导入 ' + r.imported + ' 条', 'success')
    importOpen.value = false
    load()
  } catch (e) {
    toast(errMsg(e), 'error')
  } finally {
    importBusy.value = false
  }
}

// ── merges modal ─────────────────────────────────────────────────────────

const mergesOpen = ref(false)
const mergesLoading = ref(false)
const mergesList = ref<MergeItem[]>([])
const mergeTargets = reactive<Record<number, string>>({})

async function loadMerges(): Promise<void> {
  mergesLoading.value = true
  try {
    const r = await candidatesApi.merges(filters.category, filters.vote_year || undefined)
    mergesList.value = r.items
  } catch (e) {
    toast(errMsg(e), 'error')
  } finally {
    mergesLoading.value = false
  }
}
function openMerges(): void {
  mergesOpen.value = true
  loadMerges()
}
async function unmerge(item: MergeItem): Promise<void> {
  if (!confirm('拆分此合并？')) return
  try {
    await candidatesApi.unmerge(item.id, filters.category)
    toast('已拆分', 'success')
    loadMerges()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}
async function mergeInto(item: MergeItem): Promise<void> {
  const targetId = Number(mergeTargets[item.id])
  if (!Number.isFinite(targetId) || targetId <= 0) {
    toast('请输入目标 ID', 'error')
    return
  }
  if (!confirm(`确认将 ${item.id} 合并到 ${targetId}？`)) return
  try {
    await candidatesApi.mergeInto(item.id, targetId, filters.category)
    toast('已合并', 'success')
    loadMerges()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}
</script>

<template>
  <div class="h1">候选管理</div>
  <FilterBar>
    <div>
      <label class="lbl">类别</label>
      <select class="field" v-model="filters.category" @change="search">
        <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
    </div>
    <div>
      <label class="lbl">年份</label>
      <input
        class="field"
        type="number"
        style="width: 90px"
        v-model.number="filters.vote_year"
        @keyup.enter="search"
      />
    </div>
    <div>
      <label class="lbl">名称搜索</label>
      <input class="field" v-model="filters.q" @keyup.enter="search" />
    </div>
    <template #actions>
      <button class="btn" @click="search">搜索</button>
      <button class="btn ghost" @click="openMerges">查看合并</button>
      <button class="btn ghost" @click="openImport">导入</button>
    </template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="无候选项"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-name_jp="{ value }">{{ value || '—' }}</template>
    <template #cell-type="{ value }">{{ value || '—' }}</template>
    <template #cell-origin_album="{ row }">{{ row.origin || row.album || '—' }}</template>
    <template #cell-first_appearance="{ value }">{{ value || '—' }}</template>
    <template #cell-actions="{ row }">
      <button class="icobtn" @click="openEdit(row)">编辑</button>
      <button class="icobtn danger" @click="deleteRow(row)">删除</button>
    </template>
  </DataTable>

  <Modal v-if="editOpen" :title="'编辑：' + (editRow?.name || '')" @close="editOpen = false">
    <div v-for="f in editSpec" :key="f.name" style="margin-bottom: 0.6rem">
      <label class="lbl">
        {{ f.name }}<span v-if="f.required" class="mono"> *</span>
      </label>
      <input class="field" style="width: 100%" v-model="editValues[f.name]" />
    </div>
    <div class="row" style="margin-top: 1rem">
      <button class="btn" @click="saveEdit">保存</button>
      <button class="btn danger" @click="deleteFromEdit">删除</button>
      <span class="spacer" />
      <button class="btn ghost" @click="editOpen = false">取消</button>
    </div>
  </Modal>

  <Modal v-if="importOpen" title="导入候选项" @close="importOpen = false">
    <div class="row">
      <select class="field" v-model="filters.category">
        <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
      <input class="field" type="number" style="width: 90px" v-model.number="filters.vote_year" />
      <select class="field" v-model="importFormat">
        <option value="auto">自动</option>
        <option value="csv">CSV</option>
        <option value="json">JSON</option>
      </select>
    </div>
    <div style="margin-top: 0.6rem">
      <textarea
        class="field"
        style="width: 100%; min-height: 120px"
        v-model="importContent"
        placeholder="粘贴 CSV / JSON 文本…"
      ></textarea>
    </div>
    <div class="row" style="margin-top: 0.6rem">
      <button class="btn ghost" :disabled="importBusy" @click="previewImport">预览</button>
      <button
        class="btn"
        :disabled="importBusy || !importResult || importResult.valid_count <= 0"
        @click="commitImport"
      >
        确认导入{{ importResult ? ' ' + importResult.valid_count + ' 条' : '' }}
      </button>
    </div>

    <div v-if="importResult" style="margin-top: 0.8rem">
      <div class="row">
        <span class="badge ok">有效 {{ importResult.valid_count }}</span>
        <span v-if="importResult.rejected.length" class="badge bad">
          错误 {{ importResult.rejected.length }}
        </span>
      </div>
      <div v-if="importResult.rejected.length" class="small muted" style="margin-top: 0.4rem">
        <div v-for="(r, i) in importResult.rejected" :key="i">第{{ r.line }}行：{{ r.reason }}</div>
      </div>
      <table v-if="importResult.valid.length" class="tbl" style="margin-top: 0.6rem">
        <thead>
          <tr>
            <th>名称</th>
            <th>日文名</th>
            <th>类型</th>
            <th>出处/专辑</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, i) in importResult.valid.slice(0, 5)" :key="i">
            <td>{{ item.name || '—' }}</td>
            <td>{{ item.name_jp || '—' }}</td>
            <td>{{ item.type || '—' }}</td>
            <td>{{ item.origin || item.album || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </Modal>

  <Modal v-if="mergesOpen" title="合并关系" @close="mergesOpen = false">
    <div class="muted small" style="margin-bottom: 0.6rem">被合并 → 主候选 id</div>
    <div v-if="mergesLoading" class="loading">加载中…</div>
    <table v-else class="tbl">
      <thead>
        <tr>
          <th>id</th>
          <th>名称</th>
          <th>合并到</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in mergesList" :key="m.id">
          <td class="mono">{{ m.id }}</td>
          <td>{{ m.name }}</td>
          <td class="mono">→ {{ m.merged_into }}</td>
          <td>
            <div class="row" style="gap: 0.3rem; flex-wrap: nowrap">
              <button class="icobtn" @click="unmerge(m)">拆分</button>
              <input
                class="field"
                style="width: 70px"
                placeholder="目标ID"
                v-model="mergeTargets[m.id]"
              />
              <button class="icobtn" @click="mergeInto(m)">合并到</button>
            </div>
          </td>
        </tr>
        <tr v-if="!mergesList.length">
          <td colspan="4" class="muted" style="text-align: center">无合并</td>
        </tr>
      </tbody>
    </table>
  </Modal>
</template>
