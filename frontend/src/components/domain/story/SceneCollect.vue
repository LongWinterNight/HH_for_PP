<script setup>
import { computed } from 'vue'
import StoryNumber from '@/components/domain/story/StoryNumber.vue'
import { useScene } from '@/composables/useScene'
import { num, plural } from '@/utils/format'

// Сбор: что принёс каждый запрос последнего запуска.
//
// Запросы проходят по очереди, как в настоящем сборе: страницы выдачи
// заполняются одна за другой, затем видно, сколько из взятого было
// новым, сколько обновилось и сколько уже лежало в базе без изменений.
// Последнее — самое поучительное: два написания одного слова приносят
// почти одно и то же, и по полосе это видно без объяснений.
const props = defineProps({
  // story['сбор'] из /api/system/story.
  data: { type: Object, default: null },
  // Запрос, которым найдена вакансия-пример: её строка помечается.
  heroQuery: { type: String, default: '' }
})

const запросы = computed(() => props.data?.['запросы'] ?? [])
// Шаг на запрос и ещё один — на итог.
const шагов = () => запросы.value.length + 1
const сцена = useScene(шагов, { пауза: 1100, готово: () => запросы.value.length > 0 })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const наибольшее = computed(() => Math.max(...запросы.value.map((з) => з['взято']), 1))

function состав(запрос) {
  const взято = запрос['взято'] || 0
  const прежних = Math.max(0, взято - запрос['новых'] - запрос['обновлено'])
  const доля = (часть) => `${(часть / наибольшее.value) * 100}%`
  return { новых: доля(запрос['новых']), обновлено: доля(запрос['обновлено']), прежних: доля(прежних), числом: прежних }
}

function время(мс) {
  const секунд = Math.round(мс / 1000)
  if (секунд < 60) return `${секунд} с`
  return `${Math.floor(секунд / 60)} мин ${String(секунд % 60).padStart(2, '0')} с`
}

const ПОЛЯ = { name: 'названии', description: 'описании', company_name: 'названии компании' }
const гдеИщется = computed(() =>
  (props.data?.['поля_поиска'] ?? []).map((поле) => ПОЛЯ[поле] ?? поле).join(' и ')
)

const итогВиден = computed(() => шаг.value > запросы.value.length)
</script>

<template>
  <div ref="корень" class="collect">
    <p v-if="!запросы.length" class="collect__note">Сбор ещё не запускался — показать нечего.</p>

    <template v-else>
      <ol class="collect__rows" aria-label="Запросы последнего сбора">
        <li
          v-for="(запрос, i) in запросы"
          :key="запрос['запрос']"
          class="collect__row"
          :class="{ 'is-run': шаг === i + 1 && идёт, 'is-done': шаг > i + 1 || (шаг === i + 1 && !идёт), 'is-wait': шаг < i + 1 }"
        >
          <div class="collect__query">
            <span class="collect__word">{{ запрос['запрос'] }}</span>
            <span v-if="запрос['запрос'] === heroQuery" class="collect__hero">отсюда вакансия-пример</span>
          </div>

          <!-- Страницы выдачи: по квадрату на страницу. -->
          <div class="collect__pages" :aria-label="`${запрос['страниц']} ${plural(запрос['страниц'], 'страница', 'страницы', 'страниц')} выдачи`">
            <span
              v-for="страница in запрос['страниц']"
              :key="страница"
              class="collect__page"
              :style="{ '--i': страница - 1 }"
            ></span>
          </div>

          <div class="collect__taken">
            <StoryNumber :value="запрос['взято']" :active="шаг >= i + 1" class="collect__count" />
            <span class="collect__unit">из {{ num(запрос['найдено']) }}</span>
          </div>

          <!-- Из чего состоит взятое: длина полосы — доля от самого большого запроса. -->
          <div class="collect__bar" aria-hidden="true">
            <span class="collect__part collect__part--new" :style="{ width: состав(запрос).новых }"></span>
            <span class="collect__part collect__part--upd" :style="{ width: состав(запрос).обновлено }"></span>
            <span class="collect__part collect__part--old" :style="{ width: состав(запрос).прежних }"></span>
          </div>

          <p class="collect__mix">
            новых {{ num(запрос['новых']) }} · обновлено {{ num(запрос['обновлено']) }} · без изменений {{ num(состав(запрос).числом) }}
            <span class="collect__time">{{ запрос['из_памяти'] ? 'из памяти' : время(запрос['мс']) }}</span>
          </p>
        </li>
      </ol>

      <ul class="collect__legend" aria-hidden="true">
        <li><span class="collect__key collect__part--new"></span>новые</li>
        <li><span class="collect__key collect__part--upd"></span>обновлённые</li>
        <li><span class="collect__key collect__part--old"></span>уже были в базе</li>
      </ul>

      <p class="collect__total" :class="{ 'is-shown': итогВиден }" aria-live="polite">
        Сбор №{{ data['номер'] }}:
        <strong><StoryNumber :value="data['взято']" :active="итогВиден" /></strong>
        {{ plural(data['взято'], 'вакансия', 'вакансии', 'вакансий') }} с {{ data['страниц'] }}
        {{ plural(data['страниц'], 'страницы', 'страниц', 'страниц') }} за {{ время(data['мс']) }} —
        {{ num(data['новых']) }} {{ plural(data['новых'], 'новая', 'новые', 'новых') }},
        {{ num(data['обновлено']) }} {{ plural(data['обновлено'], 'обновлена', 'обновлены', 'обновлено') }}.
      </p>

      <p class="collect__note">
        Источник ищет слова запроса в {{ гдеИщется }} вакансии. Каждый запрос идёт страница за страницей;
        вакансия, найденная двумя запросами, записывается один раз — поэтому у второго написания того же слова
        новых почти нет.
      </p>
    </template>
  </div>
