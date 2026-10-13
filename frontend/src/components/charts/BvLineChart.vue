<script setup>
import { computed } from 'vue'
import BvChartCanvas from '@/components/charts/BvChartCanvas.vue'
import { baseScales, markerColor, seriesStyle, token, tooltipWithSample, withAlpha } from '@/utils/chartTheme'
import { money, vacancies as vacanciesCount } from '@/utils/format'

// Линия — для непрерывных величин: медиана зарплаты по периодам.
//
// Точки на линии не рисуются, кроме наведённой, выбранной и тех, что
// иначе пропали бы: двенадцать кружков превращают линию в пунктир из
// шума. Тултип обязательно показывает объём выборки — медиана по трём
// вакансиям и по восьмидесяти выглядят одинаково, а значат разное.
//
// Средняя здесь не строится ни при каких условиях: её тянут выбросы.
//
// Всё, что ниже первых пяти свойств, необязательно: без них график
// остаётся прежней одной линией.
const props = defineProps({
  labels: { type: Array, required: true },
  values: { type: Array, default: () => [] },
  samples: { type: Array, default: null },
  label: { type: String, required: true },
  // Одна валюта на график. Складывать и пересчитывать валюты запрещено,
  // поэтому график всегда строится внутри одной.
  currency: { type: String, default: 'RUR' },
  // Вилка вокруг линии: нижний и верхний квартиль по периодам. Одна
  // линия медианы не говорит, сошлись ли предложения к этой сумме или
  // разбросаны вдвое в обе стороны.
  low: { type: Array, default: null },
  high: { type: Array, default: null },
  // Несколько рядов вместо одного: [{ label, values, samples }]. Вилки
  // при этом не рисуются — четыре полосы друг на друге не читаются.
  series: { type: Array, default: null },
  // Столбики объёма под линией: сколько вакансий стоит за точкой. В
  // подсказке объём виден по одной точке, столбиками — по всему ряду
  // сразу.
  volumes: { type: Array, default: null },
  // Последний период ещё идёт — отмечается маркером.
  openLast: { type: Boolean, default: false },
  // Выбранный период. Передан — значит график выбирается нажатием.
  selectedIndex: { type: Number, default: null },
  // Полные названия периодов для подсказки, если подпись оси сокращена.
  titles: { type: Array, default: null }
})

const emit = defineEmits(['select'])

const сравнение = computed(() => Boolean(props.series?.length))
const последний = computed(() => props.labels.length - 1)

// Точка видна, если она выбрана, если это незакрытый период или если у
// неё нет соседей: одинокое значение между двумя разрывами линия не
// рисует вовсе, и неделя с данными исчезла бы с графика.
function радиус(значения) {
  return (ctx) => {
    const i = ctx.dataIndex
    if (значения[i] === null || значения[i] === undefined) return 0
    if (i === props.selectedIndex) return 5
    if (props.openLast && i === последний.value) return 4
    const слева = значения[i - 1]
    const справа = значения[i + 1]
    const один = (слева === null || слева === undefined) && (справа === null || справа === undefined)
    return один ? 3 : 0
  }
}

function цветТочки(цвет) {
  return (ctx) => {
    if (ctx.dataIndex === props.selectedIndex) return token('--c-data-1')
    if (props.openLast && ctx.dataIndex === последний.value) return markerColor()
    return цвет
  }
}

function линия(значения, объёмы, стиль, подпись) {
  return {
    роль: 'линия',
    label: подпись,
    data: значения,
    samples: объёмы,
    borderColor: стиль.color,
    borderDash: стиль.dash,
    borderWidth: 2,
    pointRadius: радиус(значения),
    pointBackgroundColor: цветТочки(стиль.color),
    pointBorderColor: token('--c-data-1'),
    pointBorderWidth: (ctx) => (props.openLast && ctx.dataIndex === последний.value ? 2 : 0),
    pointHoverRadius: 5,
    pointHoverBackgroundColor: token('--c-marker'),
    pointHoverBorderColor: token('--c-data-1'),
    pointHoverBorderWidth: 2,
    tension: 0.25,
    // Разрыв в данных остаётся разрывом: соединять его линией значит
    // рисовать значение там, где вакансий не было.
    spanGaps: false,
    order: 1
  }
}

const data = computed(() => {
  const ряды = []

  if (сравнение.value) {
    props.series.forEach((ряд, номер) => {
      ряды.push(линия(ряд.values, ряд.samples, seriesStyle(номер), ряд.label))
    })
  } else {
    if (props.low && props.high) {
      const невидимая = { borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, tension: 0.25, spanGaps: false, order: 2 }
      ряды.push({ роль: 'вилка', data: props.low, fill: false, ...невидимая })
      ряды.push({
        роль: 'вилка', data: props.high, fill: '-1',
        backgroundColor: withAlpha(token('--c-data-3'), 0.28), ...невидимая
      })
    }
    ряды.push(линия(props.values, props.samples, seriesStyle(1), 'медиана'))
  }

  if (props.volumes) {
    ряды.push({
      роль: 'объём',
      type: 'bar',
      data: props.volumes,
      yAxisID: 'объём',
      backgroundColor: token('--track-bar'),
      borderRadius: 2,
      maxBarThickness: 28,
      order: 3
    })
  }

  return { labels: props.labels, datasets: ряды }
})

const выбирается = computed(() => props.selectedIndex !== null)

function строкиПодсказки(item) {
  const i = item.dataIndex
  const сумма = money(item.parsed.y, props.currency)
  const объём = item.dataset.samples?.[i]
  if (сравнение.value) {
    return `${item.dataset.label}: ${сумма}${объём ? ` · по ${объём}` : ''}`
  }
  const строки = [`медиана ${сумма}`]
  if (props.low?.[i] != null && props.high?.[i] != null) {
    строки.push(`половина: ${money(props.low[i], props.currency)} — ${money(props.high[i], props.currency)}`)
  }
  if (объём != null) строки.push(vacanciesCount(объём))
  if (props.openLast && i === последний.value) строки.push('период не закончился')
  return строки
}

const options = computed(() => {
  const оси = baseScales()
  if (props.volumes) {
    // Столбики объёма занимают нижнюю четверть: они фон для линии, а не
    // второй график, и своей оси с числами у них нет.
    оси.объём = {
      display: false,
      beginAtZero: true,
      max: Math.max(...props.volumes.map((v) => v || 0), 1) * 4
    }
  }

  const простой = !сравнение.value && !props.low && !props.titles && !props.openLast
  return {
    interaction: { mode: 'index', intersect: false },
    scales: оси,
    onClick: (событие, элементы, chart) => {
      if (!выбирается.value) return
      const точки = chart.getElementsAtEventForMode(событие.native, 'index', { intersect: false }, true)
      if (точки.length) emit('select', точки[0].index)
    },
    onHover: (событие) => {
      if (выбирается.value && событие.native?.target) событие.native.target.style.cursor = 'pointer'
    },
    plugins: {
      tooltip: простой
        ? tooltipWithSample({ formatValue: (v) => money(v, props.currency) })
        : {
            filter: (item) => item.dataset.роль === 'линия' && item.parsed.y != null,
            callbacks: {
              title: (items) => {
                const i = items[0]?.dataIndex
                return (i != null && props.titles?.[i]) || items[0]?.label || ''
              },
              label: строкиПодсказки
            }
          }
    }
  }
})
</script>

<template>
  <BvChartCanvas type="line" :data="data" :options="options" :label="label" />
</template>
