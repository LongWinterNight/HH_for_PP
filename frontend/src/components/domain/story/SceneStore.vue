<script setup>
import { computed } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvTable from '@/components/ui/BvTable.vue'
import { useScene } from '@/composables/useScene'
import { num, plural } from '@/utils/format'

// Хранение: во что превращается одна вакансия.
//
// Вакансия ложится в базу четырьмя видами, и каждый нужен своему
// потребителю: строка с полями — списку и фильтрам, сжатый текст —
// карточке и повторному разбору, слова — поиску по словам, вектор —
// поиску по смыслу. Все числа и сам вектор — этой вакансии.
const props = defineProps({
  // story['герой'] из /api/system/story.
  hero: { type: Object, default: null }
})

const ШАГОВ = 4
const сцена = useScene(ШАГОВ, { пауза: 900, готово: () => Boolean(props.hero) })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const х = computed(() => props.hero?.['хранение'] ?? null)

const поля = computed(() => {
  const в = props.hero
  if (!в) return []
  return [
    ['vacancy_name', в['название']],
    ['employer_name', в['компания']],
    ['area', в['регион']],
    ['salary_from_rub', в['зарплата']?.['от_руб'] != null ? num(Math.round(в['зарплата']['от_руб'])) : null],
    ['employment', в['занятость']],
    ['skill_count', String(в['навыки']?.length ?? 0)]
  ].filter(([, значение]) => значение)
})

const сжатие = computed(() => [
  { label: 'до сжатия', value: х.value?.['байт_текста'] ?? 0 },
  { label: 'в базе', value: х.value?.['байт_сжато'] ?? 0 }
])
const воСколько = computed(() => {
  const [было, стало] = сжатие.value
  return было.value && стало.value ? (было.value / стало.value).toFixed(1).replace('.', ',') : ''
})

// Вектор столбиками от нулевой линии: высота — величина числа, сторона —
// знак. Числа вектора по отдельности ничего не значат, и столбики
// показывают ровно это: отпечаток, а не шкалу.
const вектор = computed(() => {
  const числа = х.value?.['вектор'] ?? []
  const наибольшее = Math.max(...числа.map((число) => Math.abs(число)), 0.0001)
  // Столбик растёт от середины, поэтому наибольший занимает половину высоты.
  return числа.map((число) => ({ вверх: число >= 0, высота: `${Math.max(3, (Math.abs(число) / наибольшее) * 50)}%` }))
})

const байт = (значение) => `${num(значение)} байт`
</script>

