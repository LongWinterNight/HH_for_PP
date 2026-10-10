<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvKpiTile from '@/components/ui/BvKpiTile.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import BvTable from '@/components/ui/BvTable.vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvColumnChart from '@/components/charts/BvColumnChart.vue'
import OnboardingDialog from '@/components/domain/OnboardingDialog.vue'
import BvChartFrame from '@/components/charts/BvChartFrame.vue'
import { analytics, dashboard } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { useHeaderMeta } from '@/composables/useHeaderMeta'
import { money, num, timeAgo, vacancies as vacanciesCount } from '@/utils/format'
import { MIN_SAMPLE } from '@/utils/dataRules'
import { useRouter } from 'vue-router'

// Главный экран: что собрано, каков рынок по собранным данным и что
// делать дальше. Все числа приходят из API; ни одно не выводится здесь
// из другого, чтобы на экране не появилось величины, которой нет в базе.

const router = useRouter()

// Порог свежести. Рынок вакансий меняется быстро: через два дня после
// сбора числа на экране описывают уже не совсем то, что происходит
// сейчас. Значение здесь, а не в разметке, — менять придётся в одном
// месте, если срок окажется другим.
const STALE_AFTER_HOURS = 48

const period = ref('month')
const periods = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'all_time', label: 'Всё время' }
]

const skillType = ref('hard')
// Четвёртая категория стоит особняком: первые три — наша разметка по
// словарям, последняя — то, что работодатель назвал сам в поле вакансии.
// Раскладывать её по нашим категориям не по чему: три четверти этих
// навыков в словарях отсутствуют.
const skillTypes = [
  { value: 'hard', label: 'Профессиональные' },
  { value: 'soft', label: 'Личные' },
  { value: 'tools', label: 'Инструменты' },
  { value: 'employer', label: 'От работодателя' }
]

// Онбординг показывается один раз: когда база пуста и человек его ещё
// не закрывал. Решение о показе принимает дашборд — он первым узнаёт,
// что данных нет.
const onboarding = ref(false)
const ONBOARDING_KEY = 'bv.onboarding.seen'

function markOnboardingSeen() {
  try {
    localStorage.setItem(ONBOARDING_KEY, '1')
  } catch {
    // Приватный режим запрещает запись: онбординг просто покажется
    // снова, и это лучше, чем упасть на попытке запомнить.
  }
}

const kpi = useApi((options) => analytics.kpi({ period: period.value }, options))
const summary = useApi((options) => dashboard.summary(options))
const skills = useApi((options) => analytics.topSkills({ type: skillType.value, limit: 10, period: period.value }, options))

onMounted(async () => {
  kpi.load()
  skills.load()
  byMonth.load()

  const data = await summary.load()

  let seen = false
  try {
    seen = localStorage.getItem(ONBOARDING_KEY) === '1'
  } catch {
    seen = false
  }

  // Пустая база — единственное основание для онбординга: показывать его
  // поверх собранных данных значит мешать работе.
  if (!seen && data && (data.total_vacancies ?? 0) === 0) onboarding.value = true
})

watch(period, () => {
  kpi.load()
  skills.load()
})

watch(skillType, () => skills.load())

// Сводка базы — та же, что в шапке: всего вакансий и сколько скрыто
// как найденные не по запросу. Скрытое названо числом, чтобы не
// выглядело потерянным.
const { состояниеБазы } = useHeaderMeta()
const всегоВБазе = computed(() => состояниеБазы.value?.vacancies ?? 0)
const скрыто = computed(() => состояниеБазы.value?.off_query ?? 0)

const byMonth = useApi((options) => analytics.newByMonth({}, options))

// Прирост базы по месяцам. Считается по дате первой встречи: источник
// отдаёт только открытые вакансии, и ряд по дате публикации показывал бы
// вымирающий рынок — в старых месяцах остались бы одни долгожители.
const monthSeries = computed(() => byMonth.data.value?.series ?? [])
const monthLabels = computed(() => monthSeries.value.map((т) => т.label))
const monthValues = computed(() => monthSeries.value.map((т) => т.count))
const monthTotal = computed(() => byMonth.data.value?.total ?? 0)

