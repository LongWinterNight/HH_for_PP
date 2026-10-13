<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvChartFrame from '@/components/charts/BvChartFrame.vue'
import BvRangeList from '@/components/charts/BvRangeList.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvField from '@/components/ui/BvField.vue'
import BvModal from '@/components/ui/BvModal.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import { analytics } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { useWindowRoute } from '@/composables/useWindowRoute'
import { money, num, percent } from '@/utils/format'
import { MIN_SAMPLE } from '@/utils/dataRules'

// Окно «Регионы»: география зарплат и вакансий и ничего кроме неё.
//
// Раньше окон было два — «Медиана по регионам» и «Вакансии по регионам»,
// — и человек не понимал, чем они различаются. Теперь окно одно: в
// кратком виде переключатель «Зарплата / Вакансии» выбирает, что
// показывают полосы.
//
// В сетке — десять городов с наибольшей выборкой, и карточка остаётся
// такой всегда. «Разобрать» открывает окно поверх страницы (раньше
// карточка раскрывалась на месте и сдвигала соседей): три уровня
// территорий — страны, регионы, города, —
// переход от страны к её регионам и от региона к его городам, и портрет
// выбранной территории: сколько платят, сколько вакансий, какое место
// она занимает среди соседей и из чего состоит.
//
// Опыта, формата работы, сфер и времени здесь нет намеренно: у них свои
// окна, а это отвечает на вопрос «где».
//
// Все три уровня приходят одним ответом, поэтому переходы между ними не
// ждут сервера.
const props = defineProps({
  basis: { type: String, default: 'currency' },
  currency: { type: String, default: 'RUB' },
  rateDate: { type: String, default: '' }
})

const ПЕРВЫХ = 10
const ПОРЦИЯ = 15

const { open: открыто, show: открыть, hide: закрыть } = useWindowRoute('regions')
// Что показывают полосы краткого вида: медиану зарплаты или число вакансий.
const показатель = ref('salary')
const показатели = [
  { value: 'salary', label: 'Зарплата' },
  { value: 'count', label: 'Вакансии' }
]
const уровень = ref('country')
// Чем сужен список: страна — для регионов и городов, регион — для городов.
const страна = ref('')
const область = ref('')
// Выбранная территория — строка одного из трёх списков.
const выбрано = ref(null)
const поиск = ref('')
const порядок = ref('total')
const показано = ref(ПОРЦИЯ)

const уровни = [
  { value: 'country', label: 'Страны' },
  { value: 'region', label: 'Регионы' },
  { value: 'city', label: 'Города' }
]
const порядки = [
  { value: 'total', label: 'По числу вакансий' },
  { value: 'median', label: 'По медиане' }
]

const гео = useApi((options) => analytics.geo({ basis: props.basis, currency: props.currency }, options))

onMounted(() => гео.load())
watch([() => props.basis, () => props.currency], () => гео.load())
watch([уровень, страна, область, поиск, порядок], () => { показано.value = ПОРЦИЯ })

const данные = computed(() => гео.data.value)
const валюта = computed(() => данные.value?.currency ?? props.currency)
const деньги = (значение) => money(значение, валюта.value)
const страны = computed(() => данные.value?.countries ?? [])
const области = computed(() => данные.value?.regions ?? [])
const города = computed(() => данные.value?.cities ?? [])
const всего = computed(() => данные.value?.total ?? 0)
const общие = computed(() => данные.value?.overall ?? {})

// Краткий вид: города, где данных хватает, от больших выборок к малым.
const надёжныеГорода = computed(() => города.value.filter((г) => !г.weak).sort((a, b) => b.sample - a.sample))
const первые = computed(() => надёжныеГорода.value.slice(0, ПЕРВЫХ).map((г) => ({
  label: г.label, value: г.median, note: `по ${num(г.sample)}`
})))
const объёмПервых = computed(() => надёжныеГорода.value.slice(0, ПЕРВЫХ).reduce((сумма, г) => сумма + г.sample, 0))

// Краткий вид «Вакансии»: пять городов с наибольшим числом вакансий и
// остаток одной строкой — он в сравнении не участвует, но без него
// доли не складывались бы в целое.
const КРУПНЫХ = 5
const поЧислу = computed(() => {
  const крупные = города.value.slice(0, КРУПНЫХ).map((г) => ({ label: г.label, value: г.total }))
  const остаток = всего.value - крупные.reduce((сумма, г) => сумма + г.value, 0)
  return остаток > 0 ? [...крупные, { label: 'Прочие', value: остаток }] : крупные
})

