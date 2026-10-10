<script setup>
import { computed, useId } from 'vue'

// Поле ввода со всеми семью состояниями системы: пустое, заполненное,
// фокус, ошибка, проверено, выключено, только чтение.
//
// Два правила, ради которых компонент вообще существует:
//
// 1. Место под сообщение зарезервировано всегда. Если строку ошибки
//    показывать только при ошибке, появление сообщения сдвинет форму
//    под курсором и уведёт кнопку из-под пальца.
// 2. Подпись стоит над полем, а не внутри. Плавающая подпись исчезает
//    при вводе, и человек перестаёт понимать, что заполняет.
const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, required: true },
  type: { type: String, default: 'text' },
  placeholder: { type: String, default: '' },
  // Пояснение под полем: что это за значение и чем грозит ошибка.
  hint: { type: String, default: '' },
  // Сообщение проверки. Показывается вместо hint, тон берётся из state.
  message: { type: String, default: '' },
  state: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'error', 'checked'].includes(v)
  },
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  // Единица измерения справа в поле: «мс», «₽», «шт».
  suffix: { type: String, default: '' }
})

defineEmits(['update:modelValue', 'blur'])

const id = useId()
const messageId = computed(() => `${id}-message`)
const text = computed(() => props.message || props.hint)
</script>

<template>
  <div class="field" :class="`field--${state}`">
    <label class="field__label label" :for="id">
      {{ label }}
      <span v-if="required" class="field__required">обязательно</span>
    </label>

    <div class="field__box">
      <input
        :id="id"
        class="field__input"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :required="required"
        :aria-invalid="state === 'error' || undefined"
        :aria-describedby="text ? messageId : undefined"
        @input="$emit('update:modelValue', $event.target.value)"
        @blur="$emit('blur', $event)"
      >
      <span v-if="suffix" class="field__suffix mono-num">{{ suffix }}</span>
      <!-- Знак дублирует цвет рамки: цвет никогда не единственный
           носитель смысла. -->
      <span v-if="state === 'error'" class="field__mark" aria-hidden="true">✕</span>
      <span v-else-if="state === 'checked'" class="field__mark" aria-hidden="true">✓</span>
    </div>

    <!-- Строка сообщения занимает место всегда, даже пустая. -->
    <p :id="messageId" class="field__message" :role="state === 'error' ? 'alert' : undefined">
      {{ text }}
    </p>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.field__label {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
}

/* Помечается обязательное, а не необязательное: в формах продукта
   обязательных меньшинство. */
.field__required {
  font-size: var(--t-caption-size);
  color: var(--c-negative);
}

.field__box {
  position: relative;
  display: flex;
  align-items: center;
  height: var(--h-control-lg);
  border-radius: var(--r-md);
  background: var(--c-surface-sunken);
  box-shadow: var(--border);
  transition: var(--t-hover);
}

.field__input {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  padding: 0 var(--s-3);
  border: none;
  border-radius: inherit;
  background: transparent;
  color: var(--c-text);
  font-family: var(--font-sans);
  /* 16px на мобильном: меньший кегль заставляет iOS увеличивать
     страницу при фокусе, и вёрстка уезжает. */
  font-size: max(var(--t-ui-size), 16px);
  font-variant-numeric: tabular-nums;
}

@media (min-width: 768px) {
  .field__input { font-size: var(--t-ui-size); }
}

.field__input::placeholder {
  color: var(--c-text-quiet);
}

.field__input:focus { outline: none; }

/* Обводка по focus-visible: щелчок мышью её не вызывает. */
.field__box:has(.field__input:focus-visible) {
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1px var(--c-accent), var(--focus-ring);
}

.field__suffix,
.field__mark {
  padding-right: var(--s-3);
  flex: 0 0 auto;
}

.field__mark { font-size: var(--t-ui-size); }

.field--error .field__box {
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1px var(--c-negative);
}
.field--error .field__mark { color: var(--c-negative); }
.field--error .field__message { color: var(--c-status-err-text); }

.field--checked .field__box { background: var(--c-surface); }
.field--checked .field__mark { color: var(--c-positive); }
.field--checked .field__message { color: var(--c-status-ok-text); }

/* Выключенное поле отдаёт значение самой тихой ступенью: оно есть,
   но сейчас не действует. Только чтение — это факт от API, а не
   настройка, поэтому значение остаётся читаемым. */
.field__input:disabled { color: var(--c-text-quiet); cursor: not-allowed; }
.field__input[readonly] { color: var(--c-text-muted); cursor: default; }

.field__message {
  /* Строка держит высоту даже пустой — форма не прыгает. */
  min-height: var(--t-caption-lh);
  margin: 0;
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}
</style>
