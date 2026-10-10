<script setup>
import BvStatus from '@/components/ui/BvStatus.vue'
import BvButton from '@/components/ui/BvButton.vue'
import { useToast } from '@/composables/useToast'

// Слой уведомлений: правый нижний угол, фиксированная ширина.
//
// Фон тоста всегда белый, цвет остаётся у знака статуса: цветная
// плашка во всю ширину спорит с единственными двумя окрашенными
// местами экрана — активным пунктом навигации и главной кнопкой.
const toast = useToast()

const LABELS = {
  ok: 'Готово',
  err: 'Ошибка',
  run: 'Идёт',
  info: 'Сообщение'
}
</script>

<template>
  <!-- role="status": программа чтения объявляет появление сообщения,
       но не перебивает пользователя на полуслове. -->
  <div class="toasts" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="item in toast.items" :key="item.id" class="toast">
        <div class="toast__head">
          <BvStatus :kind="item.kind === 'info' ? 'idle' : item.kind" :label="LABELS[item.kind]" />
          <button type="button" class="toast__close" aria-label="Закрыть сообщение" @click="toast.dismiss(item.id)">✕</button>
        </div>

        <p class="toast__title">{{ item.title }}</p>
        <p v-if="item.text" class="toast__text">{{ item.text }}</p>

        <BvButton
          v-if="item.action"
          size="sm"
          @click="item.action.run(); toast.dismiss(item.id)"
        >{{ item.action.label }}</BvButton>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: var(--s-4);
  bottom: calc(var(--s-4) + env(safe-area-inset-bottom, 0px));
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  width: min(360px, calc(100vw - var(--s-8)));
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-2);
  padding: var(--s-4);
  border-radius: var(--r-md);
  background: var(--c-surface-raised);
  box-shadow: var(--border), var(--shadow-popover);
}

.toast__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  width: 100%;
}

.toast__close {
  border: none;
  background: transparent;
  padding: 0;
  color: var(--c-text-muted);
  font-size: var(--t-caption-size);
  cursor: pointer;
  flex: 0 0 auto;
}

.toast__close:hover { color: var(--c-text); }

.toast__title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
  max-width: none;
}

.toast__text {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity var(--dur-ui) var(--ease-ui), transform var(--dur-ui) var(--ease-ui);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