const списокУровня = computed(() => {
  if (уровень.value === 'country') return страны.value
  if (уровень.value === 'region') return области.value.filter((р) => !страна.value || р.country === страна.value)
  return города.value.filter((г) => (
    (!страна.value || г.country === страна.value) && (!область.value || г.region === область.value)
  ))
})

const найденные = computed(() => {
  const запрос = поиск.value.trim().toLowerCase()
  const список = запрос ? списокУровня.value.filter((т) => т.label.toLowerCase().includes(запрос)) : [...списокУровня.value]
  if (порядок.value === 'median') {
    // Территории без числа — в конец: сортировать их по деньгам не по чему.
    список.sort((a, b) => (a.weak - b.weak) || (b.median - a.median) || a.label.localeCompare(b.label, 'ru'))
  }
  return список
})

function таЖе(а, б) {
  return Boolean(а && б) && а.label === б.label && (а.country ?? '') === (б.country ?? '') && (а.region ?? '') === (б.region ?? '')
}

const показанные = computed(() => найденные.value.slice(0, показано.value))
const ещё = computed(() => Math.max(0, найденные.value.length - показано.value))
const слабыхВСписке = computed(() => списокУровня.value.filter((т) => т.weak).length)

// Выбранная строка помечается по подписи; уровень выбранного должен
// совпадать с показанным, иначе «Москва»-город пометила бы «Москву»-регион.
const уровеньВыбранного = computed(() => {
  const в = выбрано.value
  if (!в) return ''
  if (в.region !== undefined) return 'city'
  return в.country !== undefined ? 'region' : 'country'
})
const подписьВыбранной = computed(() => (уровеньВыбранного.value === уровень.value ? выбрано.value.label : ''))

// В одну колонку портрет стоит над списком, и выбор строки менял бы
// числа за краем экрана. Поэтому там окно после выбора прокручивается к
// портрету: выбрал — увидел ответ.
const портрет = ref(null)
const ОДНА_КОЛОНКА = '(max-width: 960px)'

function выбрать(строка) {
  const полная = списокУровня.value.find((т) => т.label === строка.label) ?? строка
  выбрано.value = таЖе(выбрано.value, полная) ? null : полная
  if (выбрано.value && window.matchMedia?.(ОДНА_КОЛОНКА).matches) {
    nextTick(() => портрет.value?.scrollIntoView({ block: 'start' }))
  }
}

function кУровню(новый) {
  уровень.value = новый
  if (новый === 'country') { страна.value = ''; область.value = '' }
  if (новый === 'region') область.value = ''
}

// Переход вглубь: от страны к её регионам, от региона к его городам.
function внутрь() {
  const в = выбрано.value
  if (!в) return
  if (уровеньВыбранного.value === 'country') {
    страна.value = в.label
    область.value = ''
    уровень.value = 'region'
  } else if (уровеньВыбранного.value === 'region') {
    страна.value = в.country
    область.value = в.label
    уровень.value = 'city'
  }
  поиск.value = ''
}

function сброситьПуть() {
  страна.value = ''
  область.value = ''
  уровень.value = 'country'
}

function кСтране() {
  область.value = ''
  уровень.value = 'region'
}

// Портрет: из чего территория состоит — её части уровнем ниже.
const части = computed(() => {
  const в = выбрано.value
  if (!в) return страны.value
  if (уровеньВыбранного.value === 'country') return области.value.filter((р) => р.country === в.label)
  if (уровеньВыбранного.value === 'region') {
    return города.value.filter((г) => г.country === в.country && г.region === в.label)
  }
  return []
})
const частиПолосами = computed(() => части.value.slice(0, 6).map((ч) => ({ label: ч.label, value: ч.total })))
const названиеЧастей = computed(() => {
  if (!выбрано.value) return 'Страны'
  return уровеньВыбранного.value === 'country' ? 'Регионы внутри' : 'Города внутри'
})

function отличие(своя, чужая) {
  if (своя === null || своя === undefined || !чужая) return null
  const доля = Math.round((своя / чужая - 1) * 1000) / 10
  if (Math.abs(доля) < 0.05) return 'столько же'
  return `${доля > 0 ? '+' : '−'}${num(Math.abs(доля))} %`
}

