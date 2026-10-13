<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import BvSelect from '@/components/ui/BvSelect.vue'
import BvTable from '@/components/ui/BvTable.vue'
import BvChartFrame from '@/components/charts/BvChartFrame.vue'
import BvPrintMeta from '@/components/ui/BvPrintMeta.vue'
import RegionExplorer from '@/components/domain/RegionExplorer.vue'
import SalaryExplorer from '@/components/domain/SalaryExplorer.vue'
import BvStackedBar from '@/components/charts/BvStackedBar.vue'
import { analytics } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { useHeaderMeta } from '@/composables/useHeaderMeta'
import { money, num, vacancies as vacanciesCount } from '@/utils/format'
import { MIN_SAMPLE } from '@/utils/dataRules'

// Аналитика: распределение зарплат, регионы, опыт и сводка по валютам.
//
// Зарплатные числа считаются либо внутри одной валюты, либо по рублёвому
// эквиваленту — и вид всегда назван. Раньше был только первый способ:
// курса на дату сбора не было, и пересчёт создал бы точность, которой
// нет. Курс ЦБ появился (К1, К2), и теперь семь гистограмм по семи
// валютам сводятся в одну, где 6 000 000 сум и 300 000 рублей стоят
// рядом как соседние величины.

const currency = ref('RUB')

// Вид, а не срез: оба набора приезжают одним ответом, переключение не
// ходит на сервер.
const salaryView = ref('currency')
const salaryViews = [
  { value: 'currency', label: 'В валюте' },
  { value: 'rub', label: 'Все валюты в рублях' }
]
const вРублях = computed(() => salaryView.value === 'rub')

const dist = useApi((options) => analytics.distribution({ currency: currency.value }, options))
// Сколько вакансий в работе — из сводки шапки: она уже загружена, и
// ради одного числа незачем запрашивать весь расчёт дашборда.
const { состояниеБазы } = useHeaderMeta()

onMounted(() => {
  dist.load()
})

watch(currency, () => dist.load())

const currencyOptions = computed(() => {
  const raw = dist.data.value?.currencies ?? {}
  return Object.entries(raw)
    .sort((a, b) => b[1] - a[1])
    .map(([code, count]) => ({ value: code, label: `${code} · ${num(count)}` }))
})

const salarySample = computed(() => (
  вРублях.value
    ? (dist.data.value?.salary_sample_rub ?? 0)
    : (dist.data.value?.salary_sample ?? 0)
))
const stats = computed(() => (
  вРублях.value
    ? (dist.data.value?.salary_stats_rub ?? null)
    : (dist.data.value?.salary_stats ?? null)
))

// Валюта, в которой подписаны числа на экране: в рублёвом виде это
// всегда рубль, каким бы ни был выбор в списке валют.
const активнаяВалюта = computed(() => (вРублях.value ? 'RUB' : currency.value))

const rateDate = computed(() => {
  const raw = dist.data.value?.rate_date
  if (!raw) return null
  return new Date(raw).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
})

// Валюты, которых нет в курсах ЦБ, эквивалента не получают. Сколько
// таких записей — говорится вслух: иначе объём выборки в рублёвом виде
// не сходится с тем, что человек видит в списке.
const безКурса = computed(() => dist.data.value?.without_rate ?? 0)

// Оговорка под заголовком зависит от вида: в валютном из выборки
// выпадают и вакансии без зарплаты, и все прочие валюты; в рублёвом —
// только те, где зарплата не указана вовсе (и валюты без курса ЦБ,
// если такие есть).
const текстОговорки = computed(() => {
  const ноль = 'Если считать их за ноль, медиана занизится вдвое.'
  if (!вРублях.value) {
    return `У ${num(withoutSalary.value)} вакансий зарплата не указана, ещё часть указана в других валютах. ${ноль}`
  }
  const курс = безКурса.value
    ? ` Ещё ${num(безКурса.value)} — в валютах, которых нет в курсах ЦБ.`
    : ''
  return `У ${num(withoutSalary.value)} вакансий зарплата не указана.${курс} ${ноль}`
})

const totalVacancies = computed(() => состояниеБазы.value?.active ?? 0)

// Доля вакансий без зарплаты — не украшение, а условие достоверности:
// все числа ниже считаются по тем, где зарплата указана.
const withoutSalary = computed(() => {
  const withSalary = Object.values(dist.data.value?.salary_stats_by_currency ?? {})
    .reduce((sum, v) => sum + (v.count || 0), 0)
  return Math.max(0, totalVacancies.value - withSalary)
})

const experience = computed(() => {
  const raw = dist.data.value?.experience
  if (!raw) return []
  return Object.entries(raw)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)
})

const currencyRows = computed(() => {
  const raw = dist.data.value?.salary_stats_by_currency ?? {}
  return Object.entries(raw)
    .map(([code, v]) => ({ code, ...v }))
    .sort((a, b) => b.count - a.count)
})
</script>

