<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvField from '@/components/ui/BvField.vue'
import BvTable from '@/components/ui/BvTable.vue'
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
// Списки — таблицы системы, и ведут себя как любая таблица продукта:
// наведение подсвечивает строку, на которую навели, и только её.
// Раньше наведение на строку итога отмечало ту же вакансию в списках
// выше — сначала подсветкой, потом линиями; оба раза это читалось как
// сбой («выделение перескочило на другую строку»). Происхождение
// строки итога теперь написано в её же колонках.
const props = defineProps({
  // Последний замер на эталоне (state['замер']) — числа качества.
  measure: { type: Object, default: null },
  // Разобрать пример, когда до блока докрутили: пустое поле ничего не
  // объясняет, а нажмут «Разобрать» не все.
  autoplay: { type: Boolean, default: true }
})

// Разбор поднимает модель смысла, если она ещё не поднята: экран по
// этому событию перечитывает её состояние.
const emit = defineEmits(['explained'])

const ПРИМЕРЫ = ['питон разработчик', 'дизайнр интерьера', '3д макс мебель', 'рисовать баннеры для соцсетей']
const ШАГОВ = 3

const запрос = ref('')
const разбор = useApi((текст, options) => system.explain(текст, options))
const { шаг, запустить } = useSteps(ШАГОВ, { пауза: 700 })

const данные = computed(() => разбор.data.value)
const корень = ref(null)
let наблюдатель = null

async function разобрать(текст = запрос.value) {
  const чистый = (текст || '').trim()
  if (!чистый) return
  запрос.value = чистый
  шаг.value = 0
  const ответ = await разбор.load(чистый)
  if (!ответ) return
  emit('explained')
  запустить()
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

// Какую долю оценки дал каждый список — шириной частей полосы.
function доли(запись) {
  const отСлов = вклад(запись['место_по_словам'])
  const отСмысла = вклад(запись['место_по_смыслу'])
  const сумма = отСлов + отСмысла || 1
  return { слова: `${(отСлов / сумма) * 100}%`, смысл: `${(отСмысла / сумма) * 100}%` }
}

// Почему смысл не участвовал — словами, а не пустой таблицей.
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
    label: имя === 'слова' ? 'только слова' : имя.startsWith('смысл') ? 'только смысл' : 'слова и смысл',
    value: Math.round(числа['ndcg'] * 1000) / 1000
  }))
})

onMounted(() => {
  if (!props.autoplay || typeof IntersectionObserver === 'undefined' || !корень.value) return
  наблюдатель = new IntersectionObserver(
    ([запись]) => {
      if (!запись.isIntersecting) return
      наблюдатель.disconnect()
      // Пример с опечаткой: на нём видны и исправление, и оба способа.
      if (!данные.value && !разбор.loading.value) разобрать(ПРИМЕРЫ[1])
    },
    { rootMargin: '0px 0px -25% 0px', threshold: 0 }
  )
  наблюдатель.observe(корень.value)
})

onBeforeUnmount(() => наблюдатель?.disconnect())
</script>

