<script setup>
import BvButton from '@/components/ui/BvButton.vue'
import { sampleNote, sampleState } from '@/utils/dataRules'
import { vacancies } from '@/utils/format'
import { computed } from 'vue'

// Рамка графика: заголовок, объём выборки, четыре состояния данных.
//
// Высота фиксирована и одинакова во всех состояниях. Если график
// схлопывается на время загрузки, страница дёргается, и блоки под ним
// прыгают в момент, когда пользователь уже целится в один из них.
//
// Состояние «мало данных» существует отдельно и обязательно: показывать
// медиану по трём вакансиям без оговорки нельзя.
const props = defineProps({
  title: { type: String, required: true },
  // Подзаголовок: период, срез, единица измерения.
  subtitle: { type: String, default: '' },
  // Объём выборки. Ниже пяти график не строится вовсе.
  sample: { type: Number, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  // Не жёсткая высота, а нижняя граница: канвас графика занимает её
  // целиком, список полос может быть выше. Важно, что место под данные
  // зарезервировано во всех состояниях и страница не дёргается.
  height: { type: Number, default: 240 },
  // Текст пустого состояния: он объясняет, что сделать, а не
  // сообщает «нет данных» и умолкает.
  emptyText: {
    type: String,
    default: 'Ни одна вакансия за выбранный период не подходит под условия. Расширьте период или снимите фильтр.'
  }
})

defineEmits(['retry'])

const state = computed(() => {
  if (props.loading) return 'loading'
  if (props.error) return 'error'
  if (props.sample === null) return 'ready'
  return sampleState(props.sample) === 'insufficient' ? 'empty' : 'ready'
})

const note = computed(() => (props.sample === null ? null : sampleNote(props.sample)))
</script>

<template>
  <figure class="chart card">
    <figcaption class="chart__head">
      <div class="chart__titles">
        <h3 class="chart__title">{{ title }}</h3>
        <span v-if="subtitle" class="chart__subtitle">{{ subtitle }}</span>
      </div>
      <slot name="actions" />
    </figcaption>

    <div class="chart__body" :style="{ minHeight: `${height}px` }">
      <!-- Скелетон повторяет форму графика, а не закрывает его серым
           прямоугольником: место под данные видно заранее. -->
      <div v-if="state === 'loading'" class="chart__skeleton" role="status" aria-label="Данные загружаются">
        <span v-for="i in 7" :key="i" class="chart__skeleton-bar" :style="{ height: `${30 + ((i * 37) % 60)}%` }"></span>
      </div>

      <div v-else-if="state === 'error'" class="chart__state">
        <p class="chart__state-title">График не построен</p>
        <p class="chart__state-text">{{ error }}</p>
        <BvButton size="md" @click="$emit('retry')">Повторить</BvButton>
      </div>

      <div v-else-if="state === 'empty'" class="chart__state">
        <p class="chart__state-title chart__dash" aria-hidden="true">—</p>
        <p class="chart__state-text">{{ emptyText }}</p>
      </div>

      <slot v-else />
    </div>

    <!-- Оговорка о ненадёжной выборке стоит под графиком, а не в тултипе:
         её должно быть видно без курсора и на бумаге. -->
    <p v-if="state === 'ready' && note" class="chart__warning">
      <span class="chart__warning-mark" aria-hidden="true">!</span>{{ note }}
    </p>
    <p v-else-if="state === 'ready' && sample !== null" class="chart__sample">{{ vacancies(sample) }} в выборке</p>
  </figure>
</template>

<style scoped>
.chart {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
}

.chart__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-4);
  flex-wrap: wrap;
}

.chart__titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.chart__title {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  letter-spacing: var(--t-h3-ls);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.chart__subtitle {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

.chart__body {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* Канвас Chart.js растягивается на всю отведённую высоту, список полос
   занимает столько, сколько нужно строкам. */
.chart__body > :deep(canvas) { flex: 1 1 auto; min-height: 0; }

.chart__skeleton {
  display: flex;
  align-items: flex-end;
  gap: var(--s-2);
  height: 100%;
}

.chart__skeleton-bar {
  flex: 1 1 0;
  border-radius: var(--r-xs) var(--r-xs) 0 0;
  background: var(--track-bar);
}

.chart__state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  text-align: center;
}

.chart__state-title {
  font-size: var(--t-body-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

/* Прочерк того же кегля, что и число: место величины видно, но
   величины нет. Ноль на его месте был бы враньём. */
.chart__dash {
  font-size: var(--t-metric-size);
  line-height: var(--t-metric-lh);
  font-weight: var(--w-strong);
  color: var(--c-text-quiet);
}

.chart__state-text {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: 42ch;
}

.chart__sample,
.chart__warning {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

/* Предупреждение подаётся формой, а не цветом: жёлтый в системе занят
   ролью маркера, и второй жёлтый со смыслом «внимание» неотличим. */
.chart__warning {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--c-text-secondary);
}

.chart__warning-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  border-radius: var(--r-xs);
  box-shadow: var(--border-strong);
  font-size: var(--t-caption-size);
  font-weight: var(--w-strong);
  color: var(--c-text);
}
</style>
