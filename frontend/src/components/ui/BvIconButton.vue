<script setup>
// Иконочная кнопка: обновить, открыть, закрыть, убрать.
//
// Знак без подписи опознаётся не всеми и не всегда, поэтому label
// обязателен — он идёт в aria-label и во всплывающую подсказку.
// Кнопка без названия для программы чтения экрана — пустой квадрат.
defineProps({
  label: { type: String, required: true },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['md', 'sm'].includes(v)
  },
  disabled: { type: Boolean, default: false }
})
</script>

<template>
  <button
    type="button"
    class="icon-btn"
    :class="`icon-btn--${size}`"
    :aria-label="label"
    :title="label"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>

<style scoped>
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--c-text-muted);
  cursor: pointer;
  transition: var(--t-hover);
  /* Цель нажатия на касании доводится до 44px невидимым полем вокруг,
     а не увеличением самой кнопки: сетка от этого не разъезжается. */
  position: relative;
}

@media (pointer: coarse) {
  .icon-btn::after {
    content: '';
    position: absolute;
    inset: calc((44px - 100%) / -2);
    min-width: 44px;
    min-height: 44px;
  }
}

.icon-btn--md { width: var(--h-control-md); height: var(--h-control-md); }
.icon-btn--sm { width: var(--h-control-sm); height: var(--h-control-sm); }

.icon-btn:hover:not(:disabled) {
  background: var(--c-surface-hover);
  color: var(--c-text);
}

.icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
