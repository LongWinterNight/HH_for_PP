<script setup>
import { computed } from 'vue'
import BvChartCanvas from '@/components/charts/BvChartCanvas.vue'
import { baseScales, token, tooltipWithSample } from '@/utils/chartTheme'
import { money } from '@/utils/format'

// Линия — для непрерывных величин: медиана зарплаты по месяцам.
//
// Точки на линии не рисуются, кроме наведённой: двенадцать кружков
// превращают линию в пунктир из шума. Тултип обязательно показывает
// объём выборки — медиана по трём вакансиям и по восьмидесяти выглядят
// одинаково, а значат разное.
//
// Средняя здесь не строится ни при каких условиях: её тянут выбросы.
const props = defineProps({
  labels: { type: Array, required: true },
  values: { type: Array, required: true },
  samples: { type: Array, default: null },
  label: { type: String, required: true },
  // Одна валюта на график. Складывать и пересчитывать валюты запрещено,
  // поэтому график всегда строится внутри одной.
  currency: { type: String, default: 'RUR' }
})

const data = computed(() => ({
  labels: props.labels,
  datasets: [{
    data: props.values,
    samples: props.samples,
    borderColor: token('--c-data-2'),
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBackgroundColor: token('--c-marker'),
    pointHoverBorderColor: token('--c-data-1'),
    pointHoverBorderWidth: 2,
    tension: 0.25,
    // Разрыв в данных остаётся разрывом: соединять его линией значит
    // рисовать значение там, где вакансий не было.
    spanGaps: false
  }]
}))

const options = computed(() => ({
  interaction: { mode: 'index', intersect: false },
  scales: baseScales(),
  plugins: {
    tooltip: tooltipWithSample({ formatValue: (v) => money(v, props.currency) })
  }
}))
</script>

<template>
  <BvChartCanvas type="line" :data="data" :options="options" :label="label" />
</template>
