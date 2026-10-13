<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import BvChartFrame from '@/components/charts/BvChartFrame.vue'
import BvRangeList from '@/components/charts/BvRangeList.vue'
import BvStackedBar from '@/components/charts/BvStackedBar.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import { analytics } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { money, num } from '@/utils/format'
import { MIN_SAMPLE } from '@/utils/dataRules'

// Окно «Требуемый опыт»: сколько платят на каждом уровне и сколько таких
// вакансий.
//
// Раньше окон было два. «Требуемый опыт» показывало доли, а карточка
// «Что известно о зарплатах» — одну медиану на всю выборку, ту же, что
// подписана под гистограммой. Теперь окно одно, по образцу «Регионов»:
// переключатель «Зарплата / Вакансии» выбирает, что показано по уровням.
// Числа прежней карточки стоят первой строкой «Вся выборка» — с ней
// уровни и сравниваются.
const props = defineProps({
  basis: { type: String, default: 'currency' },
  currency: { type: String, default: 'RUB' },
  rateDate: { type: String, default: '' },
  // Число вакансий по уровням опыта: [{ label, value }]. Считает экран —
  // оно не зависит от валюты и уже пришло с его общим ответом.
  counts: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  countsLoading: { type: Boolean, default: false },
  countsError: { type: String, default: '' }
})

defineEmits(['retry'])

const показатель = ref('salary')
const показатели = [
  { value: 'salary', label: 'Зарплата' },
  { value: 'count', label: 'Вакансии' }
]

// Тот же ответ, что у окна «Распределение зарплат» без срезов: сервер
// держит его в памяти, и второй запрос расчёта не запускает.
const срез = useApi((options) => analytics.salary(
  { basis: props.basis, currency: props.currency, period: 'all', by: 'experience', step: 'week' }, options
))

onMounted(() => срез.load())
watch([() => props.basis, () => props.currency], () => срез.load())

const данные = computed(() => срез.data.value)
const валюта = computed(() => данные.value?.currency ?? props.currency)
const деньги = (значение) => money(значение, валюта.value)
const числа = computed(() => данные.value?.stats ?? {})
const выборка = computed(() => данные.value?.sample ?? 0)

const вилки = computed(() => {
  const уровни = данные.value?.levels?.items ?? []
  if (!числа.value.median) return уровни
  return [
    { label: 'Вся выборка', q1: числа.value.q1, median: числа.value.median, q3: числа.value.q3, sample: выборка.value, weak: false },
    ...уровни
  ]
})

const поЗарплате = computed(() => показатель.value === 'salary')

const основа = computed(() => (
  props.basis === 'rub' ? `Рублёвый эквивалент${props.rateDate ? ` по курсу ЦБ на ${props.rateDate}` : ''}` : валюта.value
))

const подзаголовок = computed(() => (
  поЗарплате.value ? `${основа.value} · медиана и половина вакансий по уровням опыта` : 'доли целого'
))

const пустойТекст = computed(() => (
  поЗарплате.value
    ? `Вакансий с указанной зарплатой меньше ${MIN_SAMPLE} — числа по такой выборке ничего не значат.`
    : 'В базе пока нет вакансий. Соберите данные.'
))
</script>

<template>
  <BvChartFrame
    title="Требуемый опыт"
    :subtitle="подзаголовок"
    :loading="поЗарплате ? (срез.loading.value && !данные) : countsLoading"
    :error="поЗарплате ? (данные ? '' : срез.error.value) : countsError"
    :sample="поЗарплате ? (данные ? выборка : null) : (total || null)"
    :height="220"
    :empty-text="пустойТекст"
    @retry="поЗарплате ? срез.load() : $emit('retry')"
  >
    <div class="ex">
      <BvSegmented v-model="показатель" :options="показатели" label="Что показывать по опыту" data-print-hide />
      <template v-if="поЗарплате">
        <BvRangeList :items="вилки" :format="деньги" />
        <!-- Оговорка о средней стояла в карточке «Что известно о
             зарплатах» и переехала сюда вместе с её числами. -->
        <p class="ex__note">
          полоса — половина вакансий, отметка — медиана, «по N» — вакансий с зарплатой ·
          средняя не показывается: её тянут выбросы
        </p>
      </template>
      <BvStackedBar v-else :items="counts" />
    </div>
  </BvChartFrame>
</template>

<style scoped>
.ex {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-4);
  min-width: 0;
}

.ex > :not(.seg) { align-self: stretch; }

.ex__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}
</style>
