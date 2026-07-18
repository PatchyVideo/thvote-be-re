// 唯一网络层。所有请求经此:统一 /api/v1 前缀、X-Admin-Secret 头、403→登出、
// !ok→抛带 detail 的 ApiError。裸 ops 端点(/admin/reload-config)走 apiBare。
import { getSecret, clearSecret } from '@/composables/useAuth'

const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function parseError(r: Response): Promise<string> {
  try {
    const d = await r.json()
    if (d && typeof d.detail === 'string') return d.detail
    return JSON.stringify(d)
  } catch {
    return r.statusText || String(r.status)
  }
}

async function handle(r: Response): Promise<Response> {
  if (r.status === 403 || r.status === 401) {
    clearSecret() // isAuthed 变 false → App 显示登录覆盖层
    throw new ApiError(r.status, 'FORBIDDEN')
  }
  if (!r.ok) throw new ApiError(r.status, await parseError(r))
  return r
}

function headers(extra?: Record<string, string>): Record<string, string> {
  return {
    'X-Admin-Secret': getSecret(),
    'Content-Type': 'application/json',
    ...(extra || {}),
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await handle(await fetch(BASE + path, { headers: headers() }))
  return (await r.json()) as T
}

export async function apiSend<T>(
  path: string,
  method: string,
  body?: unknown,
): Promise<T> {
  const r = await handle(
    await fetch(BASE + path, {
      method,
      headers: headers(),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
  return (await r.json()) as T
}

// 裸 /admin/* ops 端点(不带 /api/v1),仍需 secret。
export async function apiBare<T>(path: string, method: string): Promise<T> {
  const r = await handle(
    await fetch(path, { method, headers: { 'X-Admin-Secret': getSecret() } }),
  )
  return (await r.json()) as T
}

// 原始响应(用于 blob 下载等非 JSON 场景),仍走统一 403/!ok 处理。
export async function apiRaw(path: string): Promise<Response> {
  return handle(await fetch(BASE + path, { headers: headers() }))
}

// 登录探测:用给定 secret 打一个受保护端点,返回 HTTP 状态码(不改全局态)。
export async function probeLogin(secret: string): Promise<number> {
  const r = await fetch(BASE + '/admin/stats', {
    headers: { 'X-Admin-Secret': secret },
  })
  return r.status
}

// 拼 query string(跳过 null/undefined/空串)。
export function qs(params: Record<string, unknown>): string {
  const parts: string[] = []
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  }
  return parts.length ? '?' + parts.join('&') : ''
}
