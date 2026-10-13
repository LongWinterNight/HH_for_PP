<script setup>
import { computed, ref, watch } from 'vue'
import BvLineChart from '@/components/charts/BvLineChart.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import BvSelect from '@/components/ui/BvSelect.vue'
import { seriesStyle } from '@/utils/chartTheme'
import { money, num, vacancies as vacanciesCount } from '@/utils/format'
import { MIN_SAMPLE } from '@/utils/dataRules'

// Блок времени: как менялась зарплата в срезе.
//
// Одной линии через три точки мало — по ней не видно ни разброса, ни
// того, сколько вакансий стоит за точкой. Здесь линия идёт с вилкой
// (где лежит половина предложений) и со столбиками объёма, период
// выбирается, а вместо одной линии можно поставить несколько — по
// опыту, формату или сфере.
//
// Блок ничего не считает сам: ряд приходит с сервера тем же ответом,
// что и остальные блоки окна, и описывает ту же выборку.
const props = defineProps({
  // { step, periods: [{ key, label, title, sample, median, q1, q3, open }],
  //   series: [{ label, sample, points: [{ sample, median }] }], change }
  trend: { type: Object, default: null },
  currency: { type: String, default: 'RUB' },
  step: { type: String, default: 'week' },
  compare: { type: String, default: '' }
})

defineEmits(['update:step', 'update:compare'])

const шаги = [
  { value: 'week', label: 'По неделям' },
  { value: 'month', label: 'По месяцам' }
]

const сравнения = [
  { value: '', label: 'Без сравнения' },
  { value: 'experience', label: 'Сравнить по опыту' },
  { value: 'format', label: 'Сравнить по формату' },
  { value: 'sphere', label: 'Сравнить по сфере' }
]

const периоды = computed(() => props.trend?.periods ?? [])
const ряды = computed(() => props.trend?.series ?? [])
const сравниваем = computed(() => ряды.value.length > 0)
const естьЧисла = computed(() => периоды.value.some((п) => п.median !== null))
const словоПериода = computed(() => (props.trend?.step === 'month' ? 'месяц' : 'неделя'))

const деньги = (значение) => money(значение, props.currency)

// Выбранный период. По умолчанию — последний закрытый с числом: он и
// свежий, и полный. Незакрытый выбрать можно, но открывать блок с
// неполной недели значило бы начинать с самого ненадёжного числа.
const ключ = ref('')

function поУмолчанию() {
  const закрытые = периоды.value.filter((п) => !п.open && п.median !== null)
  const запасной = периоды.value.filter((п) => п.median !== null)
  return (закрытые.at(-1) ?? запасной.at(-1) ?? периоды.value.at(-1))?.key ?? ''
}

watch(периоды, (список) => {
  if (!список.some((п) => п.key === ключ.value)) ключ.value = поУмолчанию()
}, { immediate: true })

const номер = computed(() => периоды.value.findIndex((п) => п.key === ключ.value))
const выбранный = computed(() => периоды.value[номер.value] ?? null)

// С чем сравнивать выбранный период: ближайший предыдущий, где есть
// число. Период с тремя вакансиями между ними не в счёт.
const предыдущий = computed(() => {
  for (let i = номер.value - 1; i >= 0; i -= 1) {
    if (периоды.value[i].median !== null) return периоды.value[i]
  }
  return null
})

function процент(было, стало) {
  if (!было || стало === null || стало === undefined) return null
  return Math.round((стало / было - 1) * 1000) / 10
}

function словамиИзменение(доля) {
  if (доля === null) return ''
  if (Math.abs(доля) < 0.05) return 'без изменений'
  const знак = доля > 0 ? '+' : '−'
  return `${знак}${num(Math.abs(доля))} %`
}

const кПредыдущему = computed(() => {
  if (!выбранный.value || выбранный.value.median === null || !предыдущий.value) return null
  return {
    доля: процент(предыдущий.value.median, выбранный.value.median),
    период: предыдущий.value.title
  }
})

