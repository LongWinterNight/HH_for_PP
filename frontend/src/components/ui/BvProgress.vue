<script setup>
import { computed } from 'vue'
import { num } from '@/utils/format'

// Полоса хода работ: сколько сделано, сколько осталось, что происходит
// прямо сейчас.
//
// Во время сбора пользователь в любой момент должен видеть, что
// происходит и сколько осталось. Полоса без подписи этого не сообщает,
// поэтому текущий шаг и счётчик — часть компонента, а не украшение
// рядом с ним.
const props = defineProps({
  value: { type: Number, required: true },
  max: { type: Number, default: 100 },
  // Что делается прямо сейчас: «Собираем: Data Scientist».
  current: { type: String, default: '' },
  // Правая подпись: «248 вакансий собрано».
  note: { type: String, default: '' }
})

const percent = computed(() => {
  if (!props.max) return 0
  return Math.min(100, Math.max(0, (props.value / props.max) * 100))
})
</script>

<template>
  <div class="progress">
    <div class="progress__head">
      <span class="progress__current">{{ current }}</span>
      <span class="progress__value">{{ Math.round(percent) }} %</span>
    </div>

    <div
      class="progress__track"
      role="progressbar"
      :aria-valuenow="Math.round(percent)"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="current || 'Ход сбора'"
    >
      <span class="progress__fill" :style="{ width: `${percent}%` }"></span>
    </div>

    <span v-if="note" class="progress__note">{{ note }}</span>
  </div>
</template>

<style scoped>
.progress {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.progress__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}

.progress__current {
  font-size: var(--t-ui-size);
  color: var(--c-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress__value {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
  flex: 0 0 auto;
}

/* Трек темнее холста: иначе полоса на светлом фоне теряется. */
.progress__track {
  height: var(--s-2);
  border-radius: var(--r-pill);
  background: var(--track-bar);
  overflow: hidden;
}

.progress__fill {
  display: block;
  height: 100%;
  border-radius: var(--r-pill);
  background: var(--c-accent);
  transition: width var(--dur-panel) var(--ease-standard);
}

.progress__note {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}
</style>
