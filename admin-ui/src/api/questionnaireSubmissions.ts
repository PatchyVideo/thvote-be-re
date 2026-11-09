import { apiGet, apiSend, qs } from './client'

export interface QuestionnaireProgress {
  id: number
  key: string
  title: string
  required: boolean
  completed: boolean
}

export interface SubmissionSummary {
  vote_id: string
  vote_year: number
  attempt: number
  created_at: string
  row_count: number
  invalidated: boolean
  is_latest: boolean
  completed: boolean
  eligible: boolean
  progress: QuestionnaireProgress[]
}

interface ReadableAnswer {
  id: number
  group_id: number
  active_question_id: number | null
  question_content: string | null
  question_type: string | null
  selected_options: { id: number; content: string | null }[]
  input_text: string | null
  missing_references: string[]
}

export interface SubmissionBatch extends SubmissionSummary {
  questionnaires: { id: number; title: string | null; answers: ReadableAnswer[] }[]
}

export interface SubmissionDetail {
  vote_id: string
  vote_year: number
  batches: SubmissionBatch[]
}

export interface SubmissionsPage {
  items: SubmissionSummary[]
  total: number
  page: number
  page_size: number
}

const BASE = '/admin/questionnaire-submissions'
function detailPath(voteYear: number, voteId: string): string {
  return `${BASE}/${voteYear}/${encodeURIComponent(voteId)}`
}

export const questionnaireSubmissionsApi = {
  list: (params: {
    vote_year?: number
    vote_id?: string
    invalidated?: boolean
    page: number
    page_size: number
  }) => apiGet<SubmissionsPage>(BASE + qs(params)),
  detail: (voteYear: number, voteId: string) =>
    apiGet<SubmissionDetail>(detailPath(voteYear, voteId)),
  setInvalidated: (voteYear: number, voteId: string, attempt: number, invalidated: boolean) =>
    apiSend<{ affected_rows: number; invalidated: boolean; detail: string }>(
      `${detailPath(voteYear, voteId)}/${attempt}`, 'PATCH', { invalidated },
    ),
}
