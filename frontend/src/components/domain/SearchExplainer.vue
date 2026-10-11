<script setup>
import { computed, ref } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvField from '@/components/ui/BvField.vue'
import { system } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { useSteps } from '@/composables/useSteps'
import { num, plural } from '@/utils/format'

// Поиск по шагам, на настоящем запросе и настоящих вакансиях.
//
// Человек набирает запрос и видит то, что обычно скрыто за списком:
// как запрос разобран, что нашли слова, что нашёл смысл и как два
// списка слились в один. Считает это тот же код, что ищет на экране
// «Вакансии»: объяснение, которое считает иначе, объясняло бы не его.
//
// Шаги раскрываются по очереди один раз — порядок и есть объяснение.
const props = defineProps({
  // Последний замер на эталоне (state['замер']) — числа качества.
  measure: { type: Object, default: null }
})

const ПРИМЕРЫ = ['питон разработчик', 'дизайнр интерьера', '3д макс мебель', 'рисовать баннеры для соцсетей']
const ШАГОВ = 3

const запрос = ref('')
const разбор = useApi((текст, options) => system.explain(текст, options))
const { шаг, запустить } = useSteps(ШАГОВ, { пауза: 900 })

const данные = computed(() => разбор.data.value)
// Какая вакансия выделена: по ней видно, откуда она пришла в итог.
const выделена = ref('')

async function разобрать(текст = запрос.value) {
  const чистый = (текст || '').trim()
  if (!чистый) return
  запрос.value = чистый
  выделена.value = ''
  шаг.value = 0
  const ответ = await разбор.load(чистый)
  if (ответ) запустить()
}

// Группы запроса: внутри группы — варианты одного и того же, между
// группами — «и».
const группы = computed(() => (данные.value?.['разбор']?.['группы'] ?? []).map((варианты) =>
  варианты.map((вариант) => (вариант.endsWith('*') ? `${вариант.slice(0, -1)}…` : вариант))
))
const замены = computed(() => Object.entries(данные.value?.['разбор']?.['замены'] ?? {}))

const слова = computed(() => данные.value?.['слова'] ?? { 'найдено': 0, 'первые': [] })
const смысл = computed(() => данные.value?.['смысл'] ?? { 'найдено': 0, 'первые': [] })
const итог = computed(() => данные.value?.['итог'] ?? { 'найдено': 0, 'первые': [] })

const дробь = (число) => String(число ?? '').replace('.', ',')

// Вклад места в оценку слияния: 1 / (k + место).
function вклад(место) {
  const k = данные.value?.k ?? 60
  return место ? 1 / (k + место) : 0
}

// Какую долю оценки дал каждый список — шириной частей полосы. Сами
// вклады — сотые доли единицы: как множитель роста они оставляли полосу
// почти пустой.
function доли(строка) {
  const слова = вклад(строка['место_по_словам'])
  const смысл = вклад(строка['место_по_смыслу'])
  const сумма = слова + смысл || 1
  return { слова: `${(слова / сумма) * 100}%`, смысл: `${(смысл / сумма) * 100}%` }
}

function откуда(строка) {
  const части = []
  if (строка['место_по_словам']) части.push(`слова №${строка['место_по_словам']}`)
  if (строка['место_по_смыслу']) части.push(`смысл №${строка['место_по_смыслу']}`)
  return части.join(' + ')
}

// Почему смысл не участвовал — словами, а не пустым столбцом.
const оСмысле = computed(() => {
  const с = смысл.value
  if (с['участвовал']) return ''
  if (!с['доступен']) return 'Модель векторов не поднята — поиск идёт только по словам.'
  return `Ни одна вакансия не близка запросу настолько, чтобы считаться найденной (порог ${дробь(с['порог'])}).`
})

// Числа замера — полосами. Порядок задан: от одного способа к двум.
const качество = computed(() => {
  const способы = props.measure?.['способы']
  if (!способы) return []
  return Object.entries(способы).map(([имя, числа]) => ({
    // Модель названа в пояснении под полосами: в подписи строки она
    // не помещалась и обрезалась многоточием.
    label: имя === 'слова' ? 'только слова' : имя.startsWith('смысл') ? 'только смысл' : 'слова и смысл',
    value: Math.round(числа['ndcg'] * 1000) / 1000
  }))
})
</script>

