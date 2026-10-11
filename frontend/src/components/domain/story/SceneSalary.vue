<script setup>
import { computed } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import { useScene } from '@/composables/useScene'
import { num, plural } from '@/utils/format'

// Аналитика: почему в зарплатах стоит медиана, а не средняя.
//
// Объясняется на распределении настоящих зарплат базы. Сначала обе
// величины считаются без одного процента самых высоких зарплат, затем
// этот процент возвращается — и видно, какая из двух линий уехала.
// Довод «средняя чувствительна к выбросам» здесь не утверждение, а
// наблюдение: сдвиги измерены и показаны рядом.
//
// Столбцы — вёрсткой, а не канвасом: их нужно вырастить по одному и
// провести поверх две линии, а ради трёх десятков прямоугольников
// библиотека не нужна.
const props = defineProps({
  // story['зарплаты'] из /api/system/story.
  data: { type: Object, default: null }
})

const ШАГОВ = 4 // распределение, медиана, средняя, возвращён верх
const сцена = useScene(ШАГОВ, { пауза: (номер) => (номер === 1 ? 1500 : 1300), готово: () => Boolean(props.data) })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const корзины = computed(() => props.data?.['корзины'] ?? [])
const наибольшая = computed(() => Math.max(...корзины.value, props.data?.['за_пределом'] ?? 0, 1))
const высота = (число) => `${(число / наибольшая.value) * 100}%`

const верхВозвращён = computed(() => шаг.value >= 4)

// Столбец «выше предела»: до возврата верхнего процента в нём нет тех
// зарплат, которые сцена отложила.
const заПределом = computed(() => {
  const всего = props.data?.['за_пределом'] ?? 0
  return верхВозвращён.value ? всего : Math.max(0, всего - (props.data?.['верхних'] ?? 0))
})

const медиана = computed(() => props.data?.[верхВозвращён.value ? 'медиана' : 'медиана_без_верха'] ?? 0)
const средняя = computed(() => props.data?.[верхВозвращён.value ? 'средняя' : 'средняя_без_верха'] ?? 0)
const место = (сумма) => `${Math.min(100, (сумма / (props.data?.['предел'] || 1)) * 100)}%`

const рубли = (сумма) => `${num(Math.round(сумма))} ₽`
const тысячи = (сумма) => `${Math.round(сумма / 1000)}`

// Деления оси: шесть отметок от нуля до предела.
const деления = computed(() => {
  const предел = props.data?.['предел'] ?? 0
  return [0, 1, 2, 3, 4, 5].map((i) => ({ место: `${i * 20}%`, подпись: тысячи((предел / 5) * i) }))
})

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

const подпись = computed(() => {
  const д = props.data
  if (!д) return ''
  return [
    '',
    `Зарплаты ${num(д['вакансий'])} вакансий: нижняя граница вилки в рублях. Столбец — сколько вакансий платит столько.`,
    'Медиана: половина вакансий платит меньше этой суммы, половина — больше.',
    'Средняя стоит правее: её тянет длинный хвост высоких зарплат.',
    `Вернули ${д['верхних']} самых высоких — от ${рубли(д['наименьшая_из_верхних'])} до ${рубли(д['наибольшая'])}. Средняя уехала, медиана почти на месте.`
  ][Math.min(шаг.value, ШАГОВ)]
})
</script>

