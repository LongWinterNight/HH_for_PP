<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvChartFrame from '@/components/charts/BvChartFrame.vue'
import BvColumnChart from '@/components/charts/BvColumnChart.vue'
import BvRangeList from '@/components/charts/BvRangeList.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import BvSelect from '@/components/ui/BvSelect.vue'
import SalaryTrend from '@/components/domain/SalaryTrend.vue'
import { analytics } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { money, num, vacancies as vacanciesCount } from '@/utils/format'
import { MIN_SAMPLE } from '@/utils/dataRules'

// Окно «Распределение зарплат»: краткий ответ в сетке и разбор на месте.
//
// В сетке окно отвечает на один вопрос — как распределены зарплаты и где
// середина. «Разобрать» раскрывает его на всю ширину, не оверлеем:
// аналитику сравнивают с соседними блоками, а оверлей их закрывает.
//
// В раскрытом окне три слоя над одной выборкой:
//   срезы   — чем сузить: период, опыт, сфера, формат работы;
//   уровни  — с чем сравнить: вилки по опыту, сфере, формату, региону;
//   состав  — что внутри выбранной корзины.
// Все блоки приходят одним ответом сервера, поэтому рядом никогда не
// стоят числа разных срезов.
const props = defineProps({
  // Вид зарплат задаёт экран: «currency» — внутри валюты, «rub» — вся
  // выборка в рублёвом эквиваленте.
  basis: { type: String, default: 'currency' },
  currency: { type: String, default: 'RUB' },
  // Дата курса ЦБ для подписи рублёвого вида.
  rateDate: { type: String, default: '' }
})

const открыто = ref(false)

const период = ref('all')
const опыт = ref('')
const сфера = ref('')
const формат = ref('')
const измерение = ref('experience')
// null — корзину выбирает сервер: ту, где медиана.
const корзина = ref(null)
// Блок времени: шаг ряда и с чем сравнивать линии.
const шаг = ref('week')
const сравнение = ref('')

const периоды = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'all', label: 'Всё время' }
]

const измерения = [
  { value: 'experience', label: 'По опыту' },
  { value: 'sphere', label: 'По сфере' },
  { value: 'format', label: 'По формату' },
  { value: 'area', label: 'По региону' }
]

function параметры() {
  const запрос = {
    basis: props.basis, currency: props.currency, period: период.value, by: измерение.value, step: шаг.value
  }
  if (сравнение.value) запрос.compare = сравнение.value
  if (опыт.value) запрос.experience = опыт.value
  if (сфера.value) запрос.sphere = сфера.value
  if (формат.value) запрос.format = формат.value
  if (корзина.value !== null) запрос.bucket = корзина.value
  return запрос
}

const срез = useApi((options) => analytics.salary(параметры(), options))

onMounted(() => срез.load())

// Смена среза меняет границы корзин: номер прежней корзины значил бы
// уже другой диапазон, поэтому выбор сбрасывается к корзине с медианой.
watch([() => props.basis, () => props.currency, период, опыт, сфера, формат], () => {
  корзина.value = null
  срез.load()
})
watch([измерение, корзина, шаг, сравнение], () => срез.load())

const данные = computed(() => срез.data.value)
const валюта = computed(() => данные.value?.currency ?? props.currency)
const выборка = computed(() => данные.value?.sample ?? 0)
const числа = computed(() => данные.value?.stats ?? {})
const достаточно = computed(() => выборка.value >= MIN_SAMPLE)

// Скелетон — только пока данных нет вовсе. При смене среза прежние
// блоки остаются на месте и приглушаются: иначе вместе с графиком
// исчезали бы и сами срезы, которыми человек в этот момент управляет.
const перваяЗагрузка = computed(() => срез.loading.value && !данные.value)

const корзины = computed(() => данные.value?.histogram ?? [])
const подписиКорзин = computed(() => корзины.value.map((к) => к.label))
const высотыКорзин = computed(() => корзины.value.map((к) => к.count))
const номерМедианной = computed(() => данные.value?.median_bin ?? null)
const выбранная = computed(() => данные.value?.bucket ?? null)

const деньги = (значение) => money(значение, валюта.value)

