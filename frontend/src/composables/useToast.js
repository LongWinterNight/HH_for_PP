import { reactive } from 'vue'

/**
 * Тосты: короткие сообщения о том, что произошло.
 *
 * Форма сообщения выбирается по длительности операции. Ниже секунды
 * индикатор вредит — мигание сбивает сильнее самой задержки, поэтому
 * мгновенные действия (фильтр, сортировка) тостов не получают вовсе.
 *
 * Успех живёт четыре секунды и уходит сам. Ошибка не уходит, пока её
 * не закрыли, и всегда несёт действие: сообщение, из которого не
 * следует, что делать, — это просто помеха.
 *
 * Больше трёх подряд не показывается: четвёртый вытесняет самый
 * старый. Стопка из семи уведомлений перестаёт быть уведомлением.
 */

const MAX_VISIBLE = 3
const SUCCESS_LIFE = 4000

const state = reactive({ items: [] })

let seq = 0

function push(toast) {
  const item = {
    id: ++seq,
    kind: 'info',
    title: '',
    text: '',
    action: null,
    ...toast
  }

  state.items.push(item)
  if (state.items.length > MAX_VISIBLE) state.items.splice(0, state.items.length - MAX_VISIBLE)

  // Ошибку убирает только человек: она требует решения, а не внимания.
  if (item.kind !== 'err') {
    setTimeout(() => dismiss(item.id), item.life ?? SUCCESS_LIFE)
  }

  return item.id
}

function dismiss(id) {
  const index = state.items.findIndex((t) => t.id === id)
  if (index !== -1) state.items.splice(index, 1)
}

export function useToast() {
  return {
    items: state.items,
    dismiss,
    /** Готово: что произошло и чем измеряется. */
    success: (title, text, action) => push({ kind: 'ok', title, text, action }),
    /** Идёт: показывается только для операций длиннее секунды. */
    progress: (title, text) => push({ kind: 'run', title, text, life: 8000 }),
    /** Ошибка: висит до закрытия и всегда предлагает действие. */
    error: (title, text, action) => push({ kind: 'err', title, text, action })
  }
}