// Последний столбец — текущий месяц, и он всегда неполный. Признак
// приходит от сервера, а не вычисляется здесь: календарь на клиенте
// может отличаться часовым поясом.
const monthOpenLast = computed(() => {
  const ряд = monthSeries.value
  return ряд.length > 0 && Boolean(ряд[ряд.length - 1].partial)
})

// Подпись говорит две вещи, без которых ряд читается неверно: по какой
// дате он построен и с какого месяца шли сборы. Ноль до первого сбора —
// это отсутствие сбора, а не отсутствие вакансий на рынке.
const monthNote = computed(() => {
  // Пока ответ не пришёл, сборов не «не было» — о них ещё неизвестно.
  // Экран открывается секунды и всё это время сообщал о пустой базе.
  if (byMonth.loading.value || !byMonth.data.value) {
    return 'по дате первой встречи в базе, не по дате публикации'
  }
  const с = byMonth.data.value?.collected_since
  const начало = с
    ? `сборы идут с ${с.split('-').reverse().join('.')}`
    : 'сборов ещё не было'
  return `по дате первой встречи в базе, не по дате публикации · ${начало}`
})

const metrics = computed(() => kpi.data.value?.metrics ?? {})
const trendNote = computed(() => kpi.data.value?.trend_unavailable || '')

// Два вида одной плитки, а не два числа рядом.
//
// «В рублях» описывает только рублёвые вакансии — треть базы в них не
// входит. «Все валюты» приводит семь валют к рублёвому эквиваленту по
// курсу ЦБ и описывает базу целиком. Числа разные (82 000 против
// 80 000), и показывать их без указания, что именно посчитано, значит
// повторить ошибку старой плитки, которая называлась «· RUB», а
// считалась по всем номиналам разом.
const salaryView = ref('rub')
const salaryViews = [
  { value: 'rub', label: 'Вакансии в рублях' },
  { value: 'all', label: 'Все валюты' }
]

// В базе есть валюты кроме рубля, если эквивалентная выборка шире
// рублёвой: иначе оба вида плитки показали бы одно и то же число.
const естьВалюты = computed(() => {
  const всего = metrics.value.median_salary_rub?.sample ?? 0
  const рубли = metrics.value.median_salary?.sample ?? 0
  return всего > рубли
})

const salaryMetric = computed(() => (
  salaryView.value === 'all' ? metrics.value.median_salary_rub : metrics.value.median_salary
))

// Объём выборки идёт рядом с каждым агрегатом: без n надёжность числа
// оценить нельзя, и читателю остаётся верить на слово.
const salarySample = computed(() => salaryMetric.value?.sample ?? 0)

const medianSalary = computed(() => {
  const m = salaryMetric.value
  if (!m || m.value === null || m.value === undefined) return null
  return money(m.value, m.currency || 'RUR')
})

const salaryLabel = computed(() => (
  salaryView.value === 'all' ? 'Медиана зарплаты · все валюты' : 'Медиана зарплаты · RUB'
))

// Дата курса стоит рядом с числом, которое им посчитано: «≈ 80 000 ₽»
// без даты ничем не подтверждено.
const rateDate = computed(() => {
  const raw = metrics.value.median_salary_rub?.rate_date
  if (!raw) return null
  return new Date(raw).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
})

const salaryNote = computed(() => {
  if (!kpi.data.value) return ''
  if (salarySample.value < MIN_SAMPLE) {
    return `мало данных: ${salarySample.value} из ${MIN_SAMPLE} нужных вакансий с зарплатой`
  }
  const объём = `по ${vacanciesCount(salarySample.value)} с указанной зарплатой`
  if (salaryView.value === 'all' && rateDate.value) {
    return `${объём} · по курсу ЦБ на ${rateDate.value}`
  }
  return объём
})

// Тренд считается только для рублёвых вакансий: снимки истории пока не
// хранят курс своего дня, и тренд по эквиваленту выдавал бы падение
// рубля за рост зарплат (К4‑4a).
const salaryTrendNote = computed(() => (
  salaryView.value === 'all'
    ? (salaryMetric.value?.trend_unavailable || trendNote.value)
    : trendNote.value
))

const lastRun = computed(() => summary.data.value?.last_updated ?? null)

