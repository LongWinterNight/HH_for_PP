<script setup>
import { computed } from 'vue'
import BvChartCanvas from '@/components/charts/BvChartCanvas.vue'
import { baseScales, markerColor, markerHatch, token, tooltipWithSample } from '@/utils/chartTheme'
import { num } from '@/utils/format'

// Столбцы для счётных величин по периодам: вакансий в месяц, запусков
// сбора в неделю, — и для распределения: вакансий в зарплатной корзине.
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
  unit: { type: String, default: '' },
  // Столбец с маркером: на гистограмме это корзина с медианой. Маркер
  // на графике один — правило системы, — поэтому это номер, а не список.
  markerIndex: { type: Number, default: null },
  // Выбранный столбец. Жёлтым он не красится: жёлтый занят маркером, и
  // второй жёлтый столбец отменил бы смысл первого. Выбор показан самой
  // тёмной ступенью шкалы.
  selectedIndex: { type: Number, default: null },
  // Столбцы нажимаются, хотя выбранного нет: краткая карточка, где
  // нажатие открывает разбор на этом столбце.
  selectable: { type: Boolean, default: false },
  // Свои строки подсказки по номеру столбца — когда столбец значит
  // больше, чем одно число: диапазон корзины, доля, объём.
  tooltipLines: { type: Function, default: null }
})

// Событие есть только у графика, которому оно нужно: столбцы без
// слушателя не притворяются кнопками и курсор над ними не меняется.
const emit = defineEmits(['select'])

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
      if (ctx.dataIndex === props.markerIndex) return markerColor()
      if (ctx.dataIndex === props.selectedIndex) return token('--c-data-1')
      return token('--c-data-2')
    },
    // Выбранная корзина с медианой остаётся жёлтой, и выбор без обводки
    // на ней не был бы виден.
    borderColor: token('--c-data-1'),
    borderWidth: (ctx) => (
      ctx.dataIndex === props.selectedIndex && ctx.dataIndex === props.markerIndex ? 2 : 0
    )
  }]
}))

const выбирается = computed(() => props.selectable || props.selectedIndex !== null)

const options = computed(() => ({
  scales: baseScales({ unit: props.unit }),
  onClick: (событие, элементы) => {
    if (выбирается.value && элементы.length) emit('select', элементы[0].index)
  },
  onHover: (событие, элементы) => {
    if (!выбирается.value || !событие.native?.target) return
    событие.native.target.style.cursor = элементы.length ? 'pointer' : 'default'
  },
  plugins: {
    tooltip: props.tooltipLines
      ? {
          callbacks: {
            title: (items) => items[0]?.label ?? '',
            label: (item) => props.tooltipLines(item.dataIndex)
          }
        }
      : tooltipWithSample({
          formatValue: (v) => (props.unit ? `${num(v)} ${props.unit}` : num(v))
        })
  }
}))
</script>

<template>
  <BvChartCanvas type="bar" :data="data" :options="options" :label="label" />
</template>
