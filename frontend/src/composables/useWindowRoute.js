import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// Окно разбора, записанное в адресе: `?window=salary`.
//
// Зачем адрес. На телефоне окно занимает экран целиком, и человек
// закрывает его кнопкой «назад» — без записи в истории она увела бы с
// экрана вовсе. Заодно окно можно открыть ссылкой.
//
// Закрытие зависит от того, как окно открыли. Открытое кнопкой снимается
// шагом назад: иначе в истории осталась бы запись, которая открывает его
// снова. Открытое ссылкой шага назад не имеет — параметр просто убирается.
export function useWindowRoute(name) {
  const route = useRoute()
  const router = useRouter()
  let pushed = false

  const open = computed(() => route.query.window === name)

  function show() {
    if (open.value) return
    pushed = true
    router.push({ query: { ...route.query, window: name } })
  }

  function hide() {
    if (!open.value) return
    if (pushed) {
      pushed = false
      router.back()
      return
    }
    const rest = { ...route.query }
    delete rest.window
    router.replace({ query: rest })
  }

  return { open, show, hide }
}
