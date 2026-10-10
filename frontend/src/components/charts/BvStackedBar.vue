<script setup>
import { computed } from 'vue'
import { num, percent } from '@/utils/format'

// Доли целого: составная полоса вместо кольца. Доли читаются длиной,
// подписи стоят рядом, порядок сохраняется — в кольце он теряется.
//
// Здесь допустимы все пять ступеней шкалы: полоса лежит не на треке,
// а рядом с соседними сегментами, и светлые ступени различимы. Светлому
// сегменту всё равно добавляется контур — на белом фоне карточки его
// край иначе не виден.
const props = defineProps({
  // [{ label, value }] в порядке убывания.
  items: { type: Array, required: true }
})

const total = computed(() => props.items.reduce((sum, i) => sum + i.value, 0))
</script>

<template>
  <div class="stack">
    <div class="stack__bar" role="img" :aria-label="`Доли: ${items.map((i) => `${i.label} ${percent(i.value, total)}`).join(', ')}`">
      <span
        v-for="(item, index) in items"
        :key="item.label"
        class="stack__seg"
        :style="{
          width: `${(item.value / total) * 100}%`,
          background: `var(--c-data-${Math.min(index + 1, 5)})`,
          boxShadow: index >= 3 ? 'inset 0 0 0 1px var(--c-border-strong)' : 'none'
        }"
      ></span>
    </div>

    <ul class="stack__legend">
      <li v-for="(item, index) in items" :key="item.label" class="stack__item">
        <span
          class="stack__swatch"
          :style="{
            background: `var(--c-data-${Math.min(index + 1, 5)})`,
            boxShadow: index >= 3 ? 'inset 0 0 0 1px var(--c-border-strong)' : 'none'
          }"
          aria-hidden="true"
        ></span>
        <span class="stack__label">{{ item.label }}</span>
        <span class="stack__value">{{ num(item.value) }}</span>
        <span class="stack__pct">{{ percent(item.value, total) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.stack__bar {
  display: flex;
  height: var(--s-6);
  border-radius: var(--r-xs);
  overflow: hidden;
  background: var(--track-bar);
}

.stack__seg { display: block; height: 100%; }

.stack__legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.stack__item {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: var(--s-3);
  font-size: var(--t-ui-size);
}

.stack__swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex: 0 0 auto;
}

.stack__label {
  color: var(--c-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stack__value {
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
}

.stack__pct {
  min-width: 56px;
  text-align: right;
  color: var(--c-text-muted);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
}
</style>