const вариантыПериодов = computed(() => периоды.value.map((п) => ({
  value: п.key,
  label: `${п.title} · ${num(п.sample)}${п.open ? ' · не закончился' : ''}`
})))

// Итог одной фразой — то, что человек иначе высчитывал бы по оси.
const итог = computed(() => {
  const и = props.trend?.change
  if (!и || сравниваем.value) return ''
  const слово = Math.abs(и.percent) < 0.05
    ? 'не изменилась'
    : (и.percent > 0 ? `выросла на ${num(Math.abs(и.percent))} %` : `снизилась на ${num(Math.abs(и.percent))} %`)
  return `С ${и.from.split(' — ')[0]} по ${и.to.split(' — ').at(-1)} медиана ${слово}: ${деньги(и.from_median)} → ${деньги(и.to_median)}`
})

const открытый = computed(() => периоды.value.find((п) => п.open) ?? null)

const рядыГрафика = computed(() => ряды.value.map((ряд) => ({
  label: ряд.label,
  values: ряд.points.map((т) => т.median),
  samples: ряд.points.map((т) => т.sample)
})))

// Подписи рядов стоят рядом с графиком, с тем же цветом и той же
// формой линии: легенды-сноски в системе нет.
const подписиРядов = computed(() => ряды.value.map((ряд, i) => {
  const стиль = seriesStyle(i)
  const точка = номер.value >= 0 ? ряд.points[номер.value] : null
  return {
    label: ряд.label,
    цвет: стиль.color,
    штрих: стиль.dash.length > 0,
    медиана: точка?.median ?? null,
    объём: точка?.sample ?? 0,
    всего: ряд.sample
  }
}))

const подписьГрафика = computed(() => (
  сравниваем.value
    ? `Медиана зарплаты во времени по группам, ${props.currency}`
    : `Медиана зарплаты во времени с вилкой, ${props.currency}. ${итог.value}`
))
</script>