<template>
  <div class="exp">
    <form class="exp__form" @submit.prevent="разобрать()">
      <BvField
        v-model="запрос"
        label="Запрос"
        placeholder="Профессия, навык или задача словами"
        hint="Тот же поиск, что на экране «Вакансии», — с показом каждого шага."
      />
      <!-- Главное действие экрана — единственная окрашенная кнопка. -->
      <BvButton variant="primary" type="submit" :loading="разбор.loading.value" :disabled="!запрос.trim()">
        Разобрать запрос
      </BvButton>
    </form>

    <div class="exp__examples">
      <span class="exp__examples-label">Например:</span>
      <BvButton v-for="пример in ПРИМЕРЫ" :key="пример" size="sm" @click="разобрать(пример)">{{ пример }}</BvButton>
    </div>

    <p v-if="разбор.error.value" class="exp__error" role="alert">{{ разбор.error.value }}</p>

    <div v-if="данные" class="exp__steps" aria-live="polite">
      <!-- Шаг 1 · разбор запроса -->
      <section v-if="шаг >= 1" class="exp__step">
        <h3 class="exp__step-title"><span class="exp__num">1</span> Запрос разобран</h3>
        <div class="exp__groups">
          <template v-for="(варианты, i) in группы" :key="i">
            <span v-if="i > 0" class="exp__and">и</span>
            <span class="exp__group">
              <template v-for="(вариант, j) in варианты" :key="вариант">
                <span v-if="j > 0" class="exp__or">или</span>
                <span class="exp__term">{{ вариант }}</span>
              </template>
            </span>
          </template>
        </div>
        <p class="exp__note">
          Слова приведены к начальной форме — так же, как в индексе.
          <template v-if="замены.length">
            Добавлено:
            <template v-for="([было, стало], i) in замены" :key="было">
              <template v-if="i > 0">; </template>«{{ было }}» → {{ стало }}
            </template>.
          </template>
          <template v-if="данные['разбор']['ослаблен']">
            Вакансий со всеми словами нет — условие ослаблено до «любое из слов».
          </template>
        </p>
      </section>

      <!-- Шаг 2 · два способа -->
      <section v-if="шаг >= 2" class="exp__step">
        <h3 class="exp__step-title"><span class="exp__num">2</span> Два способа ищут независимо</h3>
        <div class="exp__lists">
          <div class="exp__list">
            <h4 class="exp__list-title">
              По словам
              <span class="exp__count">{{ num(слова['найдено']) }}</span>
            </h4>
            <p v-if="!слова['первые'].length" class="exp__empty">Слов запроса в вакансиях нет.</p>
            <ol v-else class="exp__rows">
              <li
                v-for="строка in слова['первые']"
                :key="строка['ид']"
                class="exp__row"
                :class="{ 'is-marked': выделена === строка['ид'] }"
              >
                <span class="exp__place">{{ строка['место_по_словам'] }}</span>
                <span class="exp__name">
                  {{ строка['название'] }}
                  <span class="exp__company">{{ строка['компания'] }}</span>
                </span>
                <span class="exp__why">{{ строка['почему'] }}</span>
              </li>
            </ol>
          </div>

          <div class="exp__list">
            <h4 class="exp__list-title">
              По смыслу
              <span class="exp__count">{{ num(смысл['найдено']) }}</span>
            </h4>
            <p v-if="оСмысле" class="exp__empty">{{ оСмысле }}</p>
            <ol v-else class="exp__rows">
              <li
                v-for="строка in смысл['первые']"
                :key="строка['ид']"
                class="exp__row"
                :class="{ 'is-marked': выделена === строка['ид'] }"
              >
                <span class="exp__place">{{ строка['место_по_смыслу'] }}</span>
                <span class="exp__name">
                  {{ строка['название'] }}
                  <span class="exp__company">{{ строка['компания'] }}</span>
                </span>
                <!-- Близость — полосой: по числу 0,634 не видно, много это или мало. -->
                <span class="exp__near" :title="`близость ${дробь(строка['близость'])}`">
                  <span class="exp__near-bar" :style="{ width: `${Math.round((строка['близость'] ?? 0) * 100)}%` }"></span>
                </span>
              </li>
            </ol>
            <p v-if="!оСмысле" class="exp__note">
              Модель {{ смысл['модель'] }} на видеокарте этой машины; тексты наружу не уходят.
              Ниже близости {{ дробь(смысл['порог']) }} вакансия найденной не считается.
            </p>
          </div>
        </div>
      </section>

      <!-- Шаг 3 · слияние -->
      <section v-if="шаг >= 3" class="exp__step">
        <h3 class="exp__step-title"><span class="exp__num">3</span> Списки слиты по местам</h3>
        <p v-if="!итог['первые'].length" class="exp__empty">
          Ничего не найдено: слов запроса в вакансиях нет, и по смыслу ни одна не подошла.
        </p>
        <template v-else>
          <TransitionGroup tag="ol" name="exp-merge" class="exp__rows exp__rows--merged" appear>
            <li
              v-for="(строка, i) in итог['первые']"
              :key="строка['ид']"
              class="exp__row exp__row--merged"
              :class="{ 'is-marked': выделена === строка['ид'] }"
              :style="{ '--i': i }"
              tabindex="0"
              @mouseenter="выделена = строка['ид']"
              @mouseleave="выделена = ''"
              @focus="выделена = строка['ид']"
              @blur="выделена = ''"
            >
              <span class="exp__place">{{ i + 1 }}</span>
              <span class="exp__name">
                {{ строка['название'] }}
                <span class="exp__company">{{ строка['компания'] }}</span>
              </span>
              <span class="exp__from">{{ откуда(строка) }}</span>
              <!-- Из чего сложилась оценка: вклад каждого списка одной полосой. -->
              <span class="exp__score" aria-hidden="true">
                <span class="exp__score-part exp__score-part--words" :style="{ width: доли(строка).слова }"></span>
                <span class="exp__score-part exp__score-part--sense" :style="{ width: доли(строка).смысл }"></span>
              </span>
            </li>
          </TransitionGroup>
          <p class="exp__note">
            Каждый список даёт вакансии 1 / ({{ данные.k }} + место), вклады складываются: найденное обоими способами
            встаёт выше найденного одним. Полоса справа — чья доля в оценке: тёмная часть от слов, светлая от смысла.
            Наведите на строку — она подсветится в списках выше.
            Всего найдено {{ num(итог['найдено']) }} {{ plural(итог['найдено'], 'вакансия', 'вакансии', 'вакансий') }}
            за {{ данные['мс'] }} мс.
          </p>
        </template>
      </section>
    </div>

    <!-- Качество: чем и на чём меряли. Без оговорок число обещало бы
         больше, чем за ним стоит. -->
    <section v-if="качество.length" class="exp__quality">
      <h3 class="exp__step-title">Насколько это точно</h3>
      <BvBarList :items="качество" :format="(v) => v.toFixed(3).replace('.', ',')" />
      <p class="exp__note">
        Качество первых десяти мест (nDCG@10, от 0 до 1) на эталоне: {{ measure['запросов'] }}
        {{ plural(measure['запросов'], 'запрос', 'запроса', 'запросов') }}, {{ num(measure['пар']) }} размеченных пар,
        замер от {{ measure['когда'].split('-').reverse().join('.') }}. Разметка — {{ measure['разметка'] }}.
      </p>
    </section>
  </div>
