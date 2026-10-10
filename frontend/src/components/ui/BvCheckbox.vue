<script setup>
import { useId } from 'vue'

// Флажок: «только с указанной зарплатой», «инкрементальный режим».
// Метка кликабельна вместе с квадратом — попасть в 16 пикселей
// пальцем нельзя, а в строку целиком можно.
defineProps({
  modelValue: { type: Boolean, default: false },
  label: { type: String, required: true }
})

defineEmits(['update:modelValue'])

const id = useId()
</script>

<template>
  <label class="check" :for="id">
    <input
      :id="id"
      class="check__input"
      type="checkbox"
      :checked="modelValue"
      @change="$emit('update:modelValue', $event.target.checked)"
    >
    <span class="check__box" aria-hidden="true">
      <svg viewBox="0 0 12 12" width="12" height="12" focusable="false">
        <path d="M2.5 6.2 L4.8 8.5 L9.5 3.8" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </span>
    <span class="check__text">{{ label }}</span>
  </label>
</template>

<style scoped>
.check {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  min-height: var(--h-control-lg);
  font-size: var(--t-ui-size);
  color: var(--c-text-secondary);
  cursor: pointer;
}

.check__input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.check__box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  border-radius: var(--r-xs);
  background: var(--c-surface);
  box-shadow: var(--border-strong);
  color: transparent;
  transition: var(--t-hover);
}

.check__input:checked + .check__box {
  background: var(--c-accent);
  box-shadow: none;
  color: var(--c-text-inverse);
}

.check__input:focus-visible + .check__box {
  box-shadow: var(--border-strong), var(--focus-ring);
}

.check:hover .check__text { color: var(--c-text); }
</style>
