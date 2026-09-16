<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { voteablesApi, type VoteableRow } from '@/api/voteables'
import { ApiError } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import Modal from '@/components/Modal.vue'
import type { Column } from '@/components/types'

const CATEGORIES: Array<{ value: string; label: string }> = [
  { value: 'character', label: '角色' },
  { value: 'music', label: '曲目' },
]

const cols: Column[] = [
  { key: 'id', label: 'ID', width: '70px' },
  { key: 'name', label: '名称' },
  { key: 'preview', label: '图片', width: '76px' },
  { key: 'workName', label: '出处/专辑' },
  { key: 'aliases', label: '别名', width: '70px' },
  { key: 'musicUrl', label: '试听', width: '130px' },
  { key: 'include', label: '收录', width: '120px' },
  { key: 'actions', label: '操作', width: '80px' },
]

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.detail : (e as Error).message
}

const filters = reactive<{ category: string; q: string }>({
  category: 'character',
  q: '',
})
const { data, loading, run } = useAsync<{ items: VoteableRow[]; total: number }>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } =
  usePagination(50)
const { toast } = useToast()

async function load(): Promise<void> {
  const r = await run(() =>
    voteablesApi.list({
      category: filters.category,
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

// ── 编辑弹窗 ──────────────────────────────────────────────────────────────
const editOpen = ref(false)
const editRow = ref<VoteableRow | null>(null)
const saving = ref(false)
const previewBroken = ref(false)
const form = reactive({
  image_url: '',
  music_url: '',
  aliases: '',
  include: '',
})

function openEdit(row: VoteableRow): void {
  editRow.value = row
  form.image_url = row.imageUrl ?? ''
  form.music_url = row.musicUrl ?? ''
  form.aliases = (row.aliases ?? []).join('\n')
  form.include = (row.include ?? []).join('\n')
  previewBroken.value = false
  editOpen.value = true
}

function splitLines(text: string): string[] {
  return text
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
}

async function save(): Promise<void> {
  if (!editRow.value) return
  saving.value = true
  try {
    const payload: Parameters<typeof voteablesApi.updateResources>[1] = {
      category: filters.category,
      image_url: form.image_url.trim(),
      aliases: splitLines(form.aliases),
    }
    if (filters.category === 'music') {
      payload.music_url = form.music_url.trim()
      payload.include = splitLines(form.include)
    }
    await voteablesApi.updateResources(editRow.value.id, payload)
    toast('已保存', 'success')
    editOpen.value = false
    load()
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) toast('URL 不合法（仅支持 http/https）', 'error')
    else if (e instanceof ApiError && e.status === 404) toast('投票对象不存在', 'error')
    else toast(errMsg(e), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="h1">投票对象资源</div>
  <FilterBar>
    <div>
      <label class="lbl">类别</label>
      <select class="field" v-model="filters.category" @change="search">
        <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
    </div>
    <div>
      <label class="lbl">名称搜索</label>
      <input class="field" v-model="filters.q" @keyup.enter="search" />
    </div>
    <template #actions>
      <button class="btn" @click="search">搜索</button>
    </template>
  </FilterBar>

  <DataTable
    :columns="cols"
    :rows="data?.items || []"
    :loading="loading"
    empty-text="无投票对象"
    :page="page"
    :page-count="pageCount"
    :total="total"
    :has-prev="hasPrev"
    :has-next="hasNext"
    @prev="goPrev"
    @next="goNext"
  >
    <template #cell-name="{ row }">
      {{ row.name }}
      <span v-if="row.nameJp && row.nameJp !== row.name" class="muted small">/ {{ row.nameJp }}</span>
    </template>
    <template #cell-preview="{ row }">
      <img
        v-if="row.imageUrl"
        :src="row.imageUrl"
        alt=""
        style="width: 48px; height: 48px; object-fit: contain"
      />
      <span v-else class="muted small">占位</span>
    </template>
    <template #cell-workName="{ value }">{{ value || '—' }}</template>
    <template #cell-aliases="{ row }">
      <span :title="(row.aliases || []).join(' / ')">
        {{ (row.aliases || []).length ? (row.aliases || []).length + ' 个' : '—' }}
      </span>
    </template>
    <template #cell-musicUrl="{ row }">
      <audio
        v-if="row.musicUrl"
        :src="row.musicUrl"
        controls
        preload="none"
        style="height: 28px; max-width: 120px"
      />
      <span v-else class="muted small">—</span>
    </template>
    <template #cell-include="{ row }">
      <span v-if="filters.category === 'character'" class="muted small">—</span>
      <span v-else :title="(row.include || []).join(' / ')">
        {{ (row.include || []).length || '—' }}
      </span>
    </template>
    <template #cell-actions="{ row }">
      <button class="icobtn" @click="openEdit(row)">编辑</button>
    </template>
  </DataTable>

  <Modal
    v-if="editOpen"
    :title="'编辑资源：' + (editRow?.name || '')"
    @close="editOpen = false"
  >
    <div style="margin-bottom: 0.7rem">
      <label class="lbl">图片 URL（{{ filters.category === 'character' ? '立绘' : '封面' }}）</label>
      <input class="field" style="width: 100%" v-model="form.image_url" @input="previewBroken = false" />
      <div v-if="form.image_url && !previewBroken" style="margin-top: 0.4rem">
        <img
          :src="form.image_url"
          alt="预览"
          style="max-height: 120px; max-width: 100%; object-fit: contain"
          @error="previewBroken = true"
        />
      </div>
      <div v-else-if="previewBroken" class="small muted">图片加载失败，请检查 URL</div>
    </div>

    <div v-if="filters.category === 'music'" style="margin-bottom: 0.7rem">
      <label class="lbl">试听 URL（mp3）</label>
      <input class="field" style="width: 100%" v-model="form.music_url" />
      <audio
        v-if="form.music_url"
        :src="form.music_url"
        controls
        preload="none"
        style="margin-top: 0.4rem; width: 100%; height: 32px"
      />
    </div>

    <div style="margin-bottom: 0.7rem">
      <label class="lbl">别名（每行一个，用于搜索）</label>
      <textarea class="field" style="width: 100%; min-height: 80px" v-model="form.aliases"></textarea>
    </div>

    <div v-if="filters.category === 'music'" style="margin-bottom: 0.7rem">
      <label class="lbl">收录专辑（每行一个）</label>
      <textarea class="field" style="width: 100%; min-height: 70px" v-model="form.include"></textarea>
    </div>

    <div class="row" style="margin-top: 1rem">
      <button class="btn" :disabled="saving" @click="save">
        {{ saving ? '保存中…' : '保存' }}
      </button>
      <span class="spacer" />
      <button class="btn ghost" @click="editOpen = false">取消</button>
    </div>
  </Modal>
</template>
