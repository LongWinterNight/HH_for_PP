<script setup>
import { computed } from 'vue'
import BvStackedBar from '@/components/charts/BvStackedBar.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import BvTable from '@/components/ui/BvTable.vue'
import StoryNumber from '@/components/domain/story/StoryNumber.vue'
import { useScene } from '@/composables/useScene'
import { moneyExact, num, plural, salaryPeriod } from '@/utils/format'

// Очистка: четыре правила, которые стоят между собранным и числами.
//
// У каждого правила — карточка с настоящим примером из базы и числом
// строк, которых оно касается. Правила срабатывают по очереди, и на
// примере видно, что происходит со строкой.
//
// Ни одно правило ничего не удаляет — это сказано в каждой карточке:
// без этого «очистка» читается как «потеря данных».
const props = defineProps({
  // story['очистка'] из /api/system/story.
  data: { type: Object, default: null }
})

const ШАГОВ = 4
const сцена = useScene(ШАГОВ, { пауза: 1000, готово: () => Boolean(props.data) })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const копии = computed(() => props.data?.['копии'] ?? null)
const чужие = computed(() => props.data?.['не_по_запросу'] ?? null)
const сомнительные = computed(() => props.data?.['сомнительные'] ?? null)
const снятые = computed(() => props.data?.['снятые'] ?? null)

// Название компании тремя частями: до слова запроса, само слово, после.
const компанияЧастями = computed(() => {
  const пример = чужие.value?.['пример']
  if (!пример) return null
  const где = пример['компания'].toLowerCase().indexOf(пример['запрос'].toLowerCase())
  if (где < 0) return { до: пример['компания'], слово: '', после: '' }
  const конец = где + пример['запрос'].length
  return {
    до: пример['компания'].slice(0, где),
    слово: пример['компания'].slice(где, конец),
    после: пример['компания'].slice(конец)
  }
})

function сумма(пример) {
  const части = [пример['от'], пример['до']].filter((с) => с != null).map((с) => num(Math.round(с)))
  const знак = moneyExact(0, пример['валюта'])?.replace(/^0\s*/, '') ?? пример['валюта']
  return `${части.join(' — ')} ${знак} ${salaryPeriod(пример['период']) ?? 'в месяц'}`
}

const доли = computed(() => [
  { label: 'Активные', value: снятые.value?.['активных'] ?? 0 },
  { label: 'В архиве', value: снятые.value?.['в_архиве'] ?? 0 }
])

const остатокГородов = computed(() => {
  const пример = копии.value?.['пример']
  return пример ? пример['строк'] - пример['города'].length : 0
})
</script>

