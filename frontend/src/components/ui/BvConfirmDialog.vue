<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvField from '@/components/ui/BvField.vue'

// Подтверждение необратимого действия вводом слова.
//
// Перезапись базы одним нажатием уничтожает собранное без возможности
// вернуть. Поэтому кнопка включается только после точного совпадения
// слова: это не формальность, а единственная защита от случайного
// нажатия по привычке.
//
// Предупреждение подаётся формой, а не цветом: знак, метка и двойная
// рамка. Жёлтый в системе занят маркером, и второй жёлтый со смыслом
// «внимание» был бы неотличим.
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  // Что именно произойдёт и что будет потеряно.
  message: { type: String, required: true },
  word: { type: String, default: 'перезаписать' },
  confirmLabel: { type: String, default: 'Подтвердить' }
})

const emit = defineEmits(['confirm', 'cancel'])

const typed = ref('')
const dialog = ref(null)
const matches = computed(() => typed.value.trim().toLowerCase() === props.word.toLowerCase())

// Элемент, с которого открыли диалог: туда возвращается фокус после
// закрытия. Без этого пользователь клавиатуры после Esc оказывается в
// начале страницы и заново ищет место, где был.
let opener = null

watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    typed.value = ''
    opener = document.activeElement
    await nextTick()
    // Фокус уходит в поле подтверждения: без этого он остаётся на
    // кнопке за диалогом, и человек с клавиатуры продолжает ходить
    // по странице, которую диалог перекрывает.
    dialog.value?.querySelector('input')?.focus()
    document.addEventListener('keydown', onKeydown, true)
  } else {
    document.removeEventListener('keydown', onKeydown, true)
    opener?.focus?.()
    opener = null
  }
})

onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown, true))

/**
 * Esc закрывает, Tab не выпускает фокус наружу.
 *
 * Ловушка нужна не ради строгости: диалог подтверждает необратимое
 * действие, и уйти из него незаметно для себя нельзя.
 */
function onKeydown(event) {
  if (!props.open) return

  if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
    return
  }

  if (event.key !== 'Tab') return

  const focusable = dialog.value?.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), [href], select, textarea, [tabindex]:not([tabindex="-1"])'
  )
  if (!focusable || !focusable.length) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  } else if (!dialog.value.contains(document.activeElement)) {
    event.preventDefault()
    first.focus()
  }
}

function confirm() {
  if (matches.value) emit('confirm')
}
</script>

<template>
  <div v-if="open" class="overlay" @click.self="$emit('cancel')">
    <div ref="dialog" class="dialog" role="alertdialog" aria-modal="true" :aria-label="title">
      <div class="dialog__warning">
        <span class="dialog__mark" aria-hidden="true">!</span>
        <span class="dialog__warning-text">Внимание · необратимо</span>
      </div>

      <h2 class="dialog__title">{{ title }}</h2>
      <p class="dialog__message">{{ message }}</p>

      <BvField
        v-model="typed"
        :label="`Введите слово «${word}», чтобы подтвердить`"
        :placeholder="word"
        :hint="matches ? 'Слово совпало — действие разблокировано.' : 'Кнопка включится после точного совпадения.'"
        :state="matches ? 'checked' : 'default'"
        @keydown.enter="confirm"
      />

      <div class="dialog__actions">
        <BvButton @click="$emit('cancel')">Отмена</BvButton>
        <BvButton variant="danger" :disabled="!matches" @click="confirm">{{ confirmLabel }}</BvButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--s-4);
  background: rgba(5, 0, 56, 0.32);
}

.dialog {
  width: min(480px, 100%);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-6);
  border-radius: var(--r-lg);
  background: var(--c-surface-raised);
  /* Единственная тень системы принадлежит всплывающему. */
  box-shadow: var(--border-warning), var(--shadow-overlay);
}

.dialog__warning {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.dialog__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--r-xs);
  box-shadow: var(--border-strong);
  font-weight: var(--w-strong);
  color: var(--c-text);
}

.dialog__warning-text {
  font-size: var(--t-caption-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.dialog__title {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.dialog__message {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-2);
}
</style>