// Данные устарели — состояние экрана, а не результат действия, поэтому
// сообщение живёт здесь, а не в углу с тостами, и не исчезает само.
const staleHours = computed(() => {
  if (!lastRun.value) return null
  const hours = (Date.now() - new Date(lastRun.value).getTime()) / 3600000
  return Number.isNaN(hours) ? null : hours
})

const isStale = computed(() => staleHours.value !== null && staleHours.value >= STALE_AFTER_HOURS)

const totals = computed(() => ({
  vacancies: summary.data.value?.total_vacancies ?? null
}))

// Первые пять регионов и остаток одной строкой. Без строки «Прочие»
// сумма полос не сходится с числом вакансий, и доли врут: 51 % Москвы
// считались бы от пятёрки лидеров, а не от всей базы.
const regions = computed(() => {
  const byArea = summary.data.value?.vacancies_by_area
  if (!byArea) return []

  const top = Object.entries(byArea).map(([label, value]) => ({ label, value }))
  const total = totals.value.vacancies
  const rest = total === null ? 0 : total - top.reduce((sum, r) => sum + r.value, 0)

  return rest > 0 ? [...top, { label: 'Прочие', value: rest }] : top
})

const regionTotal = computed(() => totals.value.vacancies ?? 0)

// Валюты идут отдельными строками и никогда не складываются: курс на
// дату сбора неизвестен, а сумма семи валют в одном числе — та ошибка,
// из-за которой затевалась пересборка интерфейса.
const currencies = computed(() => {
  const raw = summary.data.value?.vacancies_by_currency
  if (!raw) return []
  return Object.entries(raw)
    .map(([code, v]) => ({ code, ...v }))
    .sort((a, b) => b.sample - a.sample)
})

const recent = computed(() => summary.data.value?.recent_vacancies ?? [])

const topSkills = computed(() => {
  const list = skills.data.value?.skills ?? []
  return list.map((s) => ({ label: s.name, value: s.count }))
})
</script>