</template>

<style scoped>
.collect {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.collect__rows {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
}

.collect__row {
  display: grid;
  grid-template-columns: minmax(120px, 1.1fr) minmax(96px, 0.9fr) 104px minmax(0, 2fr);
  grid-template-areas:
    'query pages taken bar'
    'query pages taken mix';
  align-items: center;
  column-gap: var(--s-5);
  row-gap: 2px;
  padding: var(--s-3);
  border-radius: var(--r-md);
  box-shadow: inset 0 -1px 0 var(--c-border);
  transition: background-color var(--dur-panel) var(--ease-standard), opacity var(--dur-panel) var(--ease-standard);
}

.collect__row.is-wait { opacity: 0.38; }
/* Запрос, который идёт сейчас, — тем же тоном, что статус «Идёт». */
.collect__row.is-run { background: var(--c-status-run-bg); }

.collect__query {
  grid-area: query;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.collect__word {
  font-family: var(--font-mono);
  font-size: var(--t-ui-size);
  color: var(--c-text);
  overflow-wrap: anywhere;
}

.collect__hero,
.collect__unit,
.collect__mix,
.collect__note,
.collect__legend {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

.collect__pages {
  grid-area: pages;
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.collect__page {
  width: 10px;
  height: 14px;
  border-radius: 2px;
  box-shadow: var(--border-strong);
  background: transparent;
}

/* Страницы заполняются по одной — так сбор и идёт. */
.collect__row.is-run .collect__page,
.collect__row.is-done .collect__page {
  background: var(--c-text);
  box-shadow: none;
  transition: background-color var(--dur-ui) var(--ease-standard);
}
.collect__row.is-run .collect__page { transition-delay: calc(var(--i) * 90ms); }

.collect__taken {
  grid-area: taken;
  display: flex;
  align-items: baseline;
  gap: var(--s-1);
  white-space: nowrap;
}

.collect__count {
  font-size: var(--t-h3-size);
  font-weight: var(--w-strong);
  color: var(--c-text);
}

.collect__bar {
  grid-area: bar;
  display: flex;
  height: 8px;
  border-radius: var(--r-pill);
  overflow: hidden;
  background: var(--c-surface-sunken);
}

.collect__part {
  flex: 0 0 auto;
  height: 100%;
  transform-origin: left center;
  transition: width 700ms var(--ease-enter);
}

/* Тон одной шкалы, не цвета: категории в системе цветом не кодируются. */
.collect__part--new { background: var(--c-text); }
.collect__part--upd { background: var(--c-text-muted); }
.collect__part--old { background: var(--c-border-strong); }

/* Пока до запроса не дошли, полоса пуста. */
.collect__row.is-wait .collect__part { width: 0 !important; }

.collect__mix {
  grid-area: mix;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--s-2);
  max-width: none;
  font-variant-numeric: tabular-nums;
}

.collect__row.is-wait .collect__mix { visibility: hidden; }

.collect__legend {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-4);
}

.collect__legend li {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
}

.collect__key {
  width: 12px;
  height: 8px;
  border-radius: 2px;
}

.collect__total {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
  max-width: none;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity var(--dur-enter) var(--ease-enter), transform var(--dur-enter) var(--ease-enter);
}

.collect__total.is-shown { opacity: 1; transform: none; }
.collect__total strong { color: var(--c-text); font-weight: var(--w-strong); }
.collect__note { max-width: 78ch; }

@media (max-width: 1023px) {
  .collect__row {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      'query taken'
      'pages pages'
      'bar bar'
      'mix mix';
    row-gap: var(--s-2);
  }
}

@media (prefers-reduced-motion: reduce) {
  .collect__row,
  .collect__page,
  .collect__part,
  .collect__total { transition: none !important; }
}
</style>