<template>
  <div ref="корень">
    <p v-if="!data" class="st-note">Данные об очистке не получены.</p>

    <div v-else class="st-grid st-grid--2 st-grid--stretch">
      <!-- 1 · копии по городам -->
      <BvCard title="Копии по городам" class="st-dim" :class="{ 'is-on': шаг >= 1 }">
        <template #actions>
          <span class="st-scope">считаются один раз</span>
        </template>
        <p class="clean__figure">
          <span class="st-figure"><StoryNumber :value="копии['строк']" :active="шаг >= 1" /></span>
          <span class="st-note">{{ plural(копии['строк'], 'строка', 'строки', 'строк') }} — это</span>
          <span class="st-figure"><StoryNumber :value="копии['вакансий']" :active="шаг >= 1" /></span>
          <span class="st-note">{{ plural(копии['вакансий'], 'вакансия', 'вакансии', 'вакансий') }}</span>
        </p>

        <div v-if="копии['пример']" class="clean__example" :class="{ 'is-merged': шаг >= 1 }">
          <div class="st-vac">
            <span class="st-vac__name">{{ копии['пример']['название'] }}</span>
            <span class="st-vac__company">{{ копии['пример']['компания'] }}</span>
          </div>
          <div class="clean__cities">
            <span v-for="(город, i) in копии['пример']['города']" :key="город" class="clean__city" :style="{ '--i': i }" aria-hidden="true">
              <BvChip variant="count">{{ город }}</BvChip>
            </span>
            <span v-if="остатокГородов > 0" class="clean__city" :style="{ '--i': копии['пример']['города'].length }" aria-hidden="true">
              <BvChip variant="count">+{{ остатокГородов }}</BvChip>
            </span>
            <span class="clean__merged">
              <BvChip variant="count">
                1 вакансия · {{ копии['пример']['строк'] }} {{ plural(копии['пример']['строк'], 'город', 'города', 'городов') }}
              </BvChip>
            </span>
          </div>
        </div>

        <p class="st-note">
          Работодатель размещает одну вакансию в десятках городов. В медиане зарплаты и топе работодателей она
          считается один раз; в списке остаются все города — человеку нужна строка его города.
        </p>
      </BvCard>

      <!-- 2 · найдено не по запросу -->
      <BvCard title="Найдено не по запросу" class="st-dim" :class="{ 'is-on': шаг >= 2 }">
        <template #actions>
          <span class="st-scope">скрыты из списка и чисел</span>
        </template>
        <p class="clean__figure">
          <span class="st-figure"><StoryNumber :value="чужие['скрыто']" :active="шаг >= 2" /></span>
          <span class="st-note">{{ plural(чужие['скрыто'], 'вакансия', 'вакансии', 'вакансий') }}</span>
        </p>

        <div v-if="чужие['пример']" class="clean__example">
          <div class="clean__row">
            <div class="st-vac">
              <span class="st-vac__name">{{ чужие['пример']['название'] }}</span>
              <span class="st-vac__company">
                {{ компанияЧастями.до }}<mark class="st-hit" :class="{ 'is-on': шаг >= 2 }">{{ компанияЧастями.слово }}</mark>{{ компанияЧастями.после }}
              </span>
            </div>
            <BvStatus :kind="шаг >= 2 ? 'stop' : 'idle'" :label="шаг >= 2 ? 'Скрыта' : 'В списке'" />
          </div>
          <span class="st-note">запрос «{{ чужие['пример']['запрос'] }}»</span>
        </div>

        <p class="st-note">
          Источник по умолчанию ищет слова запроса и в названии компании. Сбор теперь просит искать только в названии
          и описании вакансии, а собранное раньше проверяет это правило: слово есть только в названии компании —
          вакансия скрыта. Найденные по синониму запроса правило не трогает.
        </p>
      </BvCard>

      <!-- 3 · сомнительные зарплаты -->
      <BvCard title="Сомнительные зарплаты" class="st-dim" :class="{ 'is-on': шаг >= 3 }">
        <template #actions>
          <span class="st-scope">не входят в медианы</span>
        </template>
        <p class="clean__figure">
          <span class="st-figure"><StoryNumber :value="сомнительные['число']" :active="шаг >= 3" /></span>
          <span class="st-note">{{ plural(сомнительные['число'], 'сумма', 'суммы', 'сумм') }} с пометкой</span>
        </p>

        <BvTable v-if="сомнительные['примеры'].length" label="Примеры сомнительных зарплат">
          <thead>
            <tr>
              <th>Вакансия</th>
              <th class="col-num">Сумма</th>
              <th>Почему сомнительна</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="пример in сомнительные['примеры']" :key="пример['название']">
              <td><div class="st-vac st-vac--short"><span class="st-vac__name">{{ пример['название'] }}</span></div></td>
              <td class="col-num">{{ сумма(пример) }}</td>
              <td>{{ пример['причина'] }}</td>
            </tr>
          </tbody>
        </BvTable>

        <p class="st-note">
          Вакансия остаётся в списке — с пометкой и причиной. Ставки за час и смену сомнительными не считаются:
          это другая единица, а не опечатка.
        </p>
      </BvCard>

      <!-- 4 · снятые с публикации -->
      <BvCard title="Снятые с публикации" class="st-dim" :class="{ 'is-on': шаг >= 4 }">
        <template #actions>
          <span class="st-scope">уходят в архив</span>
        </template>
        <p class="clean__figure">
          <span class="st-figure"><StoryNumber :value="снятые['в_архиве']" :active="шаг >= 4" /></span>
          <span class="st-note">{{ plural(снятые['в_архиве'], 'вакансия', 'вакансии', 'вакансий') }} в архиве</span>
        </p>

        <BvStackedBar :items="доли" />

        <p class="st-note">
          Вакансия, которой больше нет в выдаче, не удаляется. В списке и числах — только активные, архив нужен
          для динамики рынка.
        </p>
      </BvCard>
    </div>
  </div>
</template>

<style scoped>
.clean__figure {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1) var(--s-2);
  max-width: none;
}

/* Пример — строка из базы, отделённая волосяными линиями, как строка таблицы. */
.clean__example {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
  padding: var(--s-3) 0;
  box-shadow: inset 0 1px 0 var(--c-border), inset 0 -1px 0 var(--c-border);
}

.clean__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  min-width: 0;
}

/* Копии: города стоят рядом, затем уступают место одной вакансии. */
.clean__cities {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-1);
  min-height: var(--h-control-sm);
}

.clean__city {
  display: inline-flex;
  max-width: 180px;
  overflow: hidden;
  transition: max-width var(--dur-enter) var(--ease-enter), opacity var(--dur-panel) var(--ease-standard),
    margin var(--dur-enter) var(--ease-enter);
  transition-delay: calc((10 - var(--i)) * 30ms);
}

.clean__merged {
  display: inline-flex;
  max-width: 0;
  opacity: 0;
  overflow: hidden;
  white-space: nowrap;
  transition: max-width var(--dur-enter) var(--ease-enter) var(--dur-panel),
    opacity var(--dur-panel) var(--ease-standard) var(--dur-panel);
}

.clean__example.is-merged .clean__city {
  max-width: 0;
  margin-right: calc(var(--s-1) * -1);
  opacity: 0;
}

.clean__example.is-merged .clean__merged { max-width: 320px; opacity: 1; }

@media (prefers-reduced-motion: reduce) {
  .clean__city,
  .clean__merged { transition: none; }
}
</style>