function диапазон(к) {
  if (!к) return ''
  const последняя = к.to === null || к.to === undefined || к.label?.endsWith('+')
  return последняя ? `от ${деньги(к.from)}` : `${деньги(к.from)} — ${деньги(к.to)}`
}

function подсказкаКорзины(номер) {
  const к = корзины.value[номер]
  if (!к) return ''
  const строки = [диапазон(к), `${vacanciesCount(к.count)} · ${num(к.share)} %`]
  if (к.has_median) строки.push('здесь медиана')
  return строки
}

const вариантыКорзин = computed(() => корзины.value.map((к, номер) => ({
  value: номер,
  label: `${диапазон(к)} · ${num(к.count)}${к.has_median ? ' · медиана' : ''}`
})))

function списокСреза(ключ, пусто) {
  const пункты = (данные.value?.options?.[ключ] ?? []).map((п) => ({
    value: п.value, label: `${п.value} · ${num(п.count)}`
  }))
  return [{ value: '', label: пусто }, ...пункты]
}

const вариантыОпыта = computed(() => списокСреза('experience', 'Любой опыт'))
const вариантыСфер = computed(() => списокСреза('sphere', 'Все сферы'))
const вариантыФорматов = computed(() => списокСреза('format', 'Любой формат'))

// Применённые срезы названы чипами: по трём спискам и переключателю
// не видно с первого взгляда, что выборка уже сужена.
const чипы = computed(() => {
  const список = []
  if (период.value !== 'all') {
    список.push({ ключ: 'период', текст: периоды.find((п) => п.value === период.value)?.label, снять: () => { период.value = 'all' } })
  }
  if (опыт.value) список.push({ ключ: 'опыт', текст: опыт.value, снять: () => { опыт.value = '' } })
  if (сфера.value) список.push({ ключ: 'сфера', текст: сфера.value, снять: () => { сфера.value = '' } })
  if (формат.value) список.push({ ключ: 'формат', текст: формат.value, снять: () => { формат.value = '' } })
  return список
})

function сбросить() {
  период.value = 'all'
  опыт.value = ''
  сфера.value = ''
  формат.value = ''
}

const уровни = computed(() => данные.value?.levels ?? { items: [], hidden_small: 0, beyond: 0 })

// Нажатие на строку уровней сужает окно до этой группы: «а что внутри
// у новичков» — следующий вопрос после сравнения.
// Повторное нажатие на выбранную строку снимает срез: список — и
// сравнение, и переключатель, и выйти из выбора нужно там же, где вошёл.
const срезИзмерения = computed(() => (
  { experience: опыт, sphere: сфера, format: формат }[измерение.value] ?? null
))
const выбраннаяСтрока = computed(() => срезИзмерения.value?.value ?? '')

function сузитьДо(строка) {
  const цель = срезИзмерения.value
  if (!цель) return
  цель.value = цель.value === строка.label ? '' : строка.label
}
const уровниВыбираются = computed(() => измерение.value !== 'area')

const подписьУровней = computed(() => {
  const части = ['полоса — половина вакансий, отметка — медиана']
  if (уровни.value.hidden_small) части.push(`${num(уровни.value.hidden_small)} групп с выборкой меньше ${MIN_SAMPLE} скрыты`)
  if (уровни.value.beyond) части.push(`ещё ${num(уровни.value.beyond)} за списком`)
  return части.join(' · ')
})

const подзаголовок = computed(() => {
  if (!данные.value) return ''
  const основа = props.basis === 'rub'
    ? `Рублёвый эквивалент${props.rateDate ? ` по курсу ЦБ на ${props.rateDate}` : ''}`
    : валюта.value
  if (!открыто.value) {
    // Свёрнутое окно со срезами обязано их назвать: иначе гистограмма по
    // сорока вакансиям новичков выглядит как гистограмма всей базы.
    const срезы = чипы.value.map((ч) => ч.текст).join(', ')
    return срезы ? `${основа} · срез: ${срезы}` : `${основа}, границы корзин посчитаны по данным`
  }
  const всего = данные.value.slice_total ?? 0
  const считаем = срез.loading.value ? ' · считаем…' : ''
  return `${основа} · ${vacanciesCount(выборка.value)} с зарплатой из ${num(всего)} в срезе${считаем}`
})

