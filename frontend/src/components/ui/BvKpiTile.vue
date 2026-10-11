<script setup>
import BvTrend from '@/components/ui/BvTrend.vue'

// Плитка ключевого показателя: подпись, число, тренд, объём выборки.
//
// Число — крупнейший элемент плитки, и оно не переносится: сумма и знак
// валюты остаются вместе даже на узком экране.
//
// Нет данных — прочерк того же кегля, а не ноль и не скрытая плитка.
// Скрытая плитка ломает сетку, а ноль утверждает, что величина равна
// нулю, тогда как на самом деле её просто нечем измерить.
//
// Валюта всегда одна на плитку: складывать валюты запрещено, поэтому
// «Медиана · RUB» и «Медиана · KZT» — две разные плитки.
defineProps({
  label: { type: String, required: true },
  // Уже отформатированное значение либо null.
  value: { type: [String, Number], default: null },
  trend: { type: Number, default: null },
  trendDirection: { type: String, default: null },
  trendUnavailable: { type: String, default: '' },
  // Показатель, у которого нет прошлого периода вовсе: сколько навыков
  // в словаре, сколько полей у строки. Прочерк тренда означал бы «сравнить
  // не с чем сейчас» — а сравнивать здесь не с чем никогда.
  noTrend: { type: Boolean, default: false },
  // Строка под числом: объём выборки или оговорка о его нехватке.
  note: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})
</script>

<template>
  <div class="kpi card">
    <div class="kpi__head">
      <span class="label">{{ label }}</span>
      <BvTrend v-if="!noTrend" :value="trend" :direction="trendDirection" :unavailable="trendUnavailable" />
    </div>

    <span v-if="loading" class="kpi__skeleton" role="status" aria-label="Значение загружается"></span>
    <span v-else class="metric" :class="{ 'kpi__empty': value === null }">{{ value === null ? '—' : value }}</span>

    <span class="kpi__note">{{ note }}</span>
  </div>
</template>

<style scoped>
.kpi {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.kpi__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}

.kpi__empty { color: var(--c-text-quiet); }

/* Скелетон занимает ровно высоту числа: при появлении данных плитка
   не меняет размер и соседние блоки не сдвигаются. */
.kpi__skeleton {
  display: block;
  height: var(--t-metric-lh);
  width: 60%;
  border-radius: var(--r-xs);
  background: var(--track-bar);
}

/* Строка примечания держит высоту всегда — иначе плитки в ряду
   выравниваются по-разному в зависимости от наличия оговорки. */
.kpi__note {
  min-height: var(--t-caption-lh);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}
</style>