<template>
  <section class="st">
    <header class="st__head">
      <h4 class="st__title">Зарплата во времени</h4>
      <div class="st__controls" data-print-hide>
        <BvSegmented
          :model-value="step"
          :options="шаги"
          label="Шаг времени"
          @update:model-value="$emit('update:step', $event)"
        />
        <BvSelect
          :model-value="compare"
          label="Сравнение"
          hide-label
          :options="сравнения"
          @update:model-value="$emit('update:compare', $event)"
        />
      </div>
    </header>

    <template v-if="естьЧисла">
      <p v-if="итог" class="st__summary">{{ итог }}</p>

      <div class="st__chart">
        <BvLineChart
          :labels="периоды.map((п) => п.label)"
          :titles="периоды.map((п) => п.title)"
          :values="периоды.map((п) => п.median)"
          :samples="периоды.map((п) => п.sample)"
          :low="сравниваем ? null : периоды.map((п) => п.q1)"
          :high="сравниваем ? null : периоды.map((п) => п.q3)"
          :series="сравниваем ? рядыГрафика : null"
          :volumes="периоды.map((п) => п.sample)"
          :open-last="Boolean(открытый)"
          :selected-index="номер"
          :currency="currency"
          :label="подписьГрафика"
          @select="ключ = периоды[$event]?.key ?? ключ"
        />
      </div>

      <div class="st__detail">
        <BvSelect v-model="ключ" label="Период" :options="вариантыПериодов" data-print-hide />

        <dl v-if="!сравниваем && выбранный" class="st__numbers">
          <div class="st__number">
            <dt class="label">Медиана</dt>
            <dd class="st__value">{{ выбранный.median === null ? 'мало данных' : деньги(выбранный.median) }}</dd>
          </div>
          <div class="st__number">
            <dt class="label">Половина вакансий</dt>
            <dd class="st__value st__value--plain">
              {{ выбранный.q1 === null ? '—' : `${деньги(выбранный.q1)} — ${деньги(выбранный.q3)}` }}
            </dd>
          </div>
          <div class="st__number">
            <dt class="label">Вакансий</dt>
            <dd class="st__value st__value--plain">{{ num(выбранный.sample) }}</dd>
          </div>
          <div class="st__number">
            <dt class="label">К предыдущему</dt>
            <dd class="st__value st__value--plain">
              {{ кПредыдущему ? словамиИзменение(кПредыдущему.доля) : '—' }}
            </dd>
            <dd v-if="кПредыдущему" class="st__note">к {{ кПредыдущему.период }}</dd>
          </div>
        </dl>

        <ul v-else-if="сравниваем" class="st__series">
          <li v-for="ряд in подписиРядов" :key="ряд.label" class="st__series-row">
            <span class="st__swatch" :class="{ 'is-dashed': ряд.штрих }" :style="{ '--цвет': ряд.цвет }" aria-hidden="true"></span>
            <span class="st__series-label">{{ ряд.label }}</span>
            <span class="st__series-value">{{ ряд.медиана === null ? 'мало данных' : деньги(ряд.медиана) }}</span>
            <span class="st__series-n">по {{ num(ряд.объём) }}</span>
          </li>
        </ul>
      </div>

      <p class="st__note">
        по дате публикации · столбики под линией — число вакансий в периоде<template
          v-if="!сравниваем"> · полоса вокруг линии — половина вакансий</template>
        · {{ словоПериода }} с выборкой меньше {{ MIN_SAMPLE }} показана разрывом<template
          v-if="открытый"> · последняя точка не закрыта: {{ vacanciesCount(открытый.sample) }} на сегодня</template>
      </p>
      <p class="st__note">
        Чем старше период, тем меньше в нём вакансий: в базе остаются только те, что были открыты
        на момент сбора. Ранние периоды описывают долго висящие вакансии, а не весь рынок того времени.
      </p>
    </template>

    <p v-else class="st__note">
      В срезе нет периода, где набралось бы {{ MIN_SAMPLE }} вакансий с зарплатой, — линию провести не по чему.
      Попробуйте шаг «По месяцам» или снимите один из срезов.
    </p>
  </section>
</template>

<style scoped>
.st {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
}

.st__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
}

.st__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-3);
  min-width: 0;
  max-width: 100%;
}

.st__controls > * { min-width: 0; max-width: 100%; }

.st__title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.st__summary {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text);
  max-width: none;
}

.st__chart {
  position: relative;
  height: 260px;
  min-width: 0;
}

.st__detail {
  display: grid;
  grid-template-columns: minmax(0, 280px) minmax(0, 1fr);
  align-items: start;
  gap: var(--s-4) var(--s-6);
}

.st__numbers {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr));
  gap: var(--s-4);
}

.st__number {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.st__number dd { margin: 0; }

.st__value {
  font-size: var(--t-h2-size);
  line-height: var(--t-h2-lh);
  font-weight: var(--w-strong);
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
}

.st__value--plain {
  font-size: var(--t-body-size);
  line-height: var(--t-h2-lh);
  font-weight: var(--w-medium);
}

.st__series {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.st__series-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto minmax(56px, auto);
  align-items: center;
  gap: var(--s-3);
  font-size: var(--t-ui-size);
}

/* Отрезок той же линии, что на графике: и цвет, и штрих. */
.st__swatch {
  height: 0;
  border-top: 2px solid var(--цвет);
}

.st__swatch.is-dashed { border-top-style: dashed; }

.st__series-label {
  color: var(--c-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.st__series-value {
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.st__series-n {
  text-align: right;
  color: var(--c-text-muted);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
}

.st__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

@media (max-width: 760px) {
  .st__detail { grid-template-columns: minmax(0, 1fr); }
}
</style>