</template>

<style scoped>
.exp {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.exp__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--s-3);
  align-items: start;
}

/* Кнопка встаёт на уровень поля, а не его подписи. */
.exp__form :deep(.btn) { margin-top: calc(var(--t-caption-lh) + var(--s-1)); }

.exp__examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.exp__examples-label,
.exp__note,
.exp__empty {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.exp__error {
  font-size: var(--t-caption-size);
  color: var(--c-status-err-text);
}

.exp__steps {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.exp__step {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
  animation: exp-in var(--dur-enter) var(--ease-enter) both;
}

@keyframes exp-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

.exp__step-title {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.exp__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--r-pill);
  box-shadow: var(--border-strong);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-secondary);
}

/* Группы запроса: рамка вокруг вариантов одного и того же. */
.exp__groups {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.exp__group {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-1) var(--s-2);
  border-radius: var(--r-md);
  box-shadow: var(--border-strong);
}

.exp__term {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--t-caption-size);
  color: var(--c-text);
  overflow-wrap: anywhere;
}

.exp__and,
.exp__or {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.exp__lists {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--s-6);
}

.exp__list {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.exp__list-title {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  font-size: var(--t-caption-size);
  font-weight: var(--w-medium);
  color: var(--c-text-secondary);
}

.exp__count {
  font-variant-numeric: tabular-nums;
  font-weight: var(--w-regular);
  color: var(--c-text-muted);
}

.exp__rows {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  position: relative;
}

.exp__row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--s-2);
  min-height: var(--h-control-md);
  padding: var(--s-1) var(--s-2);
  border-radius: var(--r-sm);
  box-shadow: inset 0 -1px 0 var(--c-border);
  transition: var(--t-hover);
}

