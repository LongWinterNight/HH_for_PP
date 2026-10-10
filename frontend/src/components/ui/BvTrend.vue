<script setup>
import { computed } from 'vue'
import { trend as computeTrend } from '@/utils/dataRules'

// Тренд: стрелка, число и — только иногда — цвет.
//
// Цвет включается при отклонении от 10 %. Восемь цветных бейджей подряд
// превращают дашборд в светофор, где не выделено ничего, поэтому мелкие
// колебания несут только стрелку и вес.
//
// Направление читается стрелкой, а не оттенком: цвет никогда не бывает
// единственным носителем смысла.
//
// Когда сравнивать не с чем, компонент показывает прочерк и объясняет
// причину в подсказке. Ноль на этом месте означал бы «не изменилось» —
// то есть утверждение, которого у нас нет.
const props = defineProps({
  // Отклонение в процентах. null — сравнения нет.
  value: { type: Number, default: null },
  direction: { type: String, default: null },
  // Чем именно объясняется отсутствие тренда.
  unavailable: { type: String, default: '' }
})

const t = computed(() => computeTrend(props.value === null ? null : signed()))

function signed() {
  if (props.direction === 'down') return -Math.abs(props.value)
  if (props.direction === 'up') return Math.abs(props.value)
  return 0
}

const text = computed(() => {
  if (props.value === null) return '—'
  return `${t.value.arrow} ${props.value.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`
})
</script>

<template>
  <span
    class="trend"
    :class="[
      { 'is-colored': t.colored },
      t.colored ? `is-${t.direction}` : ''
    ]"
    :title="value === null ? unavailable : undefined"
  >{{ text }}</span>
</template>

<style scoped>
.trend {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  font-weight: var(--w-medium);
  color: var(--c-text-muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* Окрашивается только заметное отклонение. */
.trend.is-up { color: var(--c-status-ok-text); }
.trend.is-down { color: var(--c-status-err-text); }
</style>
