<script setup>
import { computed } from 'vue'
import { num } from '@/utils/format'

// Вилки по категориям: где лежит половина значений и где их середина.
//
// Нужен там, где одного числа на категорию мало. «Медиана у новичков
// 70 000» ничего не говорит о том, сходятся ли предложения к этой сумме
// или разбросаны от тридцати до ста пятидесяти. Полоса от нижнего
// квартиля до верхнего показывает разброс, отметка на ней — медиану, и
// всё это на одной шкале, поэтому категории сравниваются взглядом.
//
// Собран вёрсткой, как `BvBarList`: список доступен программам чтения
// экрана, переносится в печать и читается без курсора — значение
// медианы и объём выборки напечатаны рядом с полосой.
//
// Жёлтого здесь нет. Маркер в системе один на график и означает одно
// выделенное значение; у этого списка медиан столько же, сколько строк.
const props = defineProps({
  // [{ label, q1, median, q3, sample, weak }] — порядок задаёт вызывающий.
  items: { type: Array, required: true },
  // Как напечатать сумму. По умолчанию — число с разрядами.
  format: { type: Function, default: null },
  // Строки можно выбирать: нажатие сужает окно до этой категории.
  selectable: { type: Boolean, default: false },
  // Подпись выбранной строки. Выбор не убирает остальные строки: список
  // остаётся и сравнением, и переключателем, а повторное нажатие на
  // выбранную строку снимает выбор.
  selected: { type: String, default: '' }
})

defineEmits(['select'])

// Шкала общая и идёт от нуля: длина полосы тогда сравнима между
// строками, а положение — между категориями.
const предел = computed(() => Math.max(...props.items.filter((с) => !с.weak).map((с) => с.q3), 1))

function доля(значение) {
  return `${Math.min(100, (значение / предел.value) * 100)}%`
}

function подсказка(строка) {
  if (!props.selectable || строка.weak) return undefined
  return props.selected === строка.label
    ? 'Нажмите ещё раз, чтобы вернуть все строки'
    : `Показать только «${строка.label}»`
}

function сумма(значение) {
  return props.format ? props.format(значение) : num(Math.round(значение))
}
</script>

<template>
  <div class="ranges-box">
  <ul class="ranges">
    <li v-for="строка in items" :key="строка.label" class="ranges__item">
      <component
        :is="selectable && !строка.weak ? 'button' : 'div'"
        class="ranges__row"
        :class="{
          'is-weak': строка.weak,
          'is-button': selectable && !строка.weak,
          'is-selected': selectable && selected === строка.label,
          'is-dimmed': selectable && selected && selected !== строка.label
        }"
        :type="selectable && !строка.weak ? 'button' : undefined"
        :aria-pressed="selectable && !строка.weak ? selected === строка.label : undefined"
        :title="подсказка(строка)"
        @click="selectable && !строка.weak && $emit('select', строка)"
      >
        <span class="ranges__label">{{ строка.label }}</span>
        <span class="ranges__track" aria-hidden="true">
          <template v-if="!строка.weak">
            <span
              class="ranges__band"
              :style="{ left: доля(строка.q1), width: `calc(${доля(строка.q3)} - ${доля(строка.q1)})` }"
            ></span>
            <span class="ranges__mark" :style="{ left: доля(строка.median) }"></span>
          </template>
        </span>
        <span v-if="строка.weak" class="ranges__value ranges__value--weak">мало данных</span>
        <span v-else class="ranges__value">
          {{ сумма(строка.median) }}
          <span class="ranges__spread">{{ сумма(строка.q1) }} — {{ сумма(строка.q3) }}</span>
        </span>
        <span class="ranges__n">по {{ num(строка.sample) }}</span>
      </component>
    </li>
  </ul>
  </div>
</template>

<style scoped>
/* Обёртка меряет ширину: по ней, а не по экрану, список решает, как
   ему встать. Мерить саму сетку нельзя — контейнер не может зависеть от
   собственного содержимого. */
.ranges-box {
  container: ranges / inline-size;
  min-width: 0;
}