// С чем сравнить территорию: со всей базой, со своей страной, со своим
// регионом. Сравнение с самой собой не показывается.
const сравнения = computed(() => {
  const в = выбрано.value
  if (!в || в.weak) return []
  const итог = []
  const кБазе = отличие(в.median, общие.value.median)
  if (кБазе) итог.push({ с: 'ко всей выборке', значение: кБазе, подпись: деньги(общие.value.median) })
  if (уровеньВыбранного.value !== 'country') {
    const своя = страны.value.find((с) => с.label === в.country)
    const кСтране_ = своя && !своя.weak ? отличие(в.median, своя.median) : null
    if (кСтране_) итог.push({ с: `к стране: ${своя.label}`, значение: кСтране_, подпись: деньги(своя.median) })
  }
  if (уровеньВыбранного.value === 'city' && в.region !== в.label) {
    const свой = области.value.find((р) => р.label === в.region && р.country === в.country)
    const кОбласти = свой && !свой.weak ? отличие(в.median, свой.median) : null
    if (кОбласти) итог.push({ с: `к региону: ${свой.label}`, значение: кОбласти, подпись: деньги(свой.median) })
  }
  return итог
})

// Место по медиане среди территорий того же уровня, где данных хватает.
const место = computed(() => {
  const в = выбрано.value
  if (!в || в.weak) return null
  const ровня = { country: страны.value, region: области.value, city: города.value }[уровеньВыбранного.value]
    .filter((т) => !т.weak)
    .sort((a, b) => b.median - a.median)
  const номер = ровня.findIndex((т) => таЖе(т, в))
  const слово = { country: 'стран', region: 'регионов', city: 'городов' }[уровеньВыбранного.value]
  return номер === -1 ? null : `${номер + 1}‑е из ${num(ровня.length)} ${слово}`
})

const подписьТерритории = computed(() => {
  const в = выбрано.value
  if (!в) return 'вся база'
  if (уровеньВыбранного.value === 'country') return 'страна'
  if (уровеньВыбранного.value === 'region') return `регион · ${в.country}`
  return в.region === в.label ? `город · ${в.country}` : `город · ${в.region}, ${в.country}`
})

// Почему у страны нет чисел в валютном виде — и как их получить.
const оВалюте = computed(() => {
  const в = выбрано.value
  if (!в || !в.weak || props.basis === 'rub' || уровеньВыбранного.value !== 'country') return ''
  if (!в.main_currency || в.main_currency === props.currency) return ''
  return `Здесь зарплаты чаще указаны в ${в.main_currency}, а окно сейчас считает только ${props.currency}. Чтобы сравнить страны, включите вид «Все валюты в рублях» наверху экрана.`
})

const основа = computed(() => (
  props.basis === 'rub' ? `Рублёвый эквивалент${props.rateDate ? ` по курсу ЦБ на ${props.rateDate}` : ''}` : валюта.value
))

const подзаголовокОкна = computed(() => {
  if (!данные.value) return ''
  return `${основа.value} · ${num(страны.value.length)} стран, ${num(области.value.length)} регионов, ${num(города.value.length)} городов`
})

const подзаголовок = computed(() => {
  if (!данные.value) return ''
  if (показатель.value === 'count') {
    return `пять городов с наибольшим числом вакансий и остальные · всего ${num(города.value.length)} городов в ${num(страны.value.length)} странах`
  }
  const части_ = [основа.value, 'десять городов с наибольшей выборкой']
  const слабых = города.value.length - надёжныеГорода.value.length
  if (слабых) части_.push(`${num(слабых)} городов с выборкой меньше ${MIN_SAMPLE} скрыты`)
  if (надёжныеГорода.value.length > ПЕРВЫХ) части_.push(`ещё ${num(надёжныеГорода.value.length - ПЕРВЫХ)} за десяткой`)
  return части_.join(' · ')
})

const подписьСписка = computed(() => {
  const части_ = ['полоса — половина вакансий, отметка — медиана, «по N» — вакансий с зарплатой']
  if (слабыхВСписке.value) части_.push(`у ${num(слабыхВСписке.value)} территорий вакансий с зарплатой меньше ${MIN_SAMPLE} — чисел нет`)
  return части_.join(' · ')
})

const словоУровня = computed(() => ({ country: 'страны', region: 'региона', city: 'города' }[уровень.value]))
</script>

