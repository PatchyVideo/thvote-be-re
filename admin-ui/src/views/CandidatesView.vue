<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { adminApi } from '@/api/admin'
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
  Paged,
} from '@/api/types'
import type { Column } from '@/components/types'

const CATEGORIES: Array<{ value: string; label: string }> = [
  { value: 'character', label: '角色' },
  { value: 'music', label: '音乐' },
]

const cols: Column[] = [
  { key: 'id', label: '候选 ID', width: '90px' },
  { key: 'voteable_id', label: '对象 ID', width: '90px' },
  { key: 'sort_order', label: '排序', width: '70px' },
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
  vote_year: undefined,
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
onMounted(async () => {
  try {
    filters.vote_year = (await adminApi.stats()).vote_year
    await load()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
})

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
    if (e instanceof ApiError && e.status === 409) toast('该投票对象已加入本届候选', 'error')
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
const importTarget = reactive({ category: 'character', vote_year: 0 })
const importBusy = ref(false)
const importResult = ref<CandidateImportResult | null>(null)
const actionLabels: Record<string, string> = { create: '新增', update: '更新', unchanged: '不变' }
const fieldLabels: Record<string, string> = { voteable_id: '投票对象 ID', sort_order: '排序（留空清除）' }
const readyToImport = computed(() => !!importResult.value?.valid_count &&
  !importResult.value?.rejected.length && !importBusy.value)

watch([importContent, importFormat, () => importTarget.category, () => importTarget.vote_year], () => {
  importResult.value = null
}, { flush: 'sync' })

function openImport(): void {
  importFormat.value = 'auto'
  importContent.value = ''
  importResult.value = null
  importTarget.category = filters.category
  importTarget.vote_year = filters.vote_year || 0
  importOpen.value = true
}

async function readImportFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importBusy.value = true
  importResult.value = null
  try {
    importContent.value = await file.text()
  } catch {
    toast('文件读取失败，请重新选择', 'error')
  } finally {
    input.value = ''
    importBusy.value = false
  }
}

function useExample(): void {
  importContent.value = importFormat.value === 'csv'
    ? 'voteable_id,sort_order\n1,1\n2,2\n'
    : JSON.stringify([{ voteable_id: 1, sort_order: 1 }, { voteable_id: 2, sort_order: 2 }], null, 2)
}

function importPayload(dryRun: boolean) {
  return {
    ...importTarget,
    format: importFormat.value,
    content: importContent.value,
    dry_run: dryRun,
  }
}

async function previewImport(): Promise<void> {
  if (!Number.isInteger(importTarget.vote_year) || importTarget.vote_year <= 0) {
    toast('请输入有效届次', 'error')
    return
  }
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
  if (!readyToImport.value) return
  importBusy.value = true
  try {
    const r = await candidatesApi.import(importPayload(false))
    importResult.value = r
    if (!r.applied) {
      toast('未导入，请检查预览中的错误', 'error')
      return
    }
    toast(`已导入：新增 ${r.create_count}，更新 ${r.update_count}，不变 ${r.unchanged_count}`, 'success')
    importOpen.value = false
    filters.category = importTarget.category
    filters.vote_year = importTarget.vote_year
    search()
  } catch (e) {
    toast(errMsg(e), 'error')
  } finally {
    importBusy.value = false
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
      <label class="lbl">届次</label>
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
    <template #cell-sort_order="{ value }">{{ value ?? '—' }}</template>
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
        {{ fieldLabels[f.name] || f.name }}<span v-if="f.required" class="mono"> *</span>
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

  <Modal v-if="importOpen" title="导入本届候选" @close="!importBusy && (importOpen = false)">
    <p class="small muted">把已有角色或音乐加入指定届次。角色名称、作品和资源请在投票对象页面维护。</p>
    <fieldset :disabled="importBusy" style="border: 0; padding: 0">
      <div class="row">
        <div><label class="lbl">类别</label><select class="field" v-model="importTarget.category">
          <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
        </select></div>
        <div><label class="lbl">届次</label><input class="field" type="number" min="1" style="width: 90px" v-model.number="importTarget.vote_year" /></div>
        <div><label class="lbl">格式</label><select class="field" v-model="importFormat">
          <option value="auto">自动识别</option><option value="csv">CSV</option><option value="json">JSON</option>
        </select></div>
      </div>
      <p class="small muted">voteable_id 为投票对象 ID，必填；sort_order 为排序，可省略，已有候选会保留原排序。示例 ID 仅说明格式，请换成实际对象 ID。</p>
      <div class="row" style="margin: 0.6rem 0">
        <input type="file" accept=".json,.csv,application/json,text/csv" aria-label="选择候选文件" @change="readImportFile" />
        <button class="btn ghost" @click="useExample">填入示例</button>
      </div>
      <textarea class="field" style="width: 100%; min-height: 150px" v-model="importContent" placeholder="粘贴 CSV / JSON 文本"></textarea>
    </fieldset>
    <div class="row" style="margin-top: 0.6rem">
      <button class="btn ghost" :disabled="importBusy || !importContent.trim()" @click="previewImport">预览</button>
      <button class="btn" :disabled="!readyToImport" @click="commitImport">确认导入</button>
      <button class="btn ghost" :disabled="importBusy" @click="importOpen = false">取消</button>
    </div>
    <div v-if="importResult" style="margin-top: 0.8rem">
      <div class="row">
        <span class="badge ok">新增 {{ importResult.create_count }}</span>
        <span class="badge gray">更新 {{ importResult.update_count }}</span>
        <span class="badge gray">不变 {{ importResult.unchanged_count }}</span>
        <span v-if="importResult.rejected.length" class="badge bad">错误 {{ importResult.rejected.length }}</span>
      </div>
      <div v-if="importResult.rejected.length" class="small" style="margin-top: 0.6rem">
        <p>存在错误，整批未导入。修正后请重新预览。</p>
        <div v-for="(r, i) in importResult.rejected" :key="i">第 {{ r.line }} 行：{{ r.reason }}</div>
      </div>
      <div style="overflow: auto; max-height: 350px">
        <table v-if="importResult.valid.length" class="tbl" style="margin-top: 0.6rem">
          <thead><tr><th>行</th><th>对象 ID</th><th>名称</th><th>作品</th><th>排序</th><th>操作</th></tr></thead>
          <tbody><tr v-for="item in importResult.valid" :key="item.line">
            <td>{{ item.line }}</td><td>{{ item.voteable_id }}</td><td>{{ item.name }}</td>
            <td>{{ item.work_name || '—' }}</td><td>{{ item.sort_order ?? '—' }}</td><td>{{ actionLabels[item.action] }}</td>
          </tr></tbody>
        </table>
      </div>
    </div>
  </Modal>
</template>
