<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import BvIconButton from '@/components/ui/BvIconButton.vue'

// Модалка системы. Оверлей — единственная сущность, получающая тень:
// карточки держатся границей, поэтому тень однозначно означает
// «лежит выше страницы».
//
// Закрытие: Esc, нажатие по затемнению, крестик. Диалог необратимого
// действия — исключение, у него отдельный компонент без этих путей.
//
// Фокус входит в оверлей при открытии и не выходит за него, а при
// закрытии возвращается на кнопку, которая его вызвала: иначе человек
// с клавиатуры оказывается в начале страницы и заново ищет своё место.
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  // Ширина модалки: обычная для формы, широкая для карточки данных.
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['md', 'lg'].includes(v)
  },
  // Нажатие по затемнению закрывает. Отключается там, где в модалке
  // есть незавершённый ввод.
  closeOnOverlay: { type: Boolean, default: true }
})

const emit = defineEmits(['close'])

const dialog = ref(null)
let opener = null

watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    opener = document.activeElement
    await nextTick()
    focusFirst()
    document.addEventListener('keydown', onKeydown, true)
    // Страница под оверлеем не прокручивается: иначе она уезжает
    // под модалкой, и возвращаться приходится вслепую.
    document.body.style.overflow = 'hidden'
  } else {
    detach()
    opener?.focus?.()
    opener = null
  }
})

onBeforeUnmount(detach)

function detach() {
  document.removeEventListener('keydown', onKeydown, true)
  document.body.style.overflow = ''
}

function focusables() {
  return dialog.value?.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea, [href], [tabindex]:not([tabindex="-1"])'
  ) ?? []
}

function focusFirst() {
  const list = focusables()
  if (list.length) list[0].focus()
  else dialog.value?.focus()
}

function onKeydown(event) {
  if (!props.open) return

  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }

  if (event.key !== 'Tab') return

  const list = focusables()
  if (!list.length) return

  const first = list[0]
  const last = list[list.length - 1]

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
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="overlay" @click.self="closeOnOverlay && $emit('close')">
      <div
        ref="dialog"
        class="modal"
        :class="`modal--${size}`"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        tabindex="-1"
      >
        <header class="modal__head">
          <div class="modal__titles">
            <h2 class="modal__title">{{ title }}</h2>
            <span v-if="subtitle" class="modal__subtitle">{{ subtitle }}</span>
          </div>
          <BvIconButton label="Закрыть" @click="$emit('close')">✕</BvIconButton>
        </header>

        <div class="modal__body">
          <slot />
        </div>

        <!-- Кнопки всегда справа внизу, главная последней. -->
        <footer v-if="$slots.actions" class="modal__foot">
          <slot name="actions" />
        </footer>
      </div>
    </div>
  </Teleport>
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

.modal {
  display: flex;
  flex-direction: column;
  width: 100%;
  /* dvh: в Safari адресная строка сворачивается, и модалка, заданная
     в vh, уезжает под неё. */
  max-height: 90vh;
  max-height: 90dvh;
  border-radius: var(--r-lg);
  background: var(--c-surface-raised);
  box-shadow: var(--shadow-overlay);
  overflow: hidden;
}

.modal--md { max-width: 520px; }
.modal--lg { max-width: 760px; }

.modal__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-5) var(--s-6);
  box-shadow: inset 0 -1px 0 var(--c-border);
}

.modal__titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.modal__title {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  letter-spacing: var(--t-h3-ls);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.modal__subtitle {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

/* Прокручивается только тело: шапка с заголовком и кнопки остаются
   на месте, иначе на длинной карточке теряется и то и другое. */
.modal__body {
  padding: var(--s-6);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.modal__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-2);
  padding: var(--s-4) var(--s-6);
  padding-bottom: calc(var(--s-4) + env(safe-area-inset-bottom, 0px));
  box-shadow: inset 0 1px 0 var(--c-border);
}

/* На телефоне модалка занимает экран целиком: обрезанная по краям
   карточка данных на 390px не читается. */
@media (max-width: 640px) {
  .overlay { padding: 0; }

  .modal {
    max-width: none;
    max-height: 100dvh;
    height: 100dvh;
    border-radius: 0;
  }
}
</style>
