<script setup>
import { computed } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvChartFrame from '@/components/charts/BvChartFrame.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvKpiTile from '@/components/ui/BvKpiTile.vue'
import { useCount } from '@/composables/useCount'
import { useScene } from '@/composables/useScene'
import { num, plural } from '@/utils/format'

// Аналитика: почему в зарплатах стоит медиана, а не средняя.
//
// Гистограмма — та же, что в «Графиках»: столбцы шкалы величин, корзина
// с медианой отмечена маркером. Средняя в продукте не показывается
// вовсе; здесь она нарисована один раз — чтобы показать, почему.
// Сначала обе величины считаются без одного процента самых высоких
// зарплат, затем процент возвращается, и видно, какая из двух уехала.
// Сдвиги измерены и стоят рядом полосами.
const props = defineProps({
  // story['зарплаты'] из /api/system/story.
  data: { type: Object, default: null }
})

const ШАГОВ = 4 // распределение, медиана, средняя, возвращён верх
const сцена = useScene(ШАГОВ, { пауза: 1100, готово: () => Boolean(props.data) })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const верхВозвращён = computed(() => шаг.value >= 4)
const медиана = computed(() => props.data?.[верхВозвращён.value ? 'медиана' : 'медиана_без_верха'] ?? 0)
const средняя = computed(() => props.data?.[верхВозвращён.value ? 'средняя' : 'средняя_без_верха'] ?? 0)

// Столбец «выше предела»: до возврата верхнего процента в нём нет тех
// зарплат, которые сцена отложила.
const заПределом = computed(() => {
  const всего = props.data?.['за_пределом'] ?? 0
  return верхВозвращён.value ? всего : Math.max(0, всего - (props.data?.['верхних'] ?? 0))
})

const столбцы = computed(() => {
  const д = props.data
  if (!д) return []
  const наибольшая = Math.max(...д['корзины'], д['за_пределом'], 1)
  const сМедианой = Math.min(д['корзины'].length - 1, Math.floor(медиана.value / д['шаг']))
  return [
    ...д['корзины'].map((число, i) => ({
      число,
      высота: `${(число / наибольшая) * 100}%`,
      подпись: `${Math.round((д['шаг'] * i) / 1000)}`,
      медиана: шаг.value >= 2 && i === сМедианой
    })),
    { число: заПределом.value, высота: `${(заПределом.value / наибольшая) * 100}%`, подпись: `${Math.round(д['предел'] / 1000)}+`, медиана: false }
  ]
})

// Место средней на оси: ось делят корзины и ещё один столбец «выше».
const местоСредней = computed(() => {
  const д = props.data
  if (!д) return '0%'
  const доляОси = д['корзины'].length / (д['корзины'].length + 1)
  return `${Math.min(1, средняя.value / д['предел']) * доляОси * 100}%`
})

const рубли = (сумма) => `${num(Math.round(сумма))} ₽`

const числоМедианы = useCount(() => Math.round(медиана.value), () => шаг.value >= 2)
const числоСредней = useCount(() => Math.round(средняя.value), () => шаг.value >= 3)

const сдвиги = computed(() => {
  const д = props.data
  if (!д) return []
  return [
    { label: 'средняя', value: Math.round(д['средняя'] - д['средняя_без_верха']) },
    { label: 'медиана', value: Math.round(д['медиана'] - д['медиана_без_верха']) }
  ]
})

const воСколько = computed(() => {
  const [средняя_, медиана_] = сдвиги.value
  if (!медиана_?.value || !средняя_?.value) return ''
  return (средняя_.value / медиана_.value).toFixed(1).replace('.', ',')
})

const копииМеняют = computed(() => {
  const д = props.data
  return д?.['медиана_по_вакансиям'] != null && Math.round(д['медиана_по_вакансиям']) !== Math.round(д['медиана'])
})
</script>

