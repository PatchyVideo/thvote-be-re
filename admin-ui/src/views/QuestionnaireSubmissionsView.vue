<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { adminApi } from '@/api/admin'
import { questionnaireSubmissionsApi, type SubmissionSummary, type SubmissionDetail,
  type SubmissionsPage } from '@/api/questionnaireSubmissions'
import DataTable from '@/components/DataTable.vue'
import FilterBar from '@/components/FilterBar.vue'
import Modal from '@/components/Modal.vue'
import type { Column } from '@/components/types'
import { useAsync } from '@/composables/useAsync'
import { usePagination } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const filters = reactive({
  vote_year: undefined as number | undefined,
  vote_id: typeof route.query.vote_id === 'string' ? route.query.vote_id : '',
  invalidated: '',
})
const { data, loading, error, run } = useAsync<SubmissionsPage>()
const { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset } = usePagination(30)
const { toast } = useToast()
const columns: Column[] = [
  { key: 'vote_id', label: '账号' },
  { key: 'attempt', label: '最新批次' },
  { key: 'created_at', label: '提交时间' },
  { key: 'progress', label: '问卷填写情况' },
  { key: 'invalidated', label: '答卷状态' },
  { key: 'eligible', label: '问卷投票条件' },
  { key: 'actions', label: '操作' },
]

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}
function batchLabel(attempt: number): string {
  return attempt === 0 ? '旧存量批次' : `第 ${attempt} 次提交`
}
async function load(): Promise<void> {
  const result = await run(() => questionnaireSubmissionsApi.list({
    vote_year: filters.vote_year,
    vote_id: filters.vote_id.trim() || undefined,
    invalidated: filters.invalidated === '' ? undefined : filters.invalidated === 'true',
    page: page.value, page_size: size.value,
  }))
  if (result) setTotal(result.total)
}
function search(): void { reset(); load() }
function goPrev(): void { prev(); load() }
function goNext(): void { next(); load() }
onMounted(async () => {
  try {
    filters.vote_year = (await adminApi.stats()).vote_year
    await load()
  } catch (e) { toast((e as Error).message, 'error') }
})
watch(() => route.query.vote_id, value => {
  filters.vote_id = typeof value === 'string' ? value : ''
  search()
})

const detailOpen = ref(false)
const detailBusy = ref(false)
const actionBusy = ref(false)
const detail = ref<SubmissionDetail | null>(null)
const attempt = ref(0)
const batch = computed(() => detail.value?.batches.find(item => item.attempt === attempt.value))

async function openDetail(row: SubmissionSummary): Promise<void> {
  detailOpen.value = true
  detailBusy.value = true
  detail.value = null
  try {
    detail.value = await questionnaireSubmissionsApi.detail(row.vote_year, row.vote_id)
    attempt.value = detail.value.batches[0]?.attempt ?? 0
  } catch (e) {
    toast((e as Error).message, 'error')
    detailOpen.value = false
  } finally { detailBusy.value = false }
}

async function toggleInvalidated(): Promise<void> {
  const selected = batch.value
  if (!selected || actionBusy.value) return
  const action = selected.invalidated ? '恢复' : '作废'
  const consequence = selected.is_latest
    ? (selected.invalidated ? '恢复后会重新判断问卷投票条件。' : '作废后将不满足问卷投票条件，不会回退到旧提交。')
    : '这是历史批次，操作不会替代当前提交。'
  if (!confirm(`确认${action}${batchLabel(selected.attempt)}？${consequence}已有统计需重新计票更新。`)) return
  actionBusy.value = true
  try {
    const result = await questionnaireSubmissionsApi.setInvalidated(
      selected.vote_year, selected.vote_id, selected.attempt, !selected.invalidated,
    )
    toast(result.detail, 'success')
    detail.value = await questionnaireSubmissionsApi.detail(selected.vote_year, selected.vote_id)
    await load()
  } catch (e) { toast((e as Error).message, 'error') }
  finally { actionBusy.value = false }
}
</script>