const подписьМедианы = computed(() => {
  if (!числа.value.median) return ''
  return `корзина с медианой · ${деньги(числа.value.median)} · половина вакансий: ${деньги(числа.value.q1)} — ${деньги(числа.value.q3)}`
})

const пустойТекст = computed(() => {
  if (!чипы.value.length) return `Вакансий с указанной зарплатой меньше ${MIN_SAMPLE} — числа по такой выборке ничего не значат.`
  return `В этом срезе ${vacanciesCount(выборка.value)} с зарплатой — меньше ${MIN_SAMPLE}, числа по такой выборке ничего не значат. Снимите один из срезов.`
})
</script>

<template>
  <div class="sx" :class="{ 'sx--open': открыто }">
    <BvChartFrame
      title="Распределение зарплат"
      :subtitle="подзаголовок"
      :loading="перваяЗагрузка"
      :error="данные ? '' : срез.error.value"
      :sample="открыто || !данные ? null : выборка"
      :height="260"
      @retry="срез.load()"
    >
      <template #actions>
        <BvButton
          size="sm"
          :aria-expanded="открыто"
          data-print-hide
          @click="открыто = !открыто"
        >{{ открыто ? 'Свернуть' : 'Разобрать' }}</BvButton>
      </template>

      <div class="sx__body" :class="{ 'is-busy': срез.loading.value }" :aria-busy="срез.loading.value">
        <div v-if="открыто" class="sx__filters" data-print-hide>
          <BvSegmented v-model="период" :options="периоды" label="Период публикации" />
          <BvSelect v-model="опыт" label="Опыт" :options="вариантыОпыта" />
          <BvSelect v-model="сфера" label="Сфера" :options="вариантыСфер" />
          <BvSelect v-model="формат" label="Формат работы" :options="вариантыФорматов" />
        </div>

        <div v-if="открыто && чипы.length" class="sx__chips">
          <BvChip
            v-for="чип in чипы"
            :key="чип.ключ"
            variant="filter"
            removable
            :remove-label="`Снять срез «${чип.текст}»`"
            @remove="чип.снять()"
          >{{ чип.текст }}</BvChip>
          <BvButton variant="quiet" size="sm" data-print-hide @click="сбросить">Сбросить срезы</BvButton>
        </div>

        <template v-if="достаточно">
          <div class="sx__chart">
            <BvColumnChart
              :labels="подписиКорзин"
              :values="высотыКорзин"
              :marker-index="номерМедианной"
              :selected-index="открыто ? (выбранная?.index ?? null) : null"
              :tooltip-lines="подсказкаКорзины"
              :label="`Распределение зарплат, ${валюта}. ${подписьМедианы}`"
              @select="корзина = $event"
            />
          </div>
          <p class="sx__median">
            <span class="sx__marker" aria-hidden="true"></span>{{ подписьМедианы }}
          </p>

          <div v-if="открыто" class="sx__blocks">
            <section class="sx__block">
              <header class="sx__block-head">
                <h4 class="sx__block-title">Зарплатные уровни</h4>
                <BvSegmented v-model="измерение" :options="измерения" label="Разбить по" data-print-hide />
              </header>
              <BvRangeList
                v-if="уровни.items.length"
                :items="уровни.items"
                :format="деньги"
                :selectable="уровниВыбираются"
                :selected="выбраннаяСтрока"
                @select="сузитьДо"
              />
              <p v-else class="sx__note">В этом срезе нет групп, где набралось бы {{ MIN_SAMPLE }} вакансий с зарплатой.</p>
              <p class="sx__note">
                {{ подписьУровней }}<template v-if="уровниВыбираются && уровни.items.length"> · {{ выбраннаяСтрока ? 'окно сужено до выбранной строки — нажмите на неё ещё раз, чтобы вернуть всё' : 'нажмите на строку, чтобы сузить окно до неё' }}</template>
              </p>
            </section>

            <section v-if="выбранная" class="sx__block">
              <header class="sx__block-head">
                <h4 class="sx__block-title">В корзине {{ диапазон(выбранная) }}</h4>
                <BvSelect
                  :model-value="выбранная.index"
                  label="Корзина"
                  hide-label
                  :options="вариантыКорзин"
                  data-print-hide
                  @update:model-value="корзина = Number($event)"
                />
              </header>
              <p class="sx__note">
                {{ vacanciesCount(выбранная.count) }} · {{ num(выбранная.share) }} % среза.
                Корзину можно выбрать и нажатием на столбец.
              </p>
              <div class="sx__parts">
                <div class="sx__part">
                  <span class="label">Сферы</span>
                  <BvBarList :items="выбранная.sphere" :total="выбранная.count" />
                </div>
                <div class="sx__part">
                  <span class="label">Опыт</span>
                  <BvBarList :items="выбранная.experience" :total="выбранная.count" />
                </div>
                <div class="sx__part">
                  <span class="label">Формат работы</span>
                  <BvBarList :items="выбранная.format" :total="выбранная.count" />
                </div>
                <div class="sx__part">
                  <span class="label">Навыки</span>
                  <BvBarList v-if="выбранная.skills.length" :items="выбранная.skills" :total="выбранная.count" />
                  <p v-else class="sx__note">У вакансий этой корзины навыки не распознаны.</p>
                </div>
              </div>
            </section>

            <SalaryTrend
              v-model:step="шаг"
              v-model:compare="сравнение"
              class="sx__block--wide"
              :trend="данные?.trend ?? null"
              :currency="валюта"
            />
          </div>
        </template>

        <div v-else-if="данные" class="sx__empty">
          <p class="sx__empty-dash" aria-hidden="true">—</p>
          <p class="sx__note">{{ пустойТекст }}</p>
          <BvButton v-if="чипы.length" size="md" @click="сбросить">Сбросить срезы</BvButton>
        </div>
      </div>
    </BvChartFrame>
  </div>
