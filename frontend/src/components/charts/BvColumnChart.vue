<script setup>
import { computed } from 'vue'
import BvChartCanvas from '@/components/charts/BvChartCanvas.vue'
import { baseScales, markerHatch, token, tooltipWithSample } from '@/utils/chartTheme'
import { num } from '@/utils/format'

// Столбцы для счётных величин по периодам: вакансий в месяц, запусков
// сбора в неделю.
//
// Последний период, если он ещё не закрыт, отмечается маркером и
// штриховкой. Без пометки семнадцать вакансий за неполный сентябрь
// читаются как обвал рынка — а это просто пятое число месяца.
const props = defineProps({
  labels: { type: Array, required: true },
  values: { type: Array, required: true },
  // Объёмы выборки по периодам — уходят в тултип.
  samples: { type: Array, default: null },
  // Последний столбец относится к незакрытому периоду.
  openLast: { type: Boolean, default: false },
  label: { type: String, required: true },
  unit: { type: String, default: '' }
})

const data = computed(() => ({
  labels: props.labels,
  datasets: [{
    data: props.values,
    samples: props.samples,
    borderRadius: 4,
    maxBarThickness: 40,
    backgroundColor: (ctx) => {
      const isLast = ctx.dataIndex === props.values.length - 1
      if (props.openLast && isLast && ctx.chart.ctx) return markerHatch(ctx.chart.ctx)
      return token('--c-data-2')
    }
  }]
}))

const options = computed(() => ({
  scales: baseScales({ unit: props.unit }),
  plugins: {
    tooltip: tooltipWithSample({
      formatValue: (v) => (props.unit ? `${num(v)} ${props.unit}` : num(v))
    })
  }
}))
</script>

<template>
  <BvChartCanvas type="bar" :data="data" :options="options" :label="label" />
</template>
