import { computed, ref } from 'vue'

// 模块级单例:secret 存 sessionStorage,响应式 ref 驱动登录壳显示。
const secret = ref<string>(sessionStorage.getItem('adminSecret') || '')

export function getSecret(): string {
  return secret.value
}

export function setSecret(s: string): void {
  secret.value = s
  sessionStorage.setItem('adminSecret', s)
}

export function clearSecret(): void {
  secret.value = ''
  sessionStorage.removeItem('adminSecret')
}

export function useAuth() {
  const isAuthed = computed(() => secret.value.length > 0)
  return { isAuthed, setSecret, clearSecret }
}
