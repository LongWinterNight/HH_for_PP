import { ref, shallowRef } from 'vue'

/**
 * Загрузка данных одним куском: значение, признак загрузки, текст ошибки.
 *
 * Три состояния всегда идут вместе, потому что экран обязан собрать все
 * четыре состояния данных — заполненное, пустое, загрузку и ошибку.
 * Когда каждый экран заводит свои три переменные, одно из состояний
 * рано или поздно забывают, и пользователь видит пустоту вместо
 * объяснения.
 *
 * Устаревший ответ отбрасывается: при быстром переключении фильтров
 * запросы возвращаются не в том порядке, в каком уходили, и без
 * отмены на экране оседает результат предыдущего фильтра.
 */
export function useApi(loader, { immediate = false, initial = null } = {}) {
  const data = shallowRef(initial)
  const loading = ref(false)
  const error = ref('')

  let controller = null

  async function load(...args) {
    if (controller) controller.abort()
    controller = new AbortController()
    const signal = controller.signal

    loading.value = true
    error.value = ''

    try {
      const result = await loader(...args, { signal })
      if (signal.aborted) return null
      data.value = result
      return result
    } catch (e) {
      if (e.name === 'AbortError') return null
      error.value = e.message || 'Запрос не выполнен.'
      return null
    } finally {
      if (!signal.aborted) loading.value = false
    }
  }

  if (immediate) load()

  return { data, loading, error, load }
}
