<script setup lang="ts">
// 问卷管理(B-049 Plan 2):4 层嵌套编辑器(问卷→题组→题→选项)。
// 嵌套树节点不带父级反向引用,创建子级时父 id 一律来自“打开弹窗时记录的编辑态”,
// 而不是节点对象本身。任何增删改后都整树重新拉取(questionnaireApi.get),不做本地补丁。
import { computed, onMounted, reactive, ref } from 'vue'
import Modal from '@/components/Modal.vue'
import { importQuestionnaireTree, questionnaireApi } from '@/api/questionnaire'
import { ApiError } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { useToast } from '@/composables/useToast'
import {
  QUESTION_TYPES,
  type GroupNode,
  type OptionNode,
  type QuestionNode,
  type QuestionType,
  type QuestionnaireListItem,
  type QuestionnaireTree,
} from '@/api/types'

const TYPE_LABELS: Record<QuestionType, string> = {
  Single: '单选',
  Multiple: '多选',
  Input: '输入',
}
function questionTypeLabel(t: QuestionType): string {
  return TYPE_LABELS[t] ?? t
}
function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.detail : (e as Error).message
}

const { toast } = useToast()

// ── list mode / editor mode 切换 ─────────────────────────────────────────
const currentId = ref<number | null>(null)

const { data: listData, loading: listLoading, run: runList } = useAsync<{
  items: QuestionnaireListItem[]
}>()
const { data: tree, loading: treeLoading, run: runTree } = useAsync<QuestionnaireTree>()

async function loadList(): Promise<void> {
  await runList(() => questionnaireApi.list())
}
async function loadTree(id: number): Promise<void> {
  await runTree(() => questionnaireApi.get(id))
}
onMounted(loadList)

async function openEditor(id: number): Promise<void> {
  currentId.value = id
  await loadTree(id)
}
async function backToList(): Promise<void> {
  currentId.value = null
  await loadList()
}

// 供“关联跳转/互斥选项”多选框使用:展平当前问卷树内的全部问题 / 全部选项。
const allQuestions = computed<QuestionNode[]>(() => {
  const t = tree.value
  if (!t) return []
  const out: QuestionNode[] = []
  for (const g of t.questionGroups) for (const q of g.questions) out.push(q)
  return out
})
const allOptions = computed<OptionNode[]>(() => {
  const out: OptionNode[] = []
  for (const q of allQuestions.value) for (const o of q.options) out.push(o)
  return out
})

// ── 问卷:新建(列表页) ────────────────────────────────────────────────────
interface QuestionnaireFormState {
  key: string
  title: string
  introduction: string
  category: 'main' | 'extra'
  required: boolean
  order: number
}
function blankQuestionnaireForm(): QuestionnaireFormState {
  return { key: '', title: '', introduction: '', category: 'main', required: false, order: 0 }
}

const createOpen = ref(false)
const createForm = reactive<QuestionnaireFormState>(blankQuestionnaireForm())