<template>
  <div ref="корень">
    <p v-if="!х" class="st-note">В базе нет вакансии с текстом — показать хранение не на чем.</p>

    <div v-else class="st-grid st-grid--2 st-grid--stretch">
      <BvCard title="Строка таблицы" class="st-dim" :class="{ 'is-on': шаг >= 1 }">
        <template #actions>
          <span class="st-scope">{{ х['полей'] }} {{ plural(х['полей'], 'поле', 'поля', 'полей') }}</span>
        </template>
        <BvTable label="Поля вакансии в базе">
          <thead>
            <tr>
              <th>Поле</th>
              <th>Значение</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="[имя, значение] in поля" :key="имя">
              <!-- Имя колонки — код, а не слово: моноширинный здесь по правилу. -->
              <td><span class="mono-num">{{ имя }}</span></td>
              <td><span class="store__value">{{ значение }}</span></td>
            </tr>
          </tbody>
        </BvTable>
        <p class="st-note">По этим полям работают список, фильтры и аналитика.</p>
      </BvCard>

      <BvCard title="Текст описания" class="st-dim" :class="{ 'is-on': шаг >= 2 }">
        <template #actions>
          <span v-if="воСколько" class="st-scope">сжат в {{ воСколько }} раза</span>
        </template>
        <div class="store__grow" :class="{ 'is-on': шаг >= 2 }">
          <BvBarList :items="сжатие" :format="байт" />
        </div>
        <p class="st-note">
          Текст хранится сжатым и один раз на все копии вакансии по городам: тридцать городов — один текст.
        </p>
      </BvCard>

      <BvCard title="Слова для поиска" class="st-dim" :class="{ 'is-on': шаг >= 3 }">
        <template #actions>
          <span class="st-scope">{{ num(х['слов']) }} {{ plural(х['слов'], 'слово', 'слова', 'слов') }}</span>
        </template>
        <ul class="store__words">
          <li v-for="(слово, i) in х['слова']" :key="слово" class="st-in" :class="{ 'is-on': шаг >= 3 }" :style="{ '--i': i * 0.5 }">
            <BvChip variant="count">{{ слово }}</BvChip>
          </li>
          <li v-if="х['слов'] > х['слова'].length" class="st-in" :class="{ 'is-on': шаг >= 3 }" :style="{ '--i': х['слова'].length * 0.5 }">
            <BvChip variant="count">+{{ num(х['слов'] - х['слова'].length) }}</BvChip>
          </li>
        </ul>
        <p class="st-note">
          Слова лежат в начальной форме: «требуется» записано как «требоваться», и запрос в любой форме его найдёт.
        </p>
      </BvCard>

      <BvCard title="Вектор смысла" class="st-dim" :class="{ 'is-on': шаг >= 4 }">
        <template #actions>
          <span v-if="х['размерность']" class="st-scope">{{ num(х['размерность']) }} чисел · {{ х['модель'] }}</span>
        </template>
        <p v-if="!вектор.length" class="st-note">Вектор этой вакансии ещё не посчитан.</p>
        <template v-else>
          <div class="store__vector" :class="{ 'is-on': шаг >= 4 }" aria-hidden="true">
            <span v-for="(столбик, i) in вектор" :key="i" class="store__cell" :class="{ 'is-up': столбик.вверх }" :style="{ '--i': i }">
              <span class="store__stick" :style="{ height: столбик.высота }"></span>
            </span>
          </div>
          <p class="st-note">
            Первые {{ вектор.length }} чисел из {{ num(х['размерность']) }}. Близкие по смыслу вакансии дают похожий
            рисунок — по нему и ищет поиск по смыслу.
          </p>
        </template>
      </BvCard>
    </div>
  </div>
</template>

<style scoped>
.store__value {
  display: block;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--c-text);
}

/* Полосы растут от нуля: длина — мера, и её рост читается как измерение. */
.store__grow :deep(.bars__fill) {
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform var(--dur-enter) var(--ease-enter);
}

.store__grow.is-on :deep(.bars__fill) { transform: scaleX(1); }
.store__grow :deep(.bars__row:nth-child(2) .bars__fill) { transition-delay: var(--dur-panel); }

.store__words {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
}

/* Вектор: столбики растут из нулевой линии волной слева направо.
   Величины — ступенями шкалы данных: вверх тёмная, вниз светлее. */
.store__vector {
  position: relative;
  display: grid;
  grid-template-columns: repeat(64, minmax(0, 1fr));
  gap: 1px;
  height: 120px;
}

.store__vector::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 1px;
  background: var(--c-border-strong);
}

.store__cell {
  position: relative;
  display: block;
  height: 100%;
}

.store__stick {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  border-radius: 1px;
  background: var(--c-data-3);
  transform: scaleY(0);
  transform-origin: center top;
  transition: transform var(--dur-enter) var(--ease-enter);
  transition-delay: calc(var(--i) * 6ms);
}

.store__cell.is-up .store__stick {
  top: auto;
  bottom: 50%;
  background: var(--c-data-2);
  transform-origin: center bottom;
}

.store__vector.is-on .store__stick { transform: scaleY(1); }

@media (prefers-reduced-motion: reduce) {
  .store__grow :deep(.bars__fill),
  .store__stick { transition: none; }
}
</style>
