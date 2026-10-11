<script setup>
import { computed } from 'vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import StoryNumber from '@/components/domain/story/StoryNumber.vue'
import { useScene } from '@/composables/useScene'
import { moneyExact, num, plural, salaryPeriod } from '@/utils/format'

// Очистка: четыре правила, которые стоят между собранным и числами.
//
// У каждого правила — настоящий пример из базы и число строк, которых
// оно касается. Правила срабатывают по очереди, и на примере видно,
// что именно происходит со строкой: копии сходятся в одну, чужая
// вакансия гаснет, сомнительная сумма получает пометку.
//
// Ни одно правило ничего не удаляет — это сказано в каждом блоке: без
// этого «очистка» читается как «потеря данных».
const props = defineProps({
  // story['очистка'] из /api/system/story.
  data: { type: Object, default: null }
})

const ШАГОВ = 4
const сцена = useScene(ШАГОВ, { пауза: 1500, готово: () => Boolean(props.data) })
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
  return `${части.join(' – ')} ${знак} ${salaryPeriod(пример['период']) ?? 'в месяц'}`
}

const доляАктивных = computed(() => {
  const с = снятые.value
  const всего = (с?.['активных'] ?? 0) + (с?.['в_архиве'] ?? 0)
  return всего ? `${(с['активных'] / всего) * 100}%` : '0%'
})

const класс = (номер) => ({ 'is-run': шаг.value === номер && идёт.value, 'is-on': шаг.value >= номер })
</script>

<template>
  <div ref="корень" class="clean">
    <p v-if="!data" class="clean__note">Данные об очистке не получены.</p>

    <ol v-else class="clean__rules" aria-label="Правила очистки">
      <!-- 1 · копии по городам -->
      <li class="clean__rule" :class="класс(1)">
        <header class="clean__head">
          <h3 class="clean__title">Копии по городам</h3>
          <span class="clean__figure">
            <StoryNumber :value="копии['строк']" :active="шаг >= 1" /> → <StoryNumber :value="копии['вакансий']" :active="шаг >= 1" />
          </span>
        </header>
        <div v-if="копии['пример']" class="clean__demo">
          <p class="clean__sample">
            {{ копии['пример']['название'] }}
            <span class="clean__muted">{{ копии['пример']['компания'] }}</span>
          </p>
          <div class="clean__cities" aria-hidden="true">
            <span
              v-for="(город, i) in копии['пример']['города']"
              :key="город"
              class="clean__city"
              :style="{ '--i': i }"
            >{{ город }}</span>
            <span v-if="копии['пример']['строк'] > копии['пример']['города'].length" class="clean__city clean__city--more" :style="{ '--i': 9 }">
              ещё {{ копии['пример']['строк'] - копии['пример']['города'].length }}
            </span>
            <span class="clean__merged">
              1 вакансия · {{ копии['пример']['строк'] }}
              {{ plural(копии['пример']['строк'], 'город', 'города', 'городов') }}
            </span>
          </div>
        </div>
        <p class="clean__text">
          Работодатель размещает одну вакансию в десятках городов. В медиане зарплаты и топе работодателей она
          считается один раз; в списке остаются все города — человеку нужна строка его города.
        </p>
      </li>

      <!-- 2 · найдено не по запросу -->
      <li class="clean__rule" :class="класс(2)">
        <header class="clean__head">
          <h3 class="clean__title">Найдено не по запросу</h3>
          <span class="clean__figure"><StoryNumber :value="чужие['скрыто']" :active="шаг >= 2" /></span>
        </header>
        <div v-if="чужие['пример']" class="clean__demo">
          <p class="clean__sample clean__sample--fade">
            {{ чужие['пример']['название'] }}
            <span class="clean__muted">
              {{ компанияЧастями.до }}<mark class="clean__hit">{{ компанияЧастями.слово }}</mark>{{ компанияЧастями.после }}
            </span>
          </p>
          <p class="clean__why">
            запрос <span class="clean__mono">{{ чужие['пример']['запрос'] }}</span>
            <BvStatus v-if="шаг >= 2" kind="stop" label="Скрыта из списка" />
          </p>
        </div>
        <p class="clean__text">
          Источник по умолчанию ищет слова запроса и в названии компании. Сбор теперь просит искать только в названии
          и описании вакансии, а собранное раньше проверяет это правило: слово есть только в названии компании —
          вакансия скрыта из списка и чисел. Найденные по синониму запроса правило не трогает.
        </p>
      </li>

      <!-- 3 · сомнительные зарплаты -->
      <li class="clean__rule" :class="класс(3)">
        <header class="clean__head">
          <h3 class="clean__title">Сомнительные зарплаты</h3>
          <span class="clean__figure"><StoryNumber :value="сомнительные['число']" :active="шаг >= 3" /></span>
        </header>
        <ul class="clean__demo clean__doubts">
          <li v-for="пример in сомнительные['примеры']" :key="пример['название']" class="clean__doubt">
            <span class="clean__sample">{{ пример['название'] }}</span>
            <span class="clean__sum">{{ сумма(пример) }}</span>
            <span class="clean__reason">{{ пример['причина'] }}</span>
          </li>
        </ul>
        <p class="clean__text">
          Сумма, которой нельзя верить, не входит в медианы и распределение. Вакансия остаётся в списке — с пометкой
          и причиной. Ставки за час и смену сомнительными не считаются: это другая единица, а не опечатка.
        </p>
      </li>

      <!-- 4 · снятые с публикации -->
      <li class="clean__rule" :class="класс(4)">
        <header class="clean__head">
          <h3 class="clean__title">Снятые с публикации</h3>
          <span class="clean__figure"><StoryNumber :value="снятые['в_архиве']" :active="шаг >= 4" /></span>
        </header>
        <div class="clean__demo">
          <div class="clean__split" aria-hidden="true">
            <span class="clean__split-active" :style="{ width: шаг >= 4 ? доляАктивных : '100%' }"></span>
          </div>
          <p class="clean__why clean__why--spread">
            <span>активных {{ num(снятые['активных']) }}</span>
            <span>в архиве {{ num(снятые['в_архиве']) }}</span>
          </p>
        </div>
        <p class="clean__text">
          Вакансия, которой больше нет в выдаче, не удаляется: уходит в архив. В списке и числах — только активные,
          архив нужен для динамики рынка.
        </p>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.clean__rules {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--s-5);
}