<template>
  <section class="an">
    <!-- Колонтитул печати: аналитика чаще всего и уходит на бумагу, а
         без периода и объёма выборки её числа нечем подтвердить. -->
    <BvPrintMeta
      :slice="`${num(salarySample)} вакансий с зарплатой из ${num(totalVacancies)}`"
      :filters="`валюта ${currency}`"
    />
    <header class="an__head">
      <div class="an__titles">
        <h1>Аналитика</h1>
        <p class="an__meta">
          <template v-if="dist.loading.value">Считаем…</template>
          <template v-else>
            {{ vacanciesCount(salarySample) }} с указанной зарплатой
            <template v-if="вРублях">во всех валютах</template>
            <template v-else>в {{ currency }}</template>
            из {{ num(totalVacancies) }} собранных
          </template>
        </p>
      </div>
      <div class="an__views">
        <BvSegmented
          v-model="salaryView"
          :options="salaryViews"
          label="Зарплаты"
          data-print-hide
        />
        <!-- В рублёвом виде выбор валюты ни на что не влияет: считается
             вся выборка сразу. Выключенный список честнее исчезнувшего —
             человек видит, что настройка есть и почему сейчас не нужна. -->
        <div class="an__currency">
          <BvSelect
            v-model="currency"
            label="Валюта"
            :options="currencyOptions"
            :disabled="вРублях"
          />
          <!-- Спека «Формы»: выключенное поле сопровождается
               объяснением, иначе оно читается как поломка. -->
          <span v-if="вРублях" class="an__currency-note">
            в рублёвом виде считается вся выборка
          </span>
        </div>
      </div>
    </header>

    <!-- Оговорка про вакансии без зарплаты стоит первой: без неё
         читатель решит, что числа описывают всю базу. -->
    <BvBanner
      v-if="withoutSalary > 0"
      kind="filtered"
      :title="`Зарплатные числа считаются по ${num(salarySample)} вакансиям из ${num(totalVacancies)}`"
      :text="текстОговорки"
    />

    <div class="an__grid">
      <!-- Окно раскрывается на месте: срезы, зарплатные уровни и состав
           корзины. Вид зарплат и валюту задаёт экран, остальное — окно. -->
      <SalaryExplorer :basis="salaryView" :currency="currency" :rate-date="rateDate || ''" />

      <!-- Одно окно на всю географию: зарплата и число вакансий по
           городам, а в раскрытом виде — страны, регионы и города. -->
      <RegionExplorer :basis="salaryView" :currency="currency" :rate-date="rateDate || ''" />

      <BvChartFrame
        title="Требуемый опыт"
        subtitle="доли целого"
        :loading="dist.loading.value"
        :error="dist.error.value"
        :sample="totalVacancies || null"
        :height="220"
        @retry="dist.load()"
      >
        <BvStackedBar :items="experience" />
      </BvChartFrame>

      <BvCard title="Что известно о зарплатах">
        <template #actions>
          <span class="an__scope">{{ вРублях ? 'все валюты · RUB' : currency }}</span>
        </template>

        <div v-if="stats" class="an__stats">
          <div class="an__stat">
            <span class="label">Медиана</span>
            <span class="metric">{{ money(stats.median, активнаяВалюта) }}</span>
            <span class="an__stat-note">
              половина вакансий предлагает больше, половина меньше<template
                v-if="вРублях && rateDate"> · по курсу ЦБ на {{ rateDate }}</template>
            </span>
          </div>
          <div class="an__stat">
            <span class="label">Половина вакансий</span>
            <span class="an__stat-range">{{ num(Math.round(stats.q1)) }} — {{ num(Math.round(stats.q3)) }}</span>
            <span class="an__stat-note">средняя не показывается: её тянут выбросы</span>
          </div>
        </div>

        <!-- Пока ответ не пришёл, данных не «мало» — их ещё нет. Сервер
             считает распределение секунды, и всё это время карточка
             утверждала «меньше 5 вакансий» при полутора тысячах. -->
        <p v-else-if="dist.loading.value" class="an__stat-note">Считаем…</p>

        <p v-else class="an__stat-note">
          <template v-if="вРублях">
            Вакансий с рублёвым эквивалентом меньше {{ MIN_SAMPLE }} —
          </template>
          <template v-else>
            В валюте {{ currency }} меньше {{ MIN_SAMPLE }} вакансий с указанной зарплатой —
          </template>
          числа по такой выборке ничего не значат.
        </p>
      </BvCard>
    </div>

    <BvCard title="Зарплаты по валютам">
      <BvTable label="Зарплаты по валютам">
        <thead>
          <tr>
            <th>Валюта</th>
            <th class="col-num">Медиана</th>
            <th class="col-num">Минимум</th>
            <th class="col-num">Максимум</th>
            <th class="col-num">Вакансий</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in currencyRows" :key="row.code">
            <td><span class="mono-num">{{ row.code }}</span></td>
            <td class="col-num">
              <template v-if="row.count >= MIN_SAMPLE">{{ num(Math.round(row.median)) }}</template>
              <span v-else class="an__weak">мало данных</span>
            </td>
            <td class="col-num">{{ num(Math.round(row.min)) }}</td>
            <td class="col-num">{{ num(Math.round(row.max)) }}</td>
            <td class="col-num">{{ num(row.count) }}</td>
          </tr>
        </tbody>
      </BvTable>
      <p class="an__note">
        В этой таблице валюты не складываются: каждая строка считается в своей валюте.
        Рублёвый эквивалент по курсу ЦБ включается переключателем «Все валюты в рублях»
        наверху. Минимум и максимум показаны как есть — среди них встречаются опечатки
        работодателей.
      </p>
    </BvCard>

  </section>
</template>

<style scoped>
.an {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.an__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.an__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.an__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.an__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(380px, 100%), 1fr));
  gap: var(--gap-grid);
}

.an__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(200px, 100%), 1fr));
  gap: var(--s-6);
}

.an__stat {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.an__stat-range {
  font-size: var(--t-h2-size);
  line-height: var(--t-h2-lh);
  font-weight: var(--w-strong);
  color: var(--c-text);
  white-space: nowrap;
}

.an__stat-note,
.an__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.an__currency {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.an__currency-note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

.an__views {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--s-3);
}

.an__scope {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.an__weak { color: var(--c-text-quiet); }
</style>
