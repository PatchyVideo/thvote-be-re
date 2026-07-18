import { apiGet, apiSend } from './client'
import type { QuestionnaireListItem, QuestionnaireTree } from './types'

// 整树导入(POST /admin/questionnaire/import):全量替换所有问卷结构,非增量。
export function importQuestionnaireTree(questionnaires: unknown[]) {
  return apiSend<{ ok: boolean; imported_questionnaires: number }>(
    '/admin/questionnaire/import',
    'POST',
    { questionnaires },
  )
}

type Body = Record<string, unknown>
type Created = { ok: boolean; id: number }
type Ok = { ok: boolean }

// 4 层嵌套 CRUD(问卷→题组→题→选项)。create body 带父 id;update body 不带父 id。
export const questionnaireApi = {
  list: () => apiGet<{ items: QuestionnaireListItem[] }>('/admin/questionnaires'),
  get: (id: number) => apiGet<QuestionnaireTree>(`/admin/questionnaires/${id}`),

  create: (body: Body) => apiSend<Created>('/admin/questionnaires', 'POST', body),
  update: (id: number, body: Body) =>
    apiSend<Ok>(`/admin/questionnaires/${id}`, 'PUT', body),
  remove: (id: number) => apiSend<Ok>(`/admin/questionnaires/${id}`, 'DELETE'),

  createGroup: (body: Body) => apiSend<Created>('/admin/question-groups', 'POST', body),
  updateGroup: (gid: number, body: Body) =>
    apiSend<Ok>(`/admin/question-groups/${gid}`, 'PUT', body),
  removeGroup: (gid: number) => apiSend<Ok>(`/admin/question-groups/${gid}`, 'DELETE'),

  createQuestion: (body: Body) => apiSend<Created>('/admin/questions', 'POST', body),
  updateQuestion: (qid: number, body: Body) =>
    apiSend<Ok>(`/admin/questions/${qid}`, 'PUT', body),
  removeQuestion: (qid: number) => apiSend<Ok>(`/admin/questions/${qid}`, 'DELETE'),

  createOption: (body: Body) => apiSend<Created>('/admin/options', 'POST', body),
  updateOption: (oid: number, body: Body) =>
    apiSend<Ok>(`/admin/options/${oid}`, 'PUT', body),
  removeOption: (oid: number) => apiSend<Ok>(`/admin/options/${oid}`, 'DELETE'),
}