<template>
  <section class="dash">
    <header class="dash__head">
      <div class="dash__titles">
        <h1>Дашборд</h1>
        <p class="dash__meta">
          <template v-if="summary.loading.value">Данные загружаются…</template>
          <template v-else-if="totals.vacancies !== null">
            <!-- Числа названы тем, что они считают. Прежде здесь стояло
                 «3 493 вакансии в базе», а в шапке — «10 294»: одно слово
                 на два разных числа. Экран считает по активным. -->
            {{ num(totals.vacancies) }} активных<template v-if="всегоВБазе"> из {{ vacanciesCount(всегоВБазе) }} в базе</template><template
              v-if="lastRun">, последний сбор {{ timeAgo(lastRun) }}</template><template
              v-if="скрыто"> · {{ num(скрыто) }} найденных не по запросу скрыты</template>
          </template>
          <template v-else>Сбор ещё не запускался</template>
        </p>
      </div>
      <div class="dash__switches">
        <!-- Вид зарплаты — это вид, а не фильтр: он не меняет выборку и
             не уходит на сервер, оба числа приезжают одним ответом.
             Показываем переключатель, только когда в базе есть что
             пересчитывать: на чисто рублёвой базе выбирать не из чего. -->
        <BvSegmented
          v-if="естьВалюты"
          v-model="salaryView"
          :options="salaryViews"
          label="Медиана зарплаты"
          data-print-hide
        />
        <BvSegmented v-model="period" :options="periods" label="Период" data-print-hide />
      </div>
    </header>

    <BvBanner
      v-if="isStale"
      kind="info"
      :title="`Данные собраны ${timeAgo(lastRun)}`"
      text="Рынок мог измениться. Запустите сбор, чтобы обновить выборку."
    >
      <template #actions>
        <BvButton size="md" @click="router.push({ name: 'collection' })">Собрать</BvButton>
      </template>
    </BvBanner>

    <!-- Плитки KPI. Средней зарплаты среди них нет: правило системы
         допускает только медиану, потому что среднюю тянут выбросы. -->
    <div class="dash__kpi">
      <BvKpiTile
        class="dash__salary-tile"
        :label="salaryLabel"
        :value="medianSalary"
        :trend="salaryView === 'all' ? null : (metrics.median_salary?.trend_percent ?? null)"
        :trend-direction="salaryView === 'all' ? null : (metrics.median_salary?.trend_direction ?? null)"
        :trend-unavailable="salaryTrendNote"
        :note="salaryNote"
        :loading="kpi.loading.value"
      />
      <BvKpiTile
        label="Вакансий за период"
        :value="metrics.total_vacancies ? num(metrics.total_vacancies.value) : null"
        :trend="metrics.total_vacancies?.trend_percent ?? null"
        :trend-direction="metrics.total_vacancies?.trend_direction ?? null"
        :trend-unavailable="trendNote"
        note="по дате публикации вакансии"
        :loading="kpi.loading.value"
      />
      <BvKpiTile
        label="Компаний"
        :value="metrics.unique_companies ? num(metrics.unique_companies.value) : null"
        :trend="metrics.unique_companies?.trend_percent ?? null"
        :trend-direction="metrics.unique_companies?.trend_direction ?? null"
        :trend-unavailable="trendNote"
        note="с открытыми вакансиями"
        :loading="kpi.loading.value"
      />
      <BvKpiTile
        label="Регионов"
        :value="metrics.unique_regions ? num(metrics.unique_regions.value) : null"
        :trend="metrics.unique_regions?.trend_percent ?? null"
        :trend-direction="metrics.unique_regions?.trend_direction ?? null"
        :trend-unavailable="trendNote"
        note="города и области в выборке"
        :loading="kpi.loading.value"
      />
    </div>

    <!-- Почему у плиток прочерки вместо трендов — сказано прямо на
         экране, а не оставлено на догадку. -->
    <BvBanner
      v-if="trendNote"
      kind="info"
      title="Сравнение с прошлым периодом не показывается"
      :text="`${trendNote}. Тренды появятся, когда накопится история сборов.`"
    />

    <BvChartFrame
      class="dash__months"
      title="Новых вакансий в месяц"
      :subtitle="monthNote"
      :loading="byMonth.loading.value"
      :error="byMonth.error.value"
      :sample="monthTotal || null"
      :height="240"
      empty-text="Сборов ещё не было — база пуста. Запустите первый сбор, и месяцы начнут заполняться."
      @retry="byMonth.load()"
    >
      <!-- open-last штрихует последний столбец: текущий месяц ещё идёт,
           и без пометки он читается как обвал. Примитив это умеет —
           заводить своё оформление не нужно. -->
      <BvColumnChart
        :labels="monthLabels"
        :values="monthValues"
        :open-last="monthOpenLast"
        label="Новых вакансий в месяц"
      />
    </BvChartFrame>
    <!-- Оговорка стоит под графиком, а не в подзаголовке: она объясняет
         последний столбец, и читается она после того, как его увидели. -->
    <p v-if="monthTotal" class="dash__note">
      Текущий месяц ещё не кончился: его столбец ниже соседних не потому,
      что вакансий стало меньше. Пустой месяц — месяц без сбора.
    </p>

    <div class="dash__grid">
      <BvChartFrame
        title="Вакансии по регионам"
        :loading="summary.loading.value"
        :error="summary.error.value"
        :sample="regionTotal || null"
        :height="220"
        @retry="summary.load()"
      >
        <BvBarList :items="regions" :total="regionTotal" />
      </BvChartFrame>

      <BvChartFrame
        title="Топ навыков"
        :loading="skills.loading.value"
        :error="skills.error.value"
        subtitle="сколько вакансий требуют навык"
        :sample="null"
        :height="220"
        @retry="skills.load()"
      >
        <template #actions>
          <BvSegmented v-model="skillType" :options="skillTypes" label="Категория навыков" />
        </template>
        <BvBarList :items="topSkills" />
      </BvChartFrame>
    </div>

    <BvCard title="Зарплаты по валютам">
      <template #actions>
        <span class="dash__scope">по всей базе, период не применяется</span>
      </template>
      <BvTable label="Зарплаты по валютам">
        <thead>
          <tr>
            <th>Валюта</th>
            <th class="col-num">Медиана</th>
            <th class="col-num">Половина вакансий</th>
            <th class="col-num">Вакансий</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in currencies" :key="c.code">
            <td><span class="mono-num">{{ c.code }}</span></td>
            <td class="col-num">
              <template v-if="c.median_salary === null">
                <span class="dash__weak">мало данных</span>
              </template>
              <template v-else>{{ num(Math.round(c.median_salary)) }}</template>
            </td>
            <td class="col-num">
              <template v-if="c.q1_salary === null">—</template>
              <template v-else>{{ num(Math.round(c.q1_salary)) }} — {{ num(Math.round(c.q3_salary)) }}</template>
            </td>
            <td class="col-num">{{ num(c.sample) }}</td>
          </tr>
        </tbody>
      </BvTable>
      <p class="dash__note">
        В этой таблице валюты не складываются: каждая строка считается в своей валюте,
        рублёвый эквивалент включается переключателем наверху.
        Выборка меньше {{ MIN_SAMPLE }} вакансий показана пометкой вместо числа.
        «Половина вакансий» — диапазон, в который попадает средняя половина предложений;
        крайние значения не показываются, потому что среди них встречаются опечатки
        работодателей вроде «50 ₽».
      </p>
    </BvCard>

    <OnboardingDialog
      :open="onboarding"
      @close="onboarding = false; markOnboardingSeen()"
      @done="summary.load(); kpi.load(); skills.load()"
    />

    <BvCard title="Недавние вакансии">
      <template #actions>
        <span class="dash__scope">последние добавленные в базу</span>
      </template>
      <BvTable label="Недавно добавленные вакансии" sticky-first>
        <thead>
          <tr>
            <th>Вакансия</th>
            <th>Компания</th>
            <th>Регион</th>
            <th class="col-num">Зарплата</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(v, i) in recent" :key="`${v.name}-${i}`">
            <td class="dash__name"><span class="dash__name-text">{{ v.name }}</span></td>
            <td>{{ v.company }}</td>
            <td>{{ v.area }}</td>
            <td class="col-num">
              <template v-if="v.salary === null || v.salary === undefined">
                <span class="dash__weak">не указана</span>
              </template>
              <template v-else>{{ money(v.salary, v.currency) }}</template>
            </td>
          </tr>
        </tbody>
      </BvTable>
    </BvCard>
  </section>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: var(--s-8);
}

