import { computed, ref } from 'vue'

export function usePagination(pageSize = 50) {
  const page = ref(1)
  const size = ref(pageSize)
  const total = ref(0)

  const pageCount = computed(() =>
    Math.max(1, Math.ceil(total.value / size.value)),
  )
  const hasPrev = computed(() => page.value > 1)
  const hasNext = computed(() => page.value < pageCount.value)

  function setTotal(t: number): void {
    total.value = t
  }
  function next(): void {
    if (hasNext.value) page.value++
  }
  function prev(): void {
    if (hasPrev.value) page.value--
  }
  function reset(): void {
    page.value = 1
  }

  return { page, size, total, pageCount, hasPrev, hasNext, setTotal, next, prev, reset }
}
