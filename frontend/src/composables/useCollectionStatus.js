import { computed, onBeforeUnmount, ref } from 'vue'
import { collection } from '@/api/endpoints'

/**
 * Состояние сбора: опрос статуса, пока работа идёт.
 *
 * Опрос запускается только на время сбора и останавливается сам, когда
 * работа закончилась: постоянный опрос каждые две секунды на пустом
 * экране — это тысячи бессмысленных запросов за рабочий день.
 *
 * Опрос также останавливается при уходе с экрана: таймер, переживший
 * компонент, продолжает дёргать сервер из ниоткуда.
 */
export function useCollectionStatus({ interval = 2000 } = {}) {
  const state = ref(null)
  const error = ref('')
  let timer = null

  const isRunning = computed(() => Boolean(state.value?.is_running))

  async function fetchStatus() {
    try {
      const result = await collection.status()
      state.value = result?.state ?? null
      error.value = ''

      if (state.value?.is_running) {
        schedule()
      } else {
        stopPolling()
      }
    } catch (e) {
      error.value = e.message || 'Статус сбора недоступен.'
      stopPolling()
    }
  }

  function schedule() {
    stopPolling()
    timer = setTimeout(fetchStatus, interval)
  }

  function startPolling() {
    stopPolling()
    fetchStatus()
  }

  function stopPolling() {
    if (timer) clearTimeout(timer)
    timer = null
  }

  onBeforeUnmount(stopPolling)

  return { state, error, isRunning, fetchStatus, startPolling, stopPolling }
}