/* График во всю ширину: канвас Chart.js тянется за контейнером, и на
   широком экране он вырастал до 650 пикселей — карточка переставала
   влезать на печатную страницу и рвалась посередине. Высота задаётся
   здесь, а не в примитиве: у графиков внутри сетки колонка узкая, и
   там та же высота смотрелась бы вытянутой. */
.dash__months :deep(.chart__body) {
  height: 260px;
}

/* Подпись зарплатной плитки занимает одну строку в рублёвом виде и две
   в валютном — там добавляется дата курса. Место под вторую строку
   зарезервировано здесь, а не в самом примитиве: у остальных плиток
   подпись однострочная, и общий отступ поднял бы весь ряд впустую.
   Без резерва переключение вида дёргает всю раскладку на 20 пикселей. */
.dash__salary-tile :deep(.kpi__note) {
  min-height: calc(var(--t-caption-lh) * 2);
}

.dash__switches {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--s-3);
}

.dash__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.dash__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.dash__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.dash__kpi {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
  gap: var(--gap-grid);
}

.dash__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(380px, 100%), 1fr));
  gap: var(--gap-grid);
}

.dash__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

/* Срез блока: чем он отличается от выбранного вверху периода. */
.dash__scope {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

/* Отсутствующее значение — самой тихой ступенью: это не данные. */
.dash__weak { color: var(--c-text-quiet); }

/* Название вакансии не сжимается до колонки в три слова: на узком
   экране таблица уезжает вбок внутри своей обёртки, и это правильнее,
   чем ломать «Менеджер по подбору персонала» на четыре строки. */
/* Ограничение ширины стоит на содержимом, а не на ячейке: ячейка с
   max-width перестаёт растягиваться до своей колонки, и между ними
   остаётся полоса без фона — подсветка строки на ней рвётся. */
.dash__name {
  color: var(--c-text);
  font-weight: var(--w-medium);
  min-width: 220px;
}

.dash__name-text {
  display: inline-block;
  max-width: 380px;
}
</style>
