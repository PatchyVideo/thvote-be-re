// 后端契约的 TS 镜像。字段名/形状与 src/apps/admin/**/schemas.py 对齐。
// 改契约只动这里 + 对应 api 模块,全站 view 编译期即报错 —— 这是"对齐固化"的落点。

// ── admin: stats / users ──────────────────────────────────────────────────
export interface VoteWindowStatus {
  status: string // open / closed / upcoming
  start: string
  end: string
}

export interface StatsResponse {
  vote_year: number
  total_users: number
  vote_window: VoteWindowStatus
  submissions: Record<string, number> // category -> count
}

export interface UserAdminItem {
  id: string
  nickname: string | null
  email: string | null
  phone: string | null
  email_verified: boolean
  phone_verified: boolean
  register_date: string | null
  removed: boolean
}

export interface UserListResponse {
  items: UserAdminItem[]
  total: number
}

export interface BanResponse {
  ok: boolean
  removed: boolean
}

export interface ReloadConfigResponse {
  status: string
  message: string
  database_url: string
  database_name: string
  vote_year: number
}

// ── monitor (B-049) ─────────────────────────────────────────────────────────
export interface OverviewResponse {
  category_totals: Record<string, number>
  distinct_ips: number
  distinct_devices: number
  submissions_by_day: Array<{ date: string; count: number }>
}

export interface GroupItem {
  key: string
  voter_count: number
}

export interface GroupsResponse {
  kind: string
  items: GroupItem[]
}

export interface SuspectItem {
  vote_id: string
  score: number
  reasons: string[]
}

export interface SuspectsResponse {
  items: SuspectItem[]
  total: number
  page: number
  page_size: number
  truncated: boolean
}

export interface VoteRow {
  id: number
  vote_id: string
  user_ip: string
  device: string | null
  fill_duration_ms: number | null
  client_env: Record<string, unknown> | null
  attempt: number | null
  invalidated: boolean
  created_at: string | null
}

export interface VotesPage {
  items: VoteRow[]
  total: number
  page: number
  page_size: number
}

export interface AccountReview {
  status: string
  note: string
  updated_at: string
}

export interface AccountDetail {
  vote_id: string
  votes: Record<string, Array<Record<string, unknown>>>
  review: AccountReview | null
  ip_groups: string[]
  device_groups: string[]
}

export interface ActionResult {
  ok: boolean
  detail: string
}

export const VOTE_CATEGORIES = ['character', 'music', 'cp', 'paper', 'dojin'] as const
export type VoteCategory = (typeof VOTE_CATEGORIES)[number]

// 分页通用包装。
export interface Paged<T> {
  items: T[]
  total: number
}

// ── candidates ──────────────────────────────────────────────────────────────
export interface CandidateAdminItem {
  id: number
  vote_year: number
  name: string
  name_jp: string
  type: string
  origin: string | null // character only
  first_appearance: string | null
  album: string | null // music only
}
export interface CandidateField {
  name: string
  required: boolean
}
export interface CandidateImportResult {
  ok: boolean
  valid_count: number
  imported: number
  valid: Record<string, string>[]
  rejected: { line: number; reason: string }[]
}
export interface MergeItem {
  id: number
  name: string
  merged_into: number
}

// ── sync ──────────────────────────────────────────────────────────────────
export interface SyncStatus {
  run_id: string | null
  status: string // "running" | "idle"(完成后即回 idle,见 SyncView 处理)
  current_collection?: string | null
  processed: number
  total: number
  inserted: number
  skipped: number
  errors: number
}
export interface SyncHistoryItem {
  id: number
  run_id: string
  started_at: string
  completed_at: string | null
  status: string
  collections: string[]
  total_docs: number
  inserted: number
  skipped: number
  errors: number
  initiated_by: string
}
export interface SyncStartResult {
  ok: boolean
  run_id: string
  message: string
}

// ── nominations ─────────────────────────────────────────────────────────────
export interface NominationItem {
  id: number
  vote_id: string
  udid: string | null
  url: string
  title: string
  author: string
  dojin_type: string
  publish_date: string | null
  status: string
  reject_reason: string | null
  created_at: string
}

// ── questionnaire (nested tree) ──────────────────────────────────────────────
export type QuestionType = 'Single' | 'Multiple' | 'Input'
export const QUESTION_TYPES: QuestionType[] = ['Single', 'Multiple', 'Input']

export interface QuestionnaireListItem {
  id: number
  key: string
  title: string
  category: string
  required: boolean
  order: number
  group_count: number
  question_count: number
}
export interface OptionNode {
  id: number
  order: number
  content: string
  relatedQuestionIds: number[]
  mutexOptionIds: number[]
  optionGroup: number
}
export interface QuestionNode {
  id: number
  order: number
  type: QuestionType
  content: string
  introduction: string
  maxInputLen: number
  options: OptionNode[]
}
export interface GroupNode {
  id: number
  order: number
  hiddenByDefault: boolean
  questions: QuestionNode[]
}
export interface QuestionnaireTree {
  id: number
  key: string
  title: string
  introduction: string
  category: 'main' | 'extra'
  required: boolean
  order: number
  questionGroups: GroupNode[]
}

// ── logs ──────────────────────────────────────────────────────────────────
export interface ActivityLogItem {
  id: number
  event_type: string
  user_id: string | null
  requester_ip: string | null
  created_at: string
}