function openCreate(): void {
  Object.assign(createForm, blankQuestionnaireForm())
  createOpen.value = true
}
async function saveCreate(): Promise<void> {
  try {
    await questionnaireApi.create({
      key: createForm.key.trim(),
      title: createForm.title,
      introduction: createForm.introduction,
      category: createForm.category,
      required: createForm.required,
      order: createForm.order,
    })
    toast('已创建', 'success')
    createOpen.value = false
    await loadList()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

async function deleteQuestionnaire(item: QuestionnaireListItem): Promise<void> {
  if (!confirm(`删除问卷《${item.title}》？将级联删除其下所有题组/问题/选项。`)) return
  try {
    await questionnaireApi.remove(item.id)
    toast('已删除', 'success')
    await loadList()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// ── 问卷元信息(编辑器页) ─────────────────────────────────────────────────
const metaOpen = ref(false)
const metaForm = reactive<QuestionnaireFormState>(blankQuestionnaireForm())

function openMeta(): void {
  const t = tree.value
  if (!t) return
  metaForm.key = t.key
  metaForm.title = t.title
  metaForm.introduction = t.introduction
  metaForm.category = t.category
  metaForm.required = t.required
  metaForm.order = t.order
  metaOpen.value = true
}
async function saveMeta(): Promise<void> {
  if (currentId.value === null) return
  try {
    await questionnaireApi.update(currentId.value, {
      key: metaForm.key.trim(),
      title: metaForm.title,
      introduction: metaForm.introduction,
      category: metaForm.category,
      required: metaForm.required,
      order: metaForm.order,
    })
    toast('已保存', 'success')
    metaOpen.value = false
    await loadTree(currentId.value)
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// ── 整树导入 ───────────────────────────────────────────────────────────────
const importOpen = ref(false)
const importText = ref('')

function openImport(): void {
  importText.value = ''
  importOpen.value = true
}
async function runImport(): Promise<void> {
  let parsed: unknown
  try {
    parsed = JSON.parse(importText.value)
  } catch {
    toast('JSON 解析失败', 'error')
    return
  }
  if (!Array.isArray(parsed)) {
    toast('需要粘贴问卷数组 JSON', 'error')
    return
  }
  if (!confirm('导入会清空并替换现有全部问卷结构，确定？')) return
  try {
    const r = await importQuestionnaireTree(parsed)
    toast(`已导入 ${r.imported_questionnaires} 份问卷`, 'success')
    importOpen.value = false
    await loadList()
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// ── 题组 ─────────────────────────────────────────────────────────────────
interface GroupFormState {
  order: number
  hidden_by_default: boolean
}
function blankGroupForm(): GroupFormState {
  return { order: 0, hidden_by_default: false }
}

const groupOpen = ref(false)
const groupEditingId = ref<number | null>(null) // null = 新建
const groupForm = reactive<GroupFormState>(blankGroupForm())

function openCreateGroup(): void {
  groupEditingId.value = null
  Object.assign(groupForm, blankGroupForm())
  groupOpen.value = true
}
function openEditGroup(g: GroupNode): void {
  groupEditingId.value = g.id
  groupForm.order = g.order
  groupForm.hidden_by_default = g.hiddenByDefault
  groupOpen.value = true
}
async function saveGroup(): Promise<void> {
  if (currentId.value === null) return
  try {
    if (groupEditingId.value === null) {
      await questionnaireApi.createGroup({
        questionnaire_id: currentId.value,
        order: groupForm.order,
        hidden_by_default: groupForm.hidden_by_default,
      })
    } else {
      await questionnaireApi.updateGroup(groupEditingId.value, {
        order: groupForm.order,
        hidden_by_default: groupForm.hidden_by_default,
      })
    }
    toast('已保存', 'success')
    groupOpen.value = false
    await loadTree(currentId.value)
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}
async function deleteGroup(g: GroupNode): Promise<void> {
  if (currentId.value === null) return
  if (!confirm('删除此题组？将级联删除其下所有问题与选项。')) return
  try {
    await questionnaireApi.removeGroup(g.id)
    toast('已删除', 'success')
    await loadTree(currentId.value)
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// ── 问题 ─────────────────────────────────────────────────────────────────
interface QuestionFormState {
  type: QuestionType
  content: string
  introduction: string
  max_input_len: number
  order: number
}
function blankQuestionForm(): QuestionFormState {
  return { type: 'Single', content: '', introduction: '', max_input_len: 1000, order: 0 }
}

const questionOpen = ref(false)
const questionEditingId = ref<number | null>(null) // null = 新建
const questionGroupId = ref(0) // 新建/编辑时问题所属的题组 id(节点自身不带此引用)
const questionForm = reactive<QuestionFormState>(blankQuestionForm())

function openCreateQuestion(groupId: number): void {
  questionEditingId.value = null
  questionGroupId.value = groupId
  Object.assign(questionForm, blankQuestionForm())
  questionOpen.value = true
}
function openEditQuestion(q: QuestionNode, groupId: number): void {
  questionEditingId.value = q.id
  questionGroupId.value = groupId
  questionForm.type = q.type
  questionForm.content = q.content
  questionForm.introduction = q.introduction
  questionForm.max_input_len = q.maxInputLen
  questionForm.order = q.order
  questionOpen.value = true
}
async function saveQuestion(): Promise<void> {
  if (currentId.value === null) return
  try {
    if (questionEditingId.value === null) {
      await questionnaireApi.createQuestion({
        group_id: questionGroupId.value,
        type: questionForm.type,
        content: questionForm.content,
        introduction: questionForm.introduction,
        max_input_len: questionForm.max_input_len,
        order: questionForm.order,
      })
    } else {
      await questionnaireApi.updateQuestion(questionEditingId.value, {
        type: questionForm.type,
        content: questionForm.content,
        introduction: questionForm.introduction,
        max_input_len: questionForm.max_input_len,
        order: questionForm.order,
      })
    }
    toast('已保存', 'success')
    questionOpen.value = false
    await loadTree(currentId.value)
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}
async function deleteQuestion(q: QuestionNode): Promise<void> {
  if (currentId.value === null) return
  if (!confirm('删除此问题？将级联删除其下所有选项。')) return
  try {
    await questionnaireApi.removeQuestion(q.id)
    toast('已删除', 'success')
    await loadTree(currentId.value)
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// ── 选项 ─────────────────────────────────────────────────────────────────
interface OptionFormState {
  content: string
  option_group: number
  order: number
  related_question_ids: number[]
  mutex_option_ids: number[]
}
function blankOptionForm(): OptionFormState {
  return { content: '', option_group: 0, order: 0, related_question_ids: [], mutex_option_ids: [] }
}

const optionOpen = ref(false)
const optionEditingId = ref<number | null>(null) // null = 新建
const optionQuestionId = ref(0) // 新建/编辑时选项所属的问题 id(节点自身不带此引用)
const optionForm = reactive<OptionFormState>(blankOptionForm())

function openCreateOption(questionId: number): void {
  optionEditingId.value = null
  optionQuestionId.value = questionId
  Object.assign(optionForm, blankOptionForm())
  optionOpen.value = true
}
function openEditOption(o: OptionNode, questionId: number): void {
  optionEditingId.value = o.id
  optionQuestionId.value = questionId
  optionForm.content = o.content
  optionForm.option_group = o.optionGroup
  optionForm.order = o.order
  optionForm.related_question_ids = [...o.relatedQuestionIds]
  optionForm.mutex_option_ids = [...o.mutexOptionIds]
  optionOpen.value = true
}
async function saveOption(): Promise<void> {
  if (currentId.value === null) return
  try {
    if (optionEditingId.value === null) {
      await questionnaireApi.createOption({
        question_id: optionQuestionId.value,
        content: optionForm.content,
        related_question_ids: optionForm.related_question_ids,
        mutex_option_ids: optionForm.mutex_option_ids,
        option_group: optionForm.option_group,
        order: optionForm.order,
      })
    } else {
      await questionnaireApi.updateOption(optionEditingId.value, {
        content: optionForm.content,
        related_question_ids: optionForm.related_question_ids,
        mutex_option_ids: optionForm.mutex_option_ids,
        option_group: optionForm.option_group,
        order: optionForm.order,
      })
    }
    toast('已保存', 'success')
    optionOpen.value = false
    await loadTree(currentId.value)
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}
async function deleteOption(o: OptionNode): Promise<void> {
  if (currentId.value === null) return
  if (!confirm('删除此选项？')) return
  try {
    await questionnaireApi.removeOption(o.id)
    toast('已删除', 'success')
    await loadTree(currentId.value)
  } catch (e) {
    toast(errMsg(e), 'error')
  }
}

// 原生 <select multiple> 的 change 事件里选中项的 value 都是字符串,存盘前转 number。
function selectedNumbers(e: Event): number[] {
  const el = e.target as HTMLSelectElement
  return Array.from(el.selectedOptions).map((opt) => Number(opt.value))
}
function onRelatedChange(e: Event): void {
  optionForm.related_question_ids = selectedNumbers(e)
}
function onMutexChange(e: Event): void {
  optionForm.mutex_option_ids = selectedNumbers(e)
}
</script>

<template>
  <!-- ══════════ A. 列表模式 ══════════ -->
  <template v-if="currentId === null">
    <div class="row">
      <div class="h1" style="margin: 0">问卷管理</div>
      <span class="spacer"></span>
      <button class="btn ghost" @click="openImport">整树导入</button>
      <button class="btn" @click="openCreate">新建问卷</button>
    </div>

    <div v-if="listLoading && !listData" class="card loading">加载中…</div>
    <template v-else>
      <div v-if="!listData?.items.length" class="card muted">暂无问卷</div>
      <div v-for="item in listData?.items ?? []" :key="item.id" class="card">
        <div class="row">
          <b>{{ item.title || '（无标题）' }}</b>
          <span class="badge gray">{{ item.category === 'main' ? '主问卷' : '附加' }}</span>
          <span v-if="item.required" class="badge bad">必填</span>
          <span class="spacer"></span>
          <button class="icobtn" @click="openEditor(item.id)">编辑</button>
          <button class="icobtn danger" @click="deleteQuestionnaire(item)">删除</button>
        </div>
        <div class="small mono muted" style="margin-top: 0.2rem">{{ item.key }}</div>
        <div class="row small muted" style="margin-top: 0.4rem">
          <span>{{ item.group_count }} 题组</span>
          <span>{{ item.question_count }} 问题</span>
        </div>
      </div>
    </template>
  </template>

  <!-- ══════════ B. 编辑器模式 ══════════ -->
  <template v-else>
    <div class="row">
      <button class="btn ghost" @click="backToList">← 返回列表</button>
      <template v-if="tree">
        <b>{{ tree.title || '（无标题）' }}</b>
        <span class="small mono muted">{{ tree.key }}</span>
        <span class="badge gray">{{ tree.category === 'main' ? '主问卷' : '附加' }}</span>
        <span v-if="tree.required" class="badge bad">必填</span>
      </template>
      <span class="spacer"></span>
      <button class="btn ghost" @click="openMeta" :disabled="!tree">保存元信息</button>
    </div>

    <div v-if="treeLoading && !tree" class="card loading">加载中…</div>
    <template v-else-if="tree">
      <div class="card">
        <div class="row">
          <div class="h2" style="margin: 0">题组</div>
          <span class="spacer"></span>
          <button class="btn" @click="openCreateGroup">新增题组</button>
        </div>
        <div v-if="!tree.questionGroups.length" class="muted small">暂无题组</div>

        <div
          v-for="g in tree.questionGroups"
          :key="g.id"
          class="card"
          style="margin-left: 1rem; margin-top: 0.8rem"
        >
          <div class="row">
            <span class="mono">#{{ g.order }}</span>
            <span v-if="g.hiddenByDefault" class="badge gray">默认隐藏</span>
            <span class="small muted">{{ g.questions.length }} 题</span>
            <span class="spacer"></span>
            <button class="icobtn" @click="openEditGroup(g)">编辑题组</button>
            <button class="icobtn danger" @click="deleteGroup(g)">删除题组</button>
          </div>

          <div class="row" style="margin-top: 0.6rem">
            <span class="small muted">问题</span>
            <span class="spacer"></span>
            <button class="btn ghost" @click="openCreateQuestion(g.id)">新增题</button>
          </div>
          <div v-if="!g.questions.length" class="muted small">暂无问题</div>

          <div
            v-for="q in g.questions"
            :key="q.id"
            class="card"
            style="margin-left: 1rem; margin-top: 0.6rem"
          >
            <div class="row">
              <span class="mono">#{{ q.order }}</span>
              <span class="badge gray">{{ questionTypeLabel(q.type) }}</span>
              <span>{{ q.content || '（无题面）' }}</span>
              <span class="spacer"></span>
              <button class="icobtn" @click="openEditQuestion(q, g.id)">编辑题</button>
              <button class="icobtn danger" @click="deleteQuestion(q)">删除题</button>
            </div>
            <div v-if="q.introduction" class="small muted" style="margin-top: 0.2rem">
              {{ q.introduction }}
            </div>

            <div v-if="q.type === 'Input'" class="small muted" style="margin-top: 0.4rem">
              文本输入题 · 最大 {{ q.maxInputLen }} 字
            </div>

            <template v-else>
              <div class="row" style="margin-top: 0.6rem">
                <span class="small muted">选项</span>
                <span class="spacer"></span>
                <button class="btn ghost" @click="openCreateOption(q.id)">新增选项</button>
              </div>
              <div v-if="!q.options.length" class="muted small">暂无选项</div>

              <div
                v-for="o in q.options"
                :key="o.id"
                class="row"
                style="
                  margin-left: 1rem;
                  margin-top: 0.3rem;
                  padding: 0.3rem 0;
                  border-bottom: 1px solid var(--border);
                "
              >
                <span class="mono">#{{ o.order }}</span>
                <span>{{ o.content }}</span>
                <span class="small muted">分组 {{ o.optionGroup }}</span>
                <span v-if="o.relatedQuestionIds.length" class="small mono">
                  ↪{{ o.relatedQuestionIds.join(',') }}
                </span>
                <span v-if="o.mutexOptionIds.length" class="small mono">
                  ⊘{{ o.mutexOptionIds.join(',') }}
                </span>
                <span class="spacer"></span>
                <button class="icobtn" @click="openEditOption(o, q.id)">编辑选项</button>
                <button class="icobtn danger" @click="deleteOption(o)">删除选项</button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>
  </template>

  <!-- ══════════ 弹窗:新建问卷 ══════════ -->
  <Modal v-if="createOpen" title="新建问卷" @close="createOpen = false">
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">标识 key</label>
      <input class="field" style="width: 100%" v-model="createForm.key" placeholder="唯一英文标识,前端按此引用" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">标题</label>
      <input class="field" style="width: 100%" v-model="createForm.title" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">说明</label>
      <input class="field" style="width: 100%" v-model="createForm.introduction" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">分类</label>
      <select class="field" v-model="createForm.category">
        <option value="main">主问卷 (main)</option>
        <option value="extra">附加 (extra)</option>
      </select>
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl"><input type="checkbox" v-model="createForm.required" /> 必填(计入投票门禁)</label>
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">排序</label>
      <input class="field" type="number" v-model.number="createForm.order" />
    </div>
    <div class="row" style="margin-top: 0.8rem">
      <span class="spacer"></span>
      <button class="btn ghost" @click="createOpen = false">取消</button>
      <button class="btn" @click="saveCreate">创建</button>
    </div>
  </Modal>

  <!-- ══════════ 弹窗:问卷元信息 ══════════ -->
  <Modal v-if="metaOpen" title="问卷元信息" @close="metaOpen = false">
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">标识 key</label>
      <input class="field" style="width: 100%" v-model="metaForm.key" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">标题</label>
      <input class="field" style="width: 100%" v-model="metaForm.title" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">说明</label>
      <input class="field" style="width: 100%" v-model="metaForm.introduction" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">分类</label>
      <select class="field" v-model="metaForm.category">
        <option value="main">主问卷 (main)</option>
        <option value="extra">附加 (extra)</option>
      </select>
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl"><input type="checkbox" v-model="metaForm.required" /> 必填(计入投票门禁)</label>
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">排序</label>
      <input class="field" type="number" v-model.number="metaForm.order" />
    </div>
    <div class="row" style="margin-top: 0.8rem">
      <span class="spacer"></span>
      <button class="btn ghost" @click="metaOpen = false">取消</button>
      <button class="btn" @click="saveMeta">保存</button>
    </div>
  </Modal>

  <!-- ══════════ 弹窗:整树导入 ══════════ -->
  <Modal v-if="importOpen" title="整树导入 · 覆盖全部问卷" @close="importOpen = false">
    <div class="small muted" style="margin-bottom: 0.5rem">
      粘贴问卷数组 JSON(可省略 id,导入时自动分配)。⚠ 导入会清空并替换现有全部问卷结构。
    </div>
    <textarea
      class="field mono"
      style="width: 100%; min-height: 220px"
      v-model="importText"
      placeholder='[{"key": "...", "title": "...", "questionGroups": [...]}]'
    ></textarea>
    <div class="row" style="margin-top: 0.8rem">
      <span class="spacer"></span>
      <button class="btn ghost" @click="importOpen = false">取消</button>
      <button class="btn" @click="runImport">导入</button>
    </div>
  </Modal>

  <!-- ══════════ 弹窗:题组 ══════════ -->
  <Modal v-if="groupOpen" :title="groupEditingId === null ? '新建题组' : '编辑题组'" @close="groupOpen = false">
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">排序</label>
      <input class="field" type="number" v-model.number="groupForm.order" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">
        <input type="checkbox" v-model="groupForm.hidden_by_default" /> 默认隐藏
      </label>
      <div class="small muted">默认隐藏的题组,需被某选项的“关联跳转”触发后才出现</div>
    </div>
    <div class="row" style="margin-top: 0.8rem">
      <span class="spacer"></span>
      <button class="btn ghost" @click="groupOpen = false">取消</button>
      <button class="btn" @click="saveGroup">保存</button>
    </div>
  </Modal>

  <!-- ══════════ 弹窗:问题 ══════════ -->
  <Modal v-if="questionOpen" :title="questionEditingId === null ? '新建问题' : '编辑问题'" @close="questionOpen = false">
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">类型</label>
      <select class="field" v-model="questionForm.type">
        <option v-for="t in QUESTION_TYPES" :key="t" :value="t">{{ questionTypeLabel(t) }}</option>
      </select>
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">题面</label>
      <input class="field" style="width: 100%" v-model="questionForm.content" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">说明</label>
      <input class="field" style="width: 100%" v-model="questionForm.introduction" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">最大输入长度</label>
      <input class="field" type="number" v-model.number="questionForm.max_input_len" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">排序</label>
      <input class="field" type="number" v-model.number="questionForm.order" />
    </div>
    <div class="row" style="margin-top: 0.8rem">
      <span class="spacer"></span>
      <button class="btn ghost" @click="questionOpen = false">取消</button>
      <button class="btn" @click="saveQuestion">保存</button>
    </div>
  </Modal>

  <!-- ══════════ 弹窗:选项 ══════════ -->
  <Modal v-if="optionOpen" :title="optionEditingId === null ? '新建选项' : '编辑选项'" @close="optionOpen = false">
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">内容</label>
      <input class="field" style="width: 100%" v-model="optionForm.content" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">选中后展示的问题(关联跳转 related)</label>
      <select
        multiple
        class="field"
        style="width: 100%; min-height: 120px"
        @change="onRelatedChange"
      >
        <option
          v-for="q in allQuestions"
          :key="q.id"
          :value="q.id"
          :selected="optionForm.related_question_ids.includes(q.id)"
        >
          #{{ q.id }} {{ q.content || '（无题面）' }}
        </option>
      </select>
      <div class="small muted">勾选的问题仅在本选项被选中时才展示给用户</div>
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">互斥选项(mutex)</label>
      <select
        multiple
        class="field"
        style="width: 100%; min-height: 120px"
        @change="onMutexChange"
      >
        <option
          v-for="o in allOptions"
          :key="o.id"
          :value="o.id"
          :selected="optionForm.mutex_option_ids.includes(o.id)"
        >
          #{{ o.id }} {{ o.content }}
        </option>
      </select>
      <div class="small muted">选中本项时自动取消勾选的互斥项</div>
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">选项分组</label>
      <input class="field" type="number" v-model.number="optionForm.option_group" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">排序</label>
      <input class="field" type="number" v-model.number="optionForm.order" />
    </div>
    <div class="row" style="margin-top: 0.8rem">
      <span class="spacer"></span>
      <button class="btn ghost" @click="optionOpen = false">取消</button>
      <button class="btn" @click="saveOption">保存</button>
    </div>
  </Modal>
</template>
