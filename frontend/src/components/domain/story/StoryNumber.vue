<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { num } from '@/utils/format'

// Число, которое досчитывается до своего значения.
//
// Счёт идёт один раз, когда сцена дошла до этого числа: так видно, что
// число появилось как итог шага, а не стояло здесь с самого начала.
// Ширина знаков табличная — цифры при счёте не толкают соседний текст.
const props = defineProps({
  value: { type: Number, default: 0 },
  // Сцена дошла до числа. Пока false — на месте числа прочерк.
  active: { type: Boolean, default: true },
  format: { type: Function, default: null },
  duration: { type: Number, default: 900 }
})

const показано = ref(props.active ? props.value : null)
let кадр = null

const безДвижения = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function считать() {
  cancelAnimationFrame(кадр)
  if (!props.active) {
    показано.value = null
    return
  }
  if (безДвижения() || !props.value) {
    показано.value = props.value
    return
  }
  const начало = performance.now()
  const шаг = (сейчас) => {
    const доля = Math.min(1, (сейчас - начало) / props.duration)
    // Быстро в начале, медленно к концу: последние цифры успеваешь прочесть.
    показано.value = Math.round(props.value * (1 - Math.pow(1 - доля, 3)))
    if (доля < 1) кадр = requestAnimationFrame(шаг)
  }
  кадр = requestAnimationFrame(шаг)
}

watch(() => [props.active, props.value], считать)
onBeforeUnmount(() => cancelAnimationFrame(кадр))
</script>

<template>
  <span class="story-num">{{ показано === null ? '—' : (format ? format(показано) : num(показано)) }}</span>
</template>

<style scoped>
.story-num { font-variant-numeric: tabular-nums; }
</style>