<template>
  <div ref="корень" class="st-stack">
    <p v-if="!data" class="st-note">Зарплат в базе слишком мало, чтобы показать распределение.</p>

    <template v-else>
      <div class="st-grid st-grid--wide st-grid--stretch">
        <BvChartFrame title="Зарплаты" subtitle="нижняя граница вилки, тыс. ₽ в месяц" :sample="data['вакансий']" :height="260">
          <template #actions>
            <span class="sal__legend" aria-hidden="true">
              <span class="sal__key"><span class="sal__swatch sal__swatch--median"></span>медиана</span>
              <span class="sal__key"><span class="sal__swatch sal__swatch--mean"></span>средняя</span>
            </span>
          </template>

          <div class="sal__plot" :class="{ 'is-on': шаг >= 1 }" role="img" :aria-label="`Распределение зарплат: медиана ${рубли(data['медиана'])}, средняя ${рубли(data['средняя'])}`">
            <!-- Сетка только горизонтальная: вертикальные линии спорят со столбцами. -->
            <span v-for="линия in 4" :key="линия" class="sal__grid" :style="{ bottom: `calc(24px + (100% - 24px) * ${линия / 4})` }"></span>

            <div class="sal__bars">
              <div v-for="(столбец, i) in столбцы" :key="i" class="sal__col" :style="{ '--i': i }">
                <span class="sal__bar-wrap">
                  <span
                    class="sal__bar"
                    :class="{ 'is-median': столбец.медиана, 'is-over': i === столбцы.length - 1 && верхВозвращён }"
                    :style="{ height: столбец.высота }"
                  ></span>
                </span>
                <span class="sal__tick">{{ столбец.подпись }}</span>
              </div>
            </div>

            <!-- Средняя: в продукте её нет, здесь — одна линия, чтобы показать почему. -->
            <span class="sal__mean" :class="{ 'is-on': шаг >= 3 }" :style="{ left: местоСредней }"></span>
          </div>
        </BvChartFrame>

        <div class="st-stack" aria-live="polite">
          <BvKpiTile
          no-trend
            label="Медиана · RUB"
            :value="числоМедианы === null ? null : рубли(числоМедианы)"
            note="половина вакансий платит меньше, половина — больше"
          />
          <BvKpiTile
          no-trend
            label="Средняя · RUB"
            :value="числоСредней === null ? null : рубли(числоСредней)"
            note="в продукте не показывается: её тянут выбросы"
          />
        </div>
      </div>

      <BvCard
        :title="`Что сделали ${data['верхних']} ${plural(data['верхних'], 'вакансия', 'вакансии', 'вакансий')} из ${num(data['вакансий'])}`"
        class="st-in"
        :class="{ 'is-on': верхВозвращён }"
      >
        <template #actions>
          <span class="st-scope">зарплаты от {{ рубли(data['наименьшая_из_верхних']) }} до {{ рубли(data['наибольшая']) }}</span>
        </template>
        <BvBarList :items="сдвиги" :format="(v) => `+${рубли(v)}`" />
        <p class="st-note">
          Сначала обе величины посчитаны без одного процента самых высоких зарплат, затем он возвращён.
          <template v-if="воСколько">Средняя сдвинулась в {{ воСколько }} раза сильнее медианы. </template>
          Поэтому во всех зарплатных числах продукта стоит медиана: одна вакансия с лишним нулём её не меняет.
          <template v-if="копииМеняют">
            Копии по городам считаются один раз: медиана по строкам — {{ рубли(data['медиана']) }}, по вакансиям —
            {{ рубли(data['медиана_по_вакансиям']) }}.
          </template>
        </p>
      </BvCard>
    </template>
  </div>
</template>

<style scoped>
.sal__legend {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--s-2) var(--s-4);
  font-size: var(--t-caption-size);
  color: var(--c-text-secondary);
}

.sal__key {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
}

.sal__swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

/* Маркер — одно значение на график: медиана. */
.sal__swatch--median { background: var(--c-marker); }
.sal__swatch--mean {
  width: 0;
  height: 12px;
  border-radius: 0;
  border-left: 2px dashed var(--c-text);
}

.sal__plot {
  position: relative;
  flex: 1 1 auto;
  min-height: 260px;
}

.sal__grid {
  position: absolute;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--c-border);
}

.sal__bars {
  position: absolute;
  inset: 0;
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  gap: var(--s-1);
}

.sal__col {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.sal__bar-wrap {
  flex: 1 1 auto;
  display: flex;
  align-items: flex-end;
  box-shadow: inset 0 -1px 0 var(--c-border-strong);
}

.sal__bar {
  display: block;
  width: 100%;
  min-height: 1px;
  border-radius: var(--r-xs) var(--r-xs) 0 0;
  background: var(--c-data-2);
  transform: scaleY(0);
  transform-origin: center bottom;
  transition: transform var(--dur-enter) var(--ease-enter), height var(--dur-enter) var(--ease-enter),
    background-color var(--dur-panel) var(--ease-standard);
  transition-delay: calc(var(--i) * 24ms), 0ms, 0ms;
}

.sal__plot.is-on .sal__bar { transform: scaleY(1); }
.sal__bar.is-median { background: var(--c-marker); }
/* Возвращённый верх — темнейшей ступенью: из-за него уехала средняя. */
.sal__bar.is-over { background: var(--c-data-1); }

.sal__tick {
  flex: 0 0 24px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  font-size: var(--t-label-alt-size);
  line-height: var(--t-label-alt-lh);
  color: var(--c-text-muted);
  white-space: nowrap;
}

.sal__mean {
  position: absolute;
  top: 0;
  bottom: 24px;
  width: 0;
  border-left: 2px dashed var(--c-text);
  opacity: 0;
  transition: left var(--dur-enter) var(--ease-standard), opacity var(--dur-panel) var(--ease-standard);
}

.sal__mean.is-on { opacity: 1; }

@media (max-width: 767px) {
  .sal__bars { gap: 2px; }
  /* Подписи оси через одну: все четырнадцать в 390 не помещаются. */
  .sal__col:nth-child(even) .sal__tick { visibility: hidden; }
  .sal__col:last-child .sal__tick { visibility: visible; }
}

@media (prefers-reduced-motion: reduce) {
  .sal__bar,
  .sal__mean { transition: none; }
}
</style>
