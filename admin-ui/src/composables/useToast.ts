import { ref } from 'vue'

export type ToastKind = 'info' | 'error' | 'success'
export interface ToastMsg {
  id: number
  text: string
  kind: ToastKind
}

// 模块级单例队列;<Toast> 组件渲染它。
const toasts = ref<ToastMsg[]>([])
let seq = 0

export function useToast() {
  function toast(text: string, kind: ToastKind = 'info', ms = 3200): void {
    const id = ++seq
    toasts.value.push({ id, text, kind })
    window.setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, ms)
  }
  return { toasts, toast }
}