<template>
  <div class="rx">
    <BvChartFrame
      title="Регионы"
      :subtitle="подзаголовок"
      :loading="гео.loading.value && !данные"
      :error="данные ? '' : гео.error.value"
      :sample="данные ? ((показатель === 'count' ? всего : объёмПервых) || null) : null"
      :height="260"
      empty-text="Ни в одном городе не набралось достаточно вакансий с зарплатой. Соберите больше данных."
      @retry="гео.load()"
    >
      <template #actions>
        <BvButton size="sm" aria-haspopup="dialog" data-print-hide @click="открыть">Разобрать</BvButton>
      </template>

      <!-- Краткий вид: полосы, а не кольцо — длину сравнивают точно.
           Переключатель выбирает, что они показывают. -->
      <div class="rx__brief">
        <BvSegmented v-model="показатель" :options="показатели" label="Что показывать по регионам" data-print-hide />
        <BvBarList v-if="показатель === 'salary'" :items="первые" :format="деньги" />
        <BvBarList v-else :items="поЧислу" :total="всего" />
      </div>
    </BvChartFrame>

    <!-- Разбор: окно поверх страницы. Уровень, путь и выбранная территория
         живут в компоненте, поэтому закрытие окна их не сбрасывает. -->
    <BvModal :open="открыто" size="xl" title="Регионы" :subtitle="подзаголовокОкна" @close="закрыть">
      <div class="rx__body">
        <div class="rx__cols">
          <section class="rx__block">
            <header class="rx__head">
              <BvSegmented :model-value="уровень" :options="уровни" label="Уровень территорий" data-print-hide @update:model-value="кУровню" />
              <BvSegmented v-model="порядок" :options="порядки" label="Порядок списка" data-print-hide />
            </header>

            <!-- Путь: чем сейчас сужен список и как выйти на уровень выше. -->
            <nav class="rx__path" aria-label="Путь по территориям">
              <BvButton variant="quiet" size="sm" :disabled="!страна" @click="сброситьПуть">Все страны</BvButton>
              <template v-if="страна">
                <span class="rx__sep" aria-hidden="true">›</span>
                <BvButton variant="quiet" size="sm" :disabled="!область" @click="кСтране">{{ страна }}</BvButton>
              </template>
              <template v-if="область">
                <span class="rx__sep" aria-hidden="true">›</span>
                <span class="rx__here">{{ область }}</span>
              </template>
            </nav>

            <BvField
              v-if="списокУровня.length > ПОРЦИЯ"
              v-model="поиск"
              :label="`Поиск ${словоУровня}`"
              placeholder="Название"
              data-print-hide
            />

            <BvRangeList
              v-if="показанные.length"
              :items="показанные"
              :format="деньги"
              selectable
              :selected="подписьВыбранной"
              @select="выбрать"
            />
            <p v-else class="rx__note">Территории с таким названием на этом уровне нет.</p>

            <BvButton v-if="ещё" variant="quiet" size="sm" data-print-hide @click="показано += ПОРЦИЯ">
              Показать ещё {{ Math.min(ещё, ПОРЦИЯ) }} из {{ num(ещё) }}
            </BvButton>
            <p class="rx__note">{{ подписьСписка }}</p>
          </section>

          <section ref="портрет" class="rx__block rx__block--portrait">
            <header class="rx__head">
              <div class="rx__titles">
                <h4 class="rx__title">{{ выбрано ? выбрано.label : 'Вся база' }}</h4>
                <span class="rx__kind">{{ подписьТерритории }}</span>
              </div>
              <BvButton
                v-if="выбрано && уровеньВыбранного !== 'city' && части.length"
                size="sm"
                data-print-hide
                @click="внутрь"
              >{{ уровеньВыбранного === 'country' ? 'Показать регионы' : 'Показать города' }}</BvButton>
            </header>

            <dl class="rx__numbers">
              <div class="rx__number">
                <dt class="label">Медиана</dt>
                <dd v-if="выбрано" class="rx__value">{{ выбрано.weak ? 'мало данных' : деньги(выбрано.median) }}</dd>
                <dd v-else class="rx__value">{{ общие.weak ? 'мало данных' : деньги(общие.median) }}</dd>
              </div>
              <div class="rx__number">
                <dt class="label">Половина вакансий</dt>
                <dd v-if="выбрано" class="rx__value rx__value--plain">
                  {{ выбрано.weak ? '—' : `${деньги(выбрано.q1)} — ${деньги(выбрано.q3)}` }}
                </dd>
                <dd v-else class="rx__value rx__value--plain">
                  {{ общие.weak ? '—' : `${деньги(общие.q1)} — ${деньги(общие.q3)}` }}
                </dd>
              </div>
              <div class="rx__number">
                <dt class="label">Вакансий</dt>
                <dd class="rx__value rx__value--plain">{{ num(выбрано ? выбрано.total : всего) }}</dd>
                <dd class="rx__note">с зарплатой в расчёте — {{ num(выбрано ? выбрано.sample : общие.sample) }}</dd>
              </div>
              <div v-if="выбрано" class="rx__number">
                <dt class="label">Доля базы</dt>
                <dd class="rx__value rx__value--plain">{{ percent(выбрано.total, всего) }}</dd>
                <dd class="rx__note">из {{ num(всего) }} вакансий</dd>
              </div>
              <div v-if="место" class="rx__number">
                <dt class="label">Место по медиане</dt>
                <dd class="rx__value rx__value--plain">{{ место }}</dd>
              </div>
              <div v-for="с in сравнения" :key="с.с" class="rx__number">
                <dt class="label">{{ с.с }}</dt>
                <dd class="rx__value rx__value--plain">{{ с.значение }}</dd>
                <dd class="rx__note">там {{ с.подпись }}</dd>
              </div>
            </dl>

            <p v-if="оВалюте" class="rx__note">{{ оВалюте }}</p>

            <div v-if="частиПолосами.length" class="rx__part">
              <span class="label">{{ названиеЧастей }} · по числу вакансий</span>
              <BvBarList :items="частиПолосами" :total="выбрано ? выбрано.total : всего" />
              <p v-if="части.length > частиПолосами.length" class="rx__note">
                показаны шесть крупнейших из {{ num(части.length) }}
              </p>
            </div>

            <p v-if="!выбрано" class="rx__note">
              Нажмите на строку слева, чтобы увидеть портрет территории; повторное нажатие вернёт сюда.
            </p>
          </section>
        </div>

        <p class="rx__note">
          Территория — место, указанное в вакансии: у удалённой работы это город работодателя.
          Страна и регион определены по справочнику hh.ru<template
            v-if="данные?.unknown"> · {{ num(данные.unknown) }} вакансий с местом вне справочника в счёт не вошли</template>.
          Одна вакансия, размещённая в нескольких городах, в регионе и в стране считается один раз.
        </p>
      </div>
    </BvModal>
  </div>