<template>
  <h1 class="h1">答卷管理</h1>
  <p class="small muted">按账号查看本届最新答卷，可在详情中查看历史提交。填写完成情况与答卷有效性分别展示。</p>
  <FilterBar>
    <div><label class="lbl">届次</label><input class="field" type="number" min="1" v-model.number="filters.vote_year" @keyup.enter="search" style="width: 90px" /></div>
    <div><label class="lbl">账号 ID</label><input class="field" v-model="filters.vote_id" @keyup.enter="search" placeholder="完整账号 ID" /></div>
    <div><label class="lbl">答卷状态</label><select class="field" v-model="filters.invalidated" @change="search">
      <option value="">全部</option><option value="false">有效</option><option value="true">已作废</option>
    </select></div>
    <template #actions><button class="btn" :disabled="loading" @click="search">查询</button></template>
  </FilterBar>
  <p v-if="error" class="err">{{ error }}</p>
  <DataTable :columns="columns" :rows="data?.items || []" :loading="loading"
    empty-text="本届暂无符合条件的答卷" :page="page" :page-count="pageCount" :total="total"
    :has-prev="hasPrev" :has-next="hasNext" @prev="goPrev" @next="goNext">
    <template #cell-vote_id="{ value }"><RouterLink :to="'/monitor/account/' + encodeURIComponent(value)">{{ value }}</RouterLink></template>
    <template #cell-attempt="{ value }">{{ batchLabel(value) }}</template>
    <template #cell-created_at="{ value }">{{ formatTime(value) }}</template>
    <template #cell-progress="{ row }"><div class="progress-list">
      <span v-for="qn in row.progress" :key="qn.id" class="badge" :class="qn.completed ? 'ok' : 'gray'">
        {{ qn.title || qn.key }}：{{ qn.completed ? '已完成' : '未完成' }}
      </span><span v-if="!row.progress.length" class="muted small">当前未配置问卷</span>
    </div></template>
    <template #cell-invalidated="{ value }"><span class="badge" :class="value ? 'bad' : 'ok'">{{ value ? '已作废' : '有效' }}</span></template>
    <template #cell-eligible="{ value }">{{ value ? '已满足' : '未满足' }}</template>
    <template #cell-actions="{ row }"><button class="icobtn" @click="openDetail(row)">查看答卷</button></template>
  </DataTable>

  <Modal v-if="detailOpen" title="答卷详情" @close="!actionBusy && (detailOpen = false)">
    <div v-if="detailBusy" class="loading">正在读取答卷…</div>
    <template v-else-if="detail">
      <div class="row"><span class="small">账号 {{ detail.vote_id }}</span><span class="badge gray">第 {{ detail.vote_year }} 届</span></div>
      <label class="lbl" style="margin-top: 1rem">提交批次</label>
      <select class="field" style="width: 100%" v-model.number="attempt" :disabled="actionBusy">
        <option v-for="item in detail.batches" :key="item.attempt" :value="item.attempt">
          {{ batchLabel(item.attempt) }} {{ item.is_latest ? '（最新）' : '' }} {{ formatTime(item.created_at) }} {{ item.invalidated ? '已作废' : '有效' }}
        </option>
      </select>
      <template v-if="batch">
        <div class="row" style="margin: 0.8rem 0">
          <span class="badge" :class="batch.invalidated ? 'bad' : 'ok'">{{ batch.invalidated ? '已作废' : '有效' }}</span>
          <span class="small">填写情况：{{ batch.completed ? '已满足问卷完成要求' : '尚未完成' }}</span>
          <span class="small">{{ batch.is_latest ? (batch.eligible ? '当前满足问卷投票条件' : '当前未满足问卷投票条件') : '历史批次，不作为当前投票资格' }}</span>
        </div>
        <div class="progress-list"><span v-for="qn in batch.progress" :key="qn.id" class="badge" :class="qn.completed ? 'ok' : 'gray'">{{ qn.title || qn.key }}：{{ qn.completed ? '已完成' : '未完成' }}</span></div>
        <p class="small muted">题目和选项按当前题库解析。定义不存在或归属变化时保留原 ID 与输入内容。</p>
        <section v-for="qn in batch.questionnaires" :key="qn.id" class="answer-questionnaire">
          <h2 class="h2">{{ qn.title ?? `问卷定义已不存在（ID ${qn.id}）` }}</h2>
          <div v-for="answer in qn.answers" :key="answer.id" class="answer-row">
            <div class="small muted">题组 {{ answer.group_id }}，题目 {{ answer.active_question_id ?? '未选择' }}</div>
            <p class="question-text">{{ answer.question_content ?? '无法解析题目' }}</p>
            <ul v-if="answer.selected_options.length" class="answer-options">
              <li v-for="option in answer.selected_options" :key="option.id">{{ option.content ?? '无法解析选项' }} <span class="small muted">（ID {{ option.id }}）</span></li>
            </ul>
            <p v-if="answer.input_text" class="input-text">{{ answer.input_text }}</p>
            <p v-if="!answer.input_text && !answer.selected_options.length" class="small muted">未填写答案</p>
            <p v-for="message in answer.missing_references" :key="message" class="small missing-reference">{{ message }}</p>
          </div>
        </section>
        <p class="small muted">作废和恢复针对整次提交，不影响账号封禁状态或其他类别已提交的票。已有统计及筛选缓存需重新计票更新。</p>
        <div class="row">
          <button class="btn" :class="{ danger: !batch.invalidated }" :disabled="actionBusy" @click="toggleInvalidated">{{ actionBusy ? '正在保存…' : (batch.invalidated ? '恢复本次答卷' : '作废本次答卷') }}</button>
          <span class="spacer" /><button class="btn ghost" :disabled="actionBusy" @click="detailOpen = false">关闭</button>
        </div>
      </template>
    </template>
  </Modal>
</template>

<style scoped>
.progress-list { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.answer-questionnaire { margin-top: 1.3rem; }
.answer-row { border-top: 1px solid var(--border); padding: 0.8rem 0; }
.question-text { margin: 0.4rem 0; white-space: pre-wrap; overflow-wrap: anywhere; font-weight: 600; }
.answer-options { margin: 0.4rem 0; padding-left: 1.3rem; }
.input-text { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0.5rem 0; }
.missing-reference { color: var(--warn); margin: 0.3rem 0; }
</style>
