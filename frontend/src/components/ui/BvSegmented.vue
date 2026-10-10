<script setup>
import { nextTick, ref, watch } from 'vue'

// Переключатель среза: период, категория навыков, тип отчёта.
//
// Выбранный сегмент помечен поверхностью и весом, а не цветом: синим в
// системе окрашены ровно два места — активный пункт навигации и главная
// кнопка экрана. Третий цветной элемент отменяет иерархию.
//
// Роль radiogroup, а не набор кнопок: выбор один из нескольких, и
// программа чтения экрана должна объявить его именно так.
const props = defineProps({
  modelValue: { type: [String, Number], required: true },
  // [{ value, label }]
  options: { type: Array, required: true },
  label: { type: String, required: true }
})

defineEmits(['update:modelValue'])

// Активный сегмент подтягивается в видимую часть.
//
// На узком экране переключатель прокручивается внутри себя, и сегменты,
// не поместившиеся в ширину, остаются за краем. Без этого выбранным
// оказывался невидимый сегмент: человек видел три невыбранные вкладки, а
// данные приходили от четвёртой — выглядело как поломка. Случилось на
// 390 с четырьмя категориями навыков.
const корень = ref(null)

watch(
  () => props.modelValue,
  async () => {
    await nextTick()
    const активный = корень.value?.querySelector('.is-active')
    активный?.scrollIntoView({ inline: 'nearest', block: 'nearest' })
  },
  { immediate: true }
)
</script>

<template>
  <div ref="корень" class="seg" role="radiogroup" :aria-label="label">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      class="seg__item"
      :class="{ 'is-active': option.value === modelValue }"
      :aria-checked="option.value === modelValue"
      @click="$emit('update:modelValue', option.value)"
    >{{ option.label }}</button>
  </div>
</template>

<style scoped>
.seg {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: var(--r-pill);
  background: var(--c-surface-sunken);
  box-shadow: var(--border);
  /* Четыре периода не помещаются в 375px: без прокрутки внутри самой
     группы переключатель распирал бы страницу, и весь экран уезжал бы
     вбок из-за одного элемента управления. */
  max-width: 100%;
  overflow-x: auto;
  scrollbar-width: none;
}

.seg::-webkit-scrollbar { display: none; }

.seg__item {
  flex: 0 0 auto;
  height: var(--h-control-sm);
  padding: 0 var(--s-3);
  border: none;
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--c-text-secondary);
  font-family: var(--font-sans);
  font-size: var(--t-caption-size);
  font-weight: var(--w-regular);
  white-space: nowrap;
  cursor: pointer;
  transition: var(--t-hover);
}

.seg__item:hover { color: var(--c-text); }

.seg__item.is-active {
  background: var(--c-surface);
  color: var(--c-text);
  font-weight: var(--w-medium);
  box-shadow: var(--border);
}
</style>
