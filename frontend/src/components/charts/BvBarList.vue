<script setup>
import { computed } from 'vue'
import { num, percent } from '@/utils/format'

// Сравнение категорий: горизонтальные полосы, отсортированные по величине.
// Это замена кольцевой диаграммы — длину люди сравнивают точно, угол
// сектора нет, а порядок рядов в кольце не читается вовсе.
//
// Значение печатается рядом с полосой, а не только в тултипе: график
// должен читаться без курсора и на бумаге.
//
// Строится вёрсткой, а не библиотекой: разметка списка доступна
// программам чтения экрана, переносится в печать и не требует канваса
// ради шести прямоугольников.
const props = defineProps({
  // [{ label, value }] — порядок задаёт вызывающий, компонент не сортирует:
  // «Прочие» должны остаться последними независимо от величины.
  items: { type: Array, required: true },
  // Целое, от которого считается доля. Без него доли не показываются:
  // сумма показанных категорий не равна целому, если есть остаток.
  total: { type: Number, default: null },
  // Подпись последней строки, которая не участвует в сравнении.
  restLabel: { type: String, default: 'Прочие' },
  // Как напечатать значение. По умолчанию это счётчик; для денег
  // передаётся money — «82 000 ₽» вместо «82 000».
  format: { type: Function, default: null }
})

const max = computed(() => Math.max(...props.items.map((i) => i.value), 1))

// Три тёмные ступени шкалы. Светлые ступени на треке дают контраст
// 1.9:1 и 1.1:1 — полоса становится неотличима от подложки, а длина
// полосы здесь единственный носитель значения.
function colorOf(item, index) {
  if (item.label === props.restLabel) return 'var(--c-data-4)'
  return `var(--c-data-${Math.min(index + 1, 3)})`
}

// Светлой полосе обязателен контур, иначе на треке её не видно.
function ringOf(item) {
  return item.label === props.restLabel ? 'var(--border-strong)' : 'none'
}
</script>

<template>
  <ul class="bars">
    <li v-for="(item, index) in items" :key="item.label" class="bars__row">
      <span class="bars__label" :title="item.label">{{ item.label }}</span>
      <span class="bars__track">
        <span
          class="bars__fill"
          :style="{
            width: `${(item.value / max) * 100}%`,
            background: colorOf(item, index),
            boxShadow: ringOf(item)
          }"
        ></span>
      </span>
      <span class="bars__value">{{ format ? format(item.value) : num(item.value) }}</span>
      <!-- Справа от значения — либо доля целого, либо своя подпись
           строки. Для медианы это объём выборки: «медиана по 47
           вакансиям» — форма из спеки, потому что медиана по трём и по
           восьмидесяти выглядят одинаково, а значат разное. -->
      <span v-if="total" class="bars__pct">{{ percent(item.value, total) }}</span>
      <span v-else-if="item.note" class="bars__pct">{{ item.note }}</span>
    </li>
  </ul>
</template>

<style scoped>
.bars {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.bars__row {
  display: grid;
  grid-template-columns: minmax(80px, 160px) 1fr auto auto;
  align-items: center;
  gap: var(--s-3);
  font-size: var(--t-ui-size);
}

.bars__label {
  color: var(--c-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bars__track {
  height: var(--s-2);
  border-radius: var(--r-pill);
  background: var(--track-bar);
  overflow: hidden;
}

.bars__fill {
  display: block;
  height: 100%;
  border-radius: var(--r-pill);
  min-width: 2px;
}

.bars__value {
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.bars__pct {
  min-width: 56px;
  text-align: right;
  color: var(--c-text-muted);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
}

/* На узком экране подпись занимает свою строку целиком: усечённое до
   восьми знаков название региона не опознаётся. */
@media (max-width: 640px) {
  .bars__row {
    grid-template-columns: 1fr auto auto;
  }

  .bars__label {
    grid-column: 1 / -1;
    white-space: normal;
  }
}
</style>