</template>

<style scoped>
.rx { min-width: 0; }

.rx__brief {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-4);
  min-width: 0;
}

.rx__brief > :deep(.bars) { align-self: stretch; }

.rx__body {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
}

.rx__cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--s-6) var(--s-8, 48px);
}

.rx__block {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
}

.rx__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  min-width: 0;
}

.rx__head > * { min-width: 0; max-width: 100%; }

.rx__path {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-1);
  min-width: 0;
  font-size: var(--t-caption-size);
}

.rx__sep { color: var(--c-text-quiet); }

.rx__here {
  padding: 0 var(--s-2);
  color: var(--c-text);
  font-weight: var(--w-medium);
}

.rx__titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.rx__title {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.rx__kind {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.rx__numbers {
  margin: 0;
  display: grid;
  /* Колонка шире вилки «60 000 ₽ — 100 000 ₽»: число, разорванное
     переносом, читается как два разных. */
  grid-template-columns: repeat(auto-fit, minmax(min(190px, 100%), 1fr));
  gap: var(--s-4);
}

.rx__number {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.rx__number dd { margin: 0; }

.rx__value {
  font-size: var(--t-h2-size);
  line-height: var(--t-h2-lh);
  font-weight: var(--w-strong);
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
}

.rx__value--plain {
  white-space: nowrap;
  font-size: var(--t-body-size);
  line-height: var(--t-h2-lh);
  font-weight: var(--w-medium);
}

.rx__part {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.rx__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

/* Список территорий длиннее окна, портрет — нет. Пока список
   прокручивается, портрет выбранной территории остаётся на виду: иначе
   строку выбирали бы внизу, а читать ответ возвращались наверх. */
@media (min-width: 961px) {
  .rx__block--portrait {
    position: sticky;
    top: 0;
    align-self: start;
  }
}

@media (max-width: 960px) {
  .rx__cols { grid-template-columns: minmax(0, 1fr); }

  /* В одной колонке портрет стоит первым: окно открывается с ответа, а
     после выбора строки прокручивается к нему обратно. */
  .rx__block--portrait { order: -1; }
}
</style>