<template>
  <div ref="корень" class="sal">
    <p v-if="!data" class="sal__note">Зарплат в базе слишком мало, чтобы показать распределение.</p>

    <template v-else>
      <div class="sal__chart" :class="{ 'is-grown': шаг >= 1 }">
        <div class="sal__plot">
          <div class="sal__bars" aria-hidden="true">
            <span v-for="(число, i) in корзины" :key="i" class="sal__bar" :style="{ height: высота(число), '--i': i }"></span>
          </div>

          <!-- Две линии поверх распределения. Различаются начертанием, не цветом. -->
          <span class="sal__line sal__line--median" :class="{ 'is-shown': шаг >= 2 }" :style="{ left: место(медиана) }" aria-hidden="true"></span>
          <span class="sal__line sal__line--mean" :class="{ 'is-shown': шаг >= 3 }" :style="{ left: место(средняя) }" aria-hidden="true"></span>

          <div class="sal__axis" aria-hidden="true">
            <span v-for="деление in деления" :key="деление.место" class="sal__tick" :style="{ left: деление.место }">{{ деление.подпись }}</span>
          </div>
        </div>

        <!-- Всё, что выше предела оси, — одним столбцом справа. -->
        <div class="sal__over" aria-hidden="true">
          <span class="sal__bar sal__bar--over" :class="{ 'is-back': верхВозвращён }" :style="{ height: высота(заПределом), '--i': корзины.length }"></span>
          <span class="sal__tick sal__tick--over">выше</span>
        </div>
      </div>
      <p class="sal__unit">тыс. ₽ в месяц</p>

      <dl class="sal__legend">
        <div class="sal__key" :class="{ 'is-shown': шаг >= 2 }">
          <dt><span class="sal__swatch sal__swatch--median" aria-hidden="true"></span>медиана</dt>
          <dd>{{ рубли(медиана) }}</dd>
        </div>
        <div class="sal__key" :class="{ 'is-shown': шаг >= 3 }">
          <dt><span class="sal__swatch sal__swatch--mean" aria-hidden="true"></span>средняя</dt>
          <dd>{{ рубли(средняя) }}</dd>
        </div>
      </dl>

      <p class="sal__caption" aria-live="polite">{{ подпись }}</p>

      <section class="sal__shift" :class="{ 'is-shown': верхВозвращён }">
        <h3 class="sal__title">
          На сколько сдвинули {{ data['верхних'] }} {{ plural(data['верхних'], 'вакансия', 'вакансии', 'вакансий') }}
          из {{ num(data['вакансий']) }}
        </h3>
        <BvBarList :items="сдвиги" :format="(v) => `+${рубли(v)}`" />
        <p class="sal__note">
          <template v-if="воСколько">Средняя сдвинулась в {{ воСколько }} раза сильнее медианы. </template>
          Поэтому во всех зарплатных числах продукта стоит медиана: одна вакансия с лишним нулём её не меняет.
          <template v-if="копииМеняют">
            Копии по городам считаются один раз: медиана по строкам — {{ рубли(data['медиана']) }}, по вакансиям —
            {{ рубли(data['медиана_по_вакансиям']) }}.
          </template>
        </p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.sal {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.sal__chart {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  gap: var(--s-3);
}

.sal__plot,
.sal__over {
  position: relative;
  height: 220px;
  padding-bottom: 22px;
  box-sizing: content-box;
}

.sal__bars {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  align-items: end;
  gap: 2px;
  height: 220px;
  box-shadow: inset 0 -1px 0 var(--c-border-strong);
}

.sal__bar {
  display: block;
  min-height: 1px;
  border-radius: 2px 2px 0 0;
  background: var(--c-border-strong);
  transform: scaleY(0);
  transform-origin: center bottom;
  transition: transform 520ms var(--ease-enter), height 700ms var(--ease-enter), background-color 400ms var(--ease-standard);
  transition-delay: calc(var(--i) * 28ms), 0ms, 0ms;
}

.sal__chart.is-grown .sal__bar { transform: scaleY(1); }

.sal__over {
  display: flex;
  align-items: flex-end;
  height: 220px;
  box-shadow: none;
}

.sal__bar--over {
  width: 100%;
  margin-bottom: 0;
  box-shadow: inset 0 -1px 0 var(--c-border-strong);
}

/* Возвращённый верх — тёмным: это те самые вакансии, из-за которых
   уехала средняя. */
.sal__bar--over.is-back { background: var(--c-text); }

.sal__line {
  position: absolute;
  top: 0;
  height: 220px;
  width: 0;
  opacity: 0;
  /* Переезд линии — главное событие сцены: медленно, чтобы за ним следили. */
  transition: left 1400ms var(--ease-standard), opacity var(--dur-panel) var(--ease-standard);
}

.sal__line.is-shown { opacity: 1; }
.sal__line--median { border-left: 2px solid var(--c-text); }
.sal__line--mean { border-left: 2px dashed var(--c-text); }

.sal__axis {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 18px;
}

.sal__tick {
  position: absolute;
  bottom: 0;
  transform: translateX(-50%);
  font-size: var(--t-label-alt-size);
  line-height: var(--t-label-alt-lh);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-muted);
  white-space: nowrap;
}

.sal__tick:first-child { transform: none; }
.sal__tick:last-child { transform: translateX(-100%); }
.sal__tick--over { left: 50%; bottom: -22px; transform: translateX(-50%) !important; }

.sal__unit,
.sal__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.sal__unit { margin-top: var(--s-1); }

.sal__legend {
  margin: var(--s-2) 0 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2) var(--s-8);
}

.sal__key {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
  opacity: 0.25;
  transition: opacity var(--dur-panel) var(--ease-standard);
}

.sal__key.is-shown { opacity: 1; }

.sal__key dt {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-secondary);
}

.sal__key dd {
  margin: 0;
  font-size: var(--t-h3-size);
  font-weight: var(--w-strong);
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
}

.sal__swatch {
  width: 0;
  height: 16px;
}

.sal__swatch--median { border-left: 2px solid var(--c-text); }
.sal__swatch--mean { border-left: 2px dashed var(--c-text); }

/* Высота подписи занята заранее: смена текста не двигает блок ниже. */
.sal__caption {
  min-height: calc(var(--t-body-lh) * 2);
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
  max-width: 78ch;
}

.sal__shift {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding-top: var(--s-5);
  box-shadow: inset 0 1px 0 var(--c-border);
  opacity: 0;
  transform: translateY(8px);
  transition: opacity var(--dur-enter) var(--ease-enter) 900ms, transform var(--dur-enter) var(--ease-enter) 900ms;
}

.sal__shift.is-shown { opacity: 1; transform: none; }

.sal__title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.sal__note { max-width: 78ch; }

@media (max-width: 767px) {
  .sal__plot,
  .sal__over,
  .sal__bars,
  .sal__line { height: 160px; }
  .sal__bars { gap: 1px; }
  .sal__chart { grid-template-columns: minmax(0, 1fr) 28px; gap: var(--s-2); }
  .sal__caption { min-height: calc(var(--t-body-lh) * 4); }
}

@media (prefers-reduced-motion: reduce) {
  .sal__bar,
  .sal__line,
  .sal__key,
  .sal__shift { transition: none !important; }
}
</style>
