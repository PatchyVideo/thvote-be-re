import { ref, type Ref } from 'vue'
import { ApiError } from '@/api/client'
import { useToast } from './useToast'

// 包一次异步调用:统一 loading/error 态 + 出错 toast(403 除外,那是登出流程)。
export function useAsync<T>() {
  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref('')
  const { toast } = useToast()

  async function run(
    fn: () => Promise<T>,
    opts: { toastError?: boolean } = {},
  ): Promise<T | null> {
    loading.value = true
    error.value = ''
    try {
      const res = await fn()
      data.value = res
      return res
    } catch (e) {
      const isAuth = e instanceof ApiError && (e.status === 403 || e.status === 401)
      const msg = e instanceof ApiError ? e.detail : (e as Error).message
      error.value = msg
      if (opts.toastError !== false && !isAuth) toast(msg, 'error')
      return null
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, run }
}
