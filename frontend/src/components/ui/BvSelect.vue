<script setup>
import { useId } from 'vue'

// Выпадающий список: опыт, число строк на странице, тип отчёта.
// Нативный select, а не собственный: он умеет клавиатуру, поиск по
// первым буквам и на телефоне открывается системным выбором — всё
// это пришлось бы писать заново и хуже.
defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, required: true },
  // [{ value, label }]
  options: { type: Array, required: true },
  // Скрыть подпись, если поле стоит в ряду с уже названными.
  hideLabel: { type: Boolean, default: false },
  // Выключенное поле — состояние из спеки «Формы»: настройка есть, но
  // сейчас не действует. Выключать его без объяснения нельзя — рядом
  // должно стоять, почему выбор ничего не меняет.
  disabled: { type: Boolean, default: false }
})

defineEmits(['update:modelValue'])

const id = useId()
</script>

<template>
  <div class="select">
    <label class="select__label label" :class="{ 'is-hidden': hideLabel }" :for="id">{{ label }}</label>
    <div class="select__box" :class="{ 'is-disabled': disabled }">
      <select
        :id="id"
        class="select__field"
        :value="modelValue"
        :disabled="disabled"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <option
          v-for="option in options"
          :key="option.value"
          :value="option.value"
          :disabled="option.disabled"
        >{{ option.label }}</option>
      </select>
      <span class="select__arrow" aria-hidden="true">▾</span>
    </div>
  </div>
</template>

<style scoped>
.select {
  /* Точка отсчёта для скрытой подписи. Без неё подпись, спрятанная
     от глаз, отсчитывала положение от страницы: в прокручиваемой
     таблице она оказывалась за правым краем экрана и распирала
     страницу на ширину таблицы. */
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.select__label.is-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}

.select__box {
  position: relative;
  display: flex;
  align-items: center;
  height: var(--h-control-lg);
  border-radius: var(--r-md);
  background: var(--c-surface-sunken);
  box-shadow: var(--border);
}

/* Выключенное поле приглушается так же, как в BvField: значение
   остаётся читаемым, курсор говорит, что менять его сейчас нельзя. */
.select__box.is-disabled { background: var(--c-surface-sunken); }
.select__field:disabled { color: var(--c-text-quiet); cursor: not-allowed; }

.select__field {
  appearance: none;
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  padding: 0 var(--s-8) 0 var(--s-3);
  border: none;
  border-radius: inherit;
  background: transparent;
  color: var(--c-text);
  font-family: var(--font-sans);
  font-size: max(var(--t-ui-size), 16px);
  cursor: pointer;
}

@media (min-width: 768px) {
  .select__field { font-size: var(--t-ui-size); }
}

.select__field:focus { outline: none; }

.select__box:has(.select__field:focus-visible) {
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1px var(--c-accent), var(--focus-ring);
}

.select__arrow {
  position: absolute;
  right: var(--s-3);
  color: var(--c-text-muted);
  pointer-events: none;
}
</style>