/* Колонки заданы один раз на весь список, строки берут их через subgrid.
   Пока сетка была у каждой строки своя, колонка полосы подстраивалась
   под ширину числа в этой строке, и шкала у строк выходила разной —
   вилки, которые список обещает сравнить взглядом, были несравнимы. */
.ranges {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: minmax(80px, 170px) minmax(120px, 1fr) auto minmax(56px, auto);
  column-gap: var(--s-3);
  row-gap: var(--s-1);
}

.ranges__item {
  display: grid;
  grid-template-columns: subgrid;
  grid-column: 1 / -1;
}

.ranges__row {
  /* Поля входят в ширину строки. Без этого строка-кнопка помещалась, а
     невыбираемая строка — обычный блок — выходила за контейнер на свои
     же поля и обрезалась границей карточки. */
  box-sizing: border-box;
  width: 100%;
  display: grid;
  grid-template-columns: subgrid;
  grid-column: 1 / -1;
  align-items: center;
  padding: var(--s-2) var(--s-2);
  border: none;
  background: transparent;
  font-family: var(--font-sans);
  font-size: var(--t-ui-size);
  text-align: left;
  color: inherit;
}

.ranges__row.is-button {
  cursor: pointer;
  border-radius: var(--r-xs);
  transition: var(--t-hover);
}

.ranges__row.is-button:hover { background: var(--c-surface-sunken); }

/* Выбранная строка помечена поверхностью и весом, а не цветом — как
   выбранный сегмент переключателя. Остальные приглушены, но остаются
   на месте: по ним видно, с чем выбранная сравнивается и куда нажать,
   чтобы переключиться. */
.ranges__row.is-selected {
  background: var(--c-surface-sunken);
  box-shadow: var(--border);
}

.ranges__row.is-selected .ranges__label {
  color: var(--c-text);
  font-weight: var(--w-medium);
}

.ranges__row.is-dimmed { opacity: 0.55; }
.ranges__row.is-dimmed:hover,
.ranges__row.is-dimmed:focus-visible { opacity: 1; }

.ranges__label {
  color: var(--c-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ranges__track {
  position: relative;
  height: var(--s-2);
  border-radius: var(--r-pill);
  background: var(--track-bar);
}

.ranges__band {
  position: absolute;
  top: 0;
  bottom: 0;
  min-width: 2px;
  border-radius: var(--r-pill);
  background: var(--c-data-2);
}

/* Отметка медианы выше полосы и темнее её: середина должна читаться
   раньше, чем границы. */
.ranges__mark {
  position: absolute;
  top: -4px;
  bottom: -4px;
  width: 3px;
  margin-left: -1.5px;
  border-radius: 2px;
  background: var(--c-data-1);
  box-shadow: 0 0 0 1px var(--c-surface);
}

.ranges__value {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.ranges__spread {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.ranges__value--weak { color: var(--c-text-quiet); }

.ranges__n {
  text-align: right;
  color: var(--c-text-muted);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.is-weak .ranges__label { color: var(--c-text-quiet); }

/* В узком месте подпись занимает свою строку целиком: усечённое
   название сферы не опознаётся. Меряется ширина списка, а не экрана:
   карточка в трёхколоночной сетке на широком экране уже телефона, и по
   ширине экрана список в ней не перестраивался — «по N» выходило за край. */
@container ranges (max-width: 480px) {
  /* Две колонки: «по N» уходит наверх, к подписи, и полоса получает
     его место — в три колонки от неё оставалось полсотни точек. */
  .ranges { grid-template-columns: minmax(40px, 1fr) auto; }

  .ranges__row { row-gap: var(--s-1); }
  .ranges__n { grid-area: 1 / 2; }
  .ranges__track { grid-area: 2 / 1; }
  .ranges__value { grid-area: 2 / 2; }

  /* Подпись идёт на всю строку и оставляет справа место под «по N»:
     в одной первой колонке она переносилась при свободной строке. */
  .ranges__label {
    grid-area: 1 / 1 / 2 / -1;
    padding-right: 5.5em;
    white-space: normal;
  }
}
</style>