.clean__rule {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
  padding: var(--s-5);
  border-radius: var(--r-md);
  box-shadow: var(--border);
  opacity: 0.4;
  transition: opacity var(--dur-panel) var(--ease-standard), box-shadow var(--dur-panel) var(--ease-standard),
    background-color var(--dur-panel) var(--ease-standard);
}

.clean__rule.is-on { opacity: 1; }
.clean__rule.is-run { background: var(--c-status-run-bg); box-shadow: inset 0 0 0 1px var(--c-status-run-dot); }

.clean__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}

.clean__title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.clean__figure {
  font-size: var(--t-h3-size);
  font-weight: var(--w-strong);
  color: var(--c-text);
  white-space: nowrap;
}

.clean__demo {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
  min-height: 84px;
  margin: 0;
  padding: var(--s-3);
  list-style: none;
  border-radius: var(--r-sm);
  background: var(--c-surface);
  box-shadow: var(--border);
}

.clean__sample {
  font-size: var(--t-ui-size);
  color: var(--c-text);
  overflow-wrap: anywhere;
  max-width: none;
  transition: opacity 500ms var(--ease-standard);
}

.clean__muted {
  margin-left: var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.clean__text,
.clean__why,
.clean__note,
.clean__reason {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

/* Копии: города стоят рядом, затем сходятся в одну плашку. */
.clean__cities {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
  min-height: var(--h-control-sm);
}

.clean__city,
.clean__merged {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 var(--s-2);
  border-radius: var(--r-xs);
  font-size: var(--t-label-alt-size);
  white-space: nowrap;
}

.clean__city {
  box-shadow: var(--border-strong);
  color: var(--c-text-secondary);
  max-width: 160px;
  overflow: hidden;
  transition: max-width 520ms var(--ease-enter), padding 520ms var(--ease-enter), opacity 360ms var(--ease-standard),
    margin 520ms var(--ease-enter);
  transition-delay: calc((9 - var(--i)) * 45ms);
}

.clean__city--more { color: var(--c-text-muted); box-shadow: none; }

.clean__merged {
  background: var(--c-text);
  color: var(--c-text-inverse);
  opacity: 0;
  transform: scale(0.92);
  transform-origin: left center;
  transition: opacity 320ms var(--ease-enter) 620ms, transform 320ms var(--ease-enter) 620ms;
}

.clean__rule.is-on .clean__city {
  max-width: 0;
  padding: 0;
  margin-right: calc(var(--s-1) * -1);
  opacity: 0;
  box-shadow: none;
}

.clean__rule.is-on .clean__merged { opacity: 1; transform: none; }

/* Не по запросу: слово запроса отмечено там, где оно нашлось, — в
   названии компании; сама строка гаснет. */
.clean__hit {
  background: transparent;
  color: inherit;
  border-radius: 3px;
  padding: 0 2px;
  transition: background-color 320ms var(--ease-standard), color 320ms var(--ease-standard);
}

.clean__rule.is-on .clean__hit { background: var(--c-marker-subtle); color: var(--c-text); }
.clean__rule.is-on .clean__sample--fade { opacity: 0.45; transition-delay: 700ms; }

.clean__why {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.clean__why--spread { justify-content: space-between; font-variant-numeric: tabular-nums; }

.clean__mono {
  font-family: var(--font-mono);
  color: var(--c-text-secondary);
}

.clean__doubt {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0 var(--s-3);
  align-items: baseline;
}

.clean__sum {
  font-size: var(--t-ui-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
  white-space: nowrap;
  text-decoration-line: line-through;
  text-decoration-color: transparent;
  transition: text-decoration-color 400ms var(--ease-standard);
}

.clean__rule.is-on .clean__sum { text-decoration-color: var(--c-text-muted); }

.clean__reason {
  grid-column: 1 / -1;
  opacity: 0;
  transition: opacity 400ms var(--ease-standard) 300ms;
}

.clean__rule.is-on .clean__reason { opacity: 1; }

/* Снятые: полоса всей базы делится на активные и архив. */
.clean__split {
  height: 10px;
  margin-top: var(--s-3);
  border-radius: var(--r-pill);
  background: var(--c-border-strong);
  overflow: hidden;
}

.clean__split-active {
  display: block;
  height: 100%;
  background: var(--c-text);
  transition: width 900ms var(--ease-enter);
}

@media (max-width: 1023px) {
  .clean__rules { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 767px) {
  .clean__rule { padding: var(--s-4); }
  .clean__muted { display: block; margin-left: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .clean__rule,
  .clean__sample,
  .clean__city,
  .clean__merged,
  .clean__hit,
  .clean__sum,
  .clean__reason,
  .clean__split-active { transition: none !important; }
}
</style>
