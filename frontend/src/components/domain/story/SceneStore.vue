<script setup>
import { computed } from 'vue'
import StoryNumber from '@/components/domain/story/StoryNumber.vue'
import { useScene } from '@/composables/useScene'
import { num } from '@/utils/format'

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
const сцена = useScene(ШАГОВ, { пауза: 1300, готово: () => Boolean(props.hero) })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const х = computed(() => props.hero?.['хранение'] ?? null)

const поля = computed(() => {
  const в = props.hero
  if (!в) return []
  return [
    ['vacancy_name', в['название']],
    ['area', в['регион']],
    ['salary_from_rub', в['зарплата']?.['от_руб'] != null ? num(Math.round(в['зарплата']['от_руб'])) : null],
    ['employment', в['занятость']],
    ['skill_count', String(в['навыки']?.length ?? 0)]
  ].filter(([, значение]) => значение)
})

const сжатие = computed(() => {
  const было = х.value?.['байт_текста'] || 0
  const стало = х.value?.['байт_сжато'] || 0
  return { доля: было ? `${(стало / было) * 100}%` : '0%', раз: было && стало ? (было / стало).toFixed(1).replace('.', ',') : '' }
})

// Вектор столбиками от нулевой линии: высота — величина числа, сторона —
// знак. Числа вектора по отдельности ничего не значат, и столбики
// показывают ровно это: отпечаток, а не шкалу.
const вектор = computed(() => {
  const числа = х.value?.['вектор'] ?? []
  const наибольшее = Math.max(...числа.map((число) => Math.abs(число)), 0.0001)
  return числа.map((число) => ({ вверх: число >= 0, высота: `${Math.max(3, (Math.abs(число) / наибольшее) * 50)}%` }))
})

const класс = (номер) => ({ 'is-run': шаг.value === номер && идёт.value, 'is-on': шаг.value >= номер })
</script>

<template>
  <div ref="корень" class="store">
    <p v-if="!х" class="store__note">В базе нет вакансии с текстом — показать хранение не на чем.</p>

    <ol v-else class="store__shelves" aria-label="В каком виде вакансия лежит в базе">
      <li class="store__shelf" :class="класс(1)">
        <header class="store__head">
          <h3 class="store__title">Строка таблицы</h3>
          <span class="store__figure"><StoryNumber :value="х['полей']" :active="шаг >= 1" /> полей</span>
        </header>
        <dl class="store__fields">
          <template v-for="([имя, значение], i) in поля" :key="имя">
            <dt :style="{ '--i': i }">{{ имя }}</dt>
            <dd :style="{ '--i': i }">{{ значение }}</dd>
          </template>
        </dl>
        <p class="store__text">По этим полям работают список, фильтры и аналитика.</p>
      </li>

      <li class="store__shelf" :class="класс(2)">
        <header class="store__head">
          <h3 class="store__title">Текст описания</h3>
          <span class="store__figure"><StoryNumber :value="х['байт_сжато']" :active="шаг >= 2" /> байт</span>
        </header>
        <div class="store__bars" aria-hidden="true">
          <span class="store__bar store__bar--raw"></span>
          <span class="store__bar store__bar--packed" :style="{ width: шаг >= 2 ? сжатие.доля : '100%' }"></span>
        </div>
        <p class="store__text">
          Было {{ num(х['байт_текста']) }} байт, после сжатия — в {{ сжатие.раз }} раза меньше. Текст хранится один раз
          на все копии вакансии по городам.
        </p>
      </li>

      <li class="store__shelf" :class="класс(3)">
        <header class="store__head">
          <h3 class="store__title">Слова для поиска</h3>
          <span class="store__figure"><StoryNumber :value="х['слов']" :active="шаг >= 3" /> слов</span>
        </header>
        <ul class="store__words">
          <li v-for="(слово, i) in х['слова']" :key="слово" class="store__word" :style="{ '--i': i }">{{ слово }}</li>
          <li class="store__word store__word--more" :style="{ '--i': х['слова'].length }">…</li>
        </ul>
        <p class="store__text">
          Слова в начальной форме: «требуется» лежит как «требоваться», и запрос в любой форме его найдёт.
        </p>
      </li>

      <li class="store__shelf" :class="класс(4)">
        <header class="store__head">
          <h3 class="store__title">Вектор смысла</h3>
          <span class="store__figure"><StoryNumber :value="х['размерность']" :active="шаг >= 4" /> чисел</span>
        </header>
        <p v-if="!вектор.length" class="store__text">Вектор этой вакансии ещё не посчитан.</p>
        <template v-else>
          <div class="store__vector" aria-hidden="true">
            <span v-for="(столбик, i) in вектор" :key="i" class="store__cell" :class="{ 'is-up': столбик.вверх }" :style="{ '--i': i }">
              <span class="store__stick" :style="{ height: столбик.высота }"></span>
            </span>
          </div>
          <p class="store__text">
            Первые {{ вектор.length }} из {{ num(х['размерность']) }} чисел, которыми модель {{ х['модель'] }} записала
            смысл вакансии. Близкие по смыслу вакансии дают похожий рисунок.
          </p>
        </template>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.store__shelves {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--s-5);
}