</template>

<style scoped>
.sx { min-width: 0; }

/* Раскрытое окно занимает всю ширину сетки экрана: блоки разбора не
   помещаются в одну колонку, а соседние окна остаются на месте ниже. */
.sx--open { grid-column: 1 / -1; }

.sx__body {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
  transition: opacity var(--dur-fast, 120ms) ease;
}

/* Пока сервер считает новый срез, прежние числа приглушены: они уже не
   отвечают выбранным срезам, но убрать их значило бы дёрнуть страницу. */
.sx__body.is-busy { opacity: 0.55; }

.sx__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--s-3);
}

.sx__filters > * { min-width: 0; max-width: 100%; }

.sx__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.sx__chart {
  position: relative;
  height: 240px;
  min-width: 0;
}

.sx__chart--low { height: 200px; }

.sx__median,
.sx__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.sx__median {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  color: var(--c-text-secondary);
}

/* Тот же жёлтый, что на столбце: подпись объясняет маркер, а не
   заводит второй. */
.sx__marker {
  flex: 0 0 auto;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  background: var(--c-marker);
  transform: translateY(1px);
}

.sx__blocks {
  display: grid;
  /* Две колонки, а не «сколько влезет»: при трёх третья оставалась
     пустой, а полосы вилок сжимались до неразличимых. */
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--s-6) var(--s-8, 48px);
  padding-top: var(--s-4);
  box-shadow: inset 0 1px 0 var(--c-border);
}

.sx__block {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
}

.sx__block--wide { grid-column: 1 / -1; }

.sx__block-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  min-width: 0;
}

.sx__block-head > * { min-width: 0; max-width: 100%; }

.sx__block-title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.sx__parts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr));
  gap: var(--s-4) var(--s-6);
}

.sx__part {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.sx__empty {
  min-height: 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  text-align: center;
}

.sx__empty-dash {
  font-size: var(--t-metric-size);
  line-height: var(--t-metric-lh);
  font-weight: var(--w-strong);
  color: var(--c-text-quiet);
}

@media (max-width: 960px) {
  .sx__blocks { grid-template-columns: minmax(0, 1fr); }
}

@media (prefers-reduced-motion: reduce) {
  .sx__body { transition: none; }
}
</style>