/* Строка, по которой видно происхождение итога: та же подложка, что у
   наведения в таблицах. */
.exp__row.is-marked {
  background: var(--c-surface-hover);
  box-shadow: inset 2px 0 0 var(--c-text), inset 0 -1px 0 var(--c-border);
}

.exp__place {
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-muted);
}

.exp__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.exp__company {
  margin-left: var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.exp__why,
.exp__from {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  white-space: nowrap;
}

/* Близость: трек и заполнение — те же, что у полосы прогресса. */
.exp__near {
  width: 56px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--c-surface-sunken);
  overflow: hidden;
}

.exp__near-bar {
  display: block;
  height: 100%;
  border-radius: var(--r-pill);
  background: var(--c-text-secondary);
}

.exp__row--merged {
  grid-template-columns: 24px minmax(0, 1fr) auto 72px;
  cursor: default;
}

.exp__row--merged:focus-visible { outline: none; box-shadow: var(--focus-ring); }

/* Оценка слияния: две части одной полосы, шириной по вкладу списка.
   Различаются тоном одной шкалы, а не цветами: в системе категории не
   кодируются цветом. */
.exp__score {
  display: flex;
  height: 6px;
  border-radius: var(--r-pill);
  overflow: hidden;
  background: var(--c-surface-sunken);
}

.exp__score-part { flex: 0 0 auto; min-width: 0; }
.exp__score-part--words { background: var(--c-text); }
.exp__score-part--sense { background: var(--c-text-muted); }

/* Слияние: строки встают на места по одной, сверху вниз. Один раз. */
.exp-merge-enter-active {
  transition: opacity var(--dur-enter) var(--ease-enter), transform var(--dur-enter) var(--ease-enter);
  transition-delay: calc(var(--i) * 110ms);
}
.exp-merge-enter-from { opacity: 0; transform: translateY(-10px); }

.exp__quality {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding-top: var(--s-5);
  box-shadow: inset 0 1px 0 var(--c-border);
}

@media (max-width: 767px) {
  .exp__form { grid-template-columns: minmax(0, 1fr); }
  .exp__form :deep(.btn) { margin-top: 0; }
  .exp__lists { grid-template-columns: minmax(0, 1fr); gap: var(--s-5); }
  /* Происхождение уходит под название: в одну строку всё не помещается. */
  .exp__row--merged { grid-template-columns: 24px minmax(0, 1fr); row-gap: 2px; }
  .exp__row--merged .exp__from { grid-column: 2; }
  .exp__row--merged .exp__score { grid-column: 2; }
  .exp__company { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .exp__step { animation: none; }
  .exp-merge-enter-active { transition: none; }
  .exp__row { transition: none; }
}
</style>