.store__shelf {
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

.store__shelf.is-on { opacity: 1; }
.store__shelf.is-run { background: var(--c-status-run-bg); box-shadow: inset 0 0 0 1px var(--c-status-run-dot); }

.store__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}

.store__title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.store__figure {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  white-space: nowrap;
}

.store__figure :deep(.story-num) {
  font-size: var(--t-h3-size);
  font-weight: var(--w-strong);
  color: var(--c-text);
}

.store__text,
.store__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

/* Поля: имя колонки моноширинным, значение обычным. */
.store__fields {
  margin: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--s-1) var(--s-4);
  min-height: 116px;
  align-content: start;
}

.store__fields dt,
.store__fields dd {
  opacity: 0;
  transform: translateY(4px);
  transition: opacity var(--dur-panel) var(--ease-enter), transform var(--dur-panel) var(--ease-enter);
  transition-delay: calc(var(--i) * 90ms);
}

.store__fields dt {
  font-family: var(--font-mono);
  font-size: var(--t-label-alt-size);
  line-height: var(--t-ui-lh);
  color: var(--c-text-muted);
}

.store__fields dd {
  margin: 0;
  font-size: var(--t-ui-size);
  color: var(--c-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.store__shelf.is-on .store__fields dt,
.store__shelf.is-on .store__fields dd { opacity: 1; transform: none; }

/* Сжатие: вторая полоса сжимается на глазах до своей настоящей доли. */
.store__bars {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-height: 116px;
  justify-content: center;
}

.store__bar {
  display: block;
  height: 12px;
  border-radius: var(--r-pill);
}

.store__bar--raw { width: 100%; background: var(--c-border-strong); }
.store__bar--packed { background: var(--c-text); transition: width 900ms var(--ease-enter); }

.store__words {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
  min-height: 116px;
  align-content: flex-start;
}

.store__word {
  padding: 2px var(--s-2);
  border-radius: var(--r-xs);
  box-shadow: var(--border-strong);
  font-family: var(--font-mono);
  font-size: var(--t-label-alt-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
  opacity: 0;
  transform: translateY(4px);
  transition: opacity var(--dur-ui) var(--ease-enter), transform var(--dur-ui) var(--ease-enter);
  transition-delay: calc(var(--i) * 55ms);
}

.store__word--more { box-shadow: none; color: var(--c-text-muted); }
.store__shelf.is-on .store__word { opacity: 1; transform: none; }

/* Вектор: столбики растут из нулевой линии волной слева направо. */
.store__vector {
  position: relative;
  display: grid;
  grid-template-columns: repeat(64, minmax(0, 1fr));
  gap: 1px;
  height: 116px;
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
  background: var(--c-text-muted);
  transform: scaleY(0);
  transform-origin: center top;
  transition: transform 420ms var(--ease-enter);
  transition-delay: calc(var(--i) * 12ms);
}

.store__cell.is-up .store__stick {
  top: auto;
  bottom: 50%;
  background: var(--c-text);
  transform-origin: center bottom;
}

.store__shelf.is-on .store__stick { transform: scaleY(1); }

@media (max-width: 1023px) {
  .store__shelves { grid-template-columns: minmax(0, 1fr); }
  .store__fields,
  .store__bars,
  .store__words { min-height: 0; }
}

@media (max-width: 767px) {
  .store__shelf { padding: var(--s-4); }
}

@media (prefers-reduced-motion: reduce) {
  .store__shelf,
  .store__fields dt,
  .store__fields dd,
  .store__bar--packed,
  .store__word,
  .store__stick { transition: none !important; }
}
</style>