<template>
  <div ref="корень" class="st-stack">
    <BvCard title="Разобрать запрос">
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
        <span class="label">Например</span>
        <BvButton v-for="пример in ПРИМЕРЫ" :key="пример" size="sm" @click="разобрать(пример)">{{ пример }}</BvButton>
      </div>

      <p v-if="разбор.error.value" class="exp__error" role="alert">{{ разбор.error.value }}</p>
    </BvCard>

    <template v-if="данные">
      <!-- Шаг 1 · разбор запроса -->
      <BvCard title="1. Запрос разобран" class="st-in" :class="{ 'is-on': шаг >= 1 }">
        <div class="exp__groups" aria-live="polite">
          <template v-for="(варианты, i) in группы" :key="i">
            <span v-if="i > 0" class="exp__join">и</span>
            <template v-for="(вариант, j) in варианты" :key="вариант">
              <span v-if="j > 0" class="exp__join">или</span>
              <BvChip variant="count">{{ вариант }}</BvChip>
            </template>
          </template>
        </div>
        <p class="st-note">
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
      </BvCard>

      <!-- Шаг 2 · два способа -->
      <div class="st-grid st-grid--2 st-grid--stretch">
        <BvCard title="2. По словам" class="st-in" :class="{ 'is-on': шаг >= 2 }">
          <template #actions>
            <span class="st-scope">найдено {{ num(слова['найдено']) }}</span>
          </template>
          <p v-if="!слова['первые'].length" class="st-note">Слов запроса в вакансиях нет.</p>
          <BvTable v-else label="Найдено по словам">
            <thead>
              <tr>
                <th class="col-num">Место</th>
                <th>Вакансия</th>
                <th>Где слово</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="запись in слова['первые']" :key="запись['ид']">
                <td class="col-num">{{ запись['место_по_словам'] }}</td>
                <td>
                  <div class="st-vac">
                    <span class="st-vac__name">{{ запись['название'] }}</span>
                    <span class="st-vac__company">{{ запись['компания'] }}</span>
                  </div>
                </td>
                <td>{{ запись['почему'] }}</td>
              </tr>
            </tbody>
          </BvTable>
          <p class="st-note">Точные названия — «Corona», «1С» — находятся только так: модель смысла их размывает.</p>
        </BvCard>

        <BvCard title="2. По смыслу" class="st-in" :class="{ 'is-on': шаг >= 2 }" :style="{ '--i': 2 }">
          <template #actions>
            <span class="st-scope">найдено {{ num(смысл['найдено']) }}</span>
          </template>
          <p v-if="оСмысле" class="st-note">{{ оСмысле }}</p>
          <template v-else>
            <BvTable label="Найдено по смыслу">
              <thead>
                <tr>
                  <th class="col-num">Место</th>
                  <th>Вакансия</th>
                  <th class="col-num">Близость</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="запись in смысл['первые']" :key="запись['ид']">
                  <td class="col-num">{{ запись['место_по_смыслу'] }}</td>
                  <td>
                    <div class="st-vac">
                      <span class="st-vac__name">{{ запись['название'] }}</span>
                      <span class="st-vac__company">{{ запись['компания'] }}</span>
                    </div>
                  </td>
                  <td class="col-num">{{ дробь((запись['близость'] ?? 0).toFixed(2)) }}</td>
                </tr>
              </tbody>
            </BvTable>
            <p class="st-note">
              Модель {{ смысл['модель'] }} работает на видеокарте этой машины; тексты наружу не уходят.
              Ниже близости {{ дробь(смысл['порог']) }} вакансия найденной не считается.
            </p>
          </template>
        </BvCard>
      </div>

      <!-- Шаг 3 · слияние -->
      <BvCard title="3. Списки слиты по местам" class="st-in" :class="{ 'is-on': шаг >= 3 }">
        <template #actions>
          <span class="st-scope">
            {{ num(итог['найдено']) }} {{ plural(итог['найдено'], 'вакансия', 'вакансии', 'вакансий') }} за
            <span class="mono-num">{{ данные['мс'] }}</span> мс
          </span>
        </template>
        <p v-if="!итог['первые'].length" class="st-note">
          Ничего не найдено: слов запроса в вакансиях нет, и по смыслу ни одна не подошла.
        </p>
        <template v-else>
          <BvTable label="Итог поиска">
            <thead>
              <tr>
                <th class="col-num">Место</th>
                <th>Вакансия</th>
                <th class="col-num">По словам</th>
                <th class="col-num">По смыслу</th>
                <th>Чей вклад</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(запись, i) in итог['первые']" :key="запись['ид']" class="st-in" :class="{ 'is-on': шаг >= 3 }" :style="{ '--i': i + 1 }">
                <td class="col-num">{{ i + 1 }}</td>
                <td>
                  <div class="st-vac">
                    <span class="st-vac__name">{{ запись['название'] }}</span>
                    <span class="st-vac__company">{{ запись['компания'] }}</span>
                  </div>
                </td>
                <!-- Откуда строка пришла — местами в двух списках. Прочерк: этим способом не найдена. -->
                <td class="col-num">
                  <template v-if="запись['место_по_словам']">{{ запись['место_по_словам'] }}</template>
                  <span v-else class="exp__none">—</span>
                </td>
                <td class="col-num">
                  <template v-if="запись['место_по_смыслу']">{{ запись['место_по_смыслу'] }}</template>
                  <span v-else class="exp__none">—</span>
                </td>
                <td>
                  <div class="exp__score" aria-hidden="true">
                    <span class="exp__part exp__part--words" :style="{ width: доли(запись).слова }"></span>
                    <span class="exp__part exp__part--sense" :style="{ width: доли(запись).смысл }"></span>
                  </div>
                </td>
              </tr>
            </tbody>
          </BvTable>

          <ul class="exp__legend" aria-hidden="true">
            <li><span class="exp__key exp__part--words"></span>от слов</li>
            <li><span class="exp__key exp__part--sense"></span>от смысла</li>
          </ul>

          <p class="st-note">
            Колонки «По словам» и «По смыслу» — место вакансии в каждом из двух списков. Каждый список даёт ей
            1 / ({{ данные.k }} + место), вклады складываются: найденное обоими способами встаёт выше найденного одним.
          </p>
        </template>
      </BvCard>
    </template>

    <!-- Качество: чем и на чём меряли. Без оговорок число обещало бы
         больше, чем за ним стоит. -->
    <BvCard v-if="качество.length" title="Насколько это точно">
      <template #actions>
        <span class="st-scope">
          замер от <span class="mono-num">{{ measure['когда'].split('-').reverse().join('.') }}</span>
        </span>
      </template>
      <BvBarList :items="качество" :format="(v) => v.toFixed(3).replace('.', ',')" />
      <p class="st-note">
        Качество первых десяти мест (nDCG@10, от 0 до 1) на эталоне: {{ measure['запросов'] }}
        {{ plural(measure['запросов'], 'запрос', 'запроса', 'запросов') }}, {{ num(measure['пар']) }} размеченных пар.
        Разметка — {{ measure['разметка'] }}.
      </p>
    </BvCard>
  </div>
</template>

<style scoped>
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

.exp__error {
  font-size: var(--t-caption-size);
  color: var(--c-status-err-text);
}

/* Группы запроса: варианты одного слова через «или», слова — через «и». */
.exp__groups {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.exp__join {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.exp__none { color: var(--c-text-quiet); }

/* Вклад в оценку: две ступени шкалы величин одной полосой. */
.exp__score {
  display: flex;
  width: 100%;
  min-width: 96px;
  height: var(--s-2);
  border-radius: var(--r-pill);
  overflow: hidden;
  background: var(--track-bar);
}

.exp__part { flex: 0 0 auto; height: 100%; }
.exp__part--words { background: var(--c-data-1); }
.exp__part--sense { background: var(--c-data-3); }

.exp__legend {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2) var(--s-5);
  font-size: var(--t-caption-size);
  color: var(--c-text-secondary);
}

.exp__legend li {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
}

.exp__key {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

@media (max-width: 767px) {
  .exp__form { grid-template-columns: minmax(0, 1fr); }
  .exp__form :deep(.btn) { margin-top: 0; }
}
</style>
