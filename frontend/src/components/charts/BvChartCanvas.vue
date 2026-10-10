<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart, setupCharts } from '@/utils/chartTheme'

// Тонкая обёртка над Chart.js: создание, обновление, уничтожение.
// Ничего не решает про внешний вид — тема применена глобально в
// chartTheme.js, а конкретный график задаёт данные и оси.
//
// Существует ради одного: график, не уничтоженный при размонтировании
// компонента, продолжает держать канвас и слушателей, и на пятом
// переходе между экранами страница начинает тормозить.
const props = defineProps({
  type: { type: String, required: true },
  data: { type: Object, required: true },
  options: { type: Object, default: () => ({}) },
  // Название графика для программ чтения экрана: канвас для них пустой.
  label: { type: String, required: true }
})

const canvas = ref(null)
let chart = null

function build() {
  setupCharts()
  if (chart) chart.destroy()
  chart = new Chart(canvas.value, {
    type: props.type,
    data: props.data,
    options: props.options
  })
}

onMounted(build)

watch(() => [props.data, props.options], build, { deep: true })

onBeforeUnmount(() => {
  if (chart) chart.destroy()
  chart = null
})
</script>

<template>
  <canvas ref="canvas" role="img" :aria-label="label"></canvas>
</template>

<style scoped>
canvas {
  display: block;
  width: 100%;
  height: 100%;
  /* Chart.js пишет ширину холста прямо в атрибут style, в пикселях, и
     правило выше её не перекрывает. При сужении окна холст оставался
     прежним — 1 313 px на экране в 390 — и почти две секунды, пока
     библиотека не перерисует график, распирал всю страницу вбок. Предел
     действует поверх ширины из style: холст сжимается сразу, вместе с
     контейнером, а перерисовка догоняет. */
  max-width: 100%;
}
</style>
