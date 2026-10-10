<script setup>
// Таблица данных: вакансии, история сборов, зарплаты по валютам,
// отчёты. Строки и колонки задаёт вызывающий экран, компонент отвечает
// за поведение, одинаковое во всех таблицах продукта.
//
// Разделители вместо теней, hover подсвечивает всю строку целиком —
// иначе на двадцатой строке глаз теряет строку при движении вправо.
//
// На узком экране таблица прокручивается вбок, а первая колонка может
// остаться на месте: без названия вакансии остальные колонки — набор
// чисел неизвестно о чём. На печати прокрутка снимается атрибутом
// data-print-full, описанным в tokens.css: на бумаге она обрезала бы
// колонки вместо переноса.
defineProps({
  // Название таблицы для программ чтения экрана.
  label: { type: String, required: true },
  // Липкая первая колонка. Нужна там, где строка длиннее экрана.
  stickyFirst: { type: Boolean, default: false }
})
</script>

<template>
  <div class="table-wrap" :class="{ 'is-sticky-first': stickyFirst }" data-print-full>
    <table class="table" :aria-label="label">
      <slot />
    </table>
  </div>
</template>

<style scoped>
.table-wrap {
  width: 100%;
  overflow-x: auto;
  background: var(--c-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--border);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--t-ui-size);
  color: var(--c-text-secondary);
}

/* Шапка утоплена, а не окрашена: цвет в системе занят двумя местами. */
.table :deep(thead th) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--c-surface-sunken);
  padding: var(--s-3) var(--s-4);
  text-align: left;
  font-size: var(--t-label-alt-size);
  line-height: var(--t-label-alt-lh);
  font-weight: var(--w-medium);
  color: var(--c-text-muted);
  white-space: nowrap;
  box-shadow: inset 0 -1px 0 var(--c-border);
}

/* Ячейкам нельзя задавать max-width и display: flex — ширину колонок
   считает браузер по табличным правилам, и ячейка, которая из них
   выпала, не растягивается до своей колонки. Между ними остаётся полоса
   без содержимого и без фона: подсветка строки рвётся, и это выглядит
   как пропавший столбец. Ограничивать ширину и раскладывать содержимое
   нужно внутри ячейки, отдельным блоком. */
.table :deep(tbody td) {
  padding: var(--s-3) var(--s-4);
  vertical-align: middle;
  box-shadow: inset 0 -1px 0 var(--c-border);
}

.table :deep(tbody tr:last-child td) { box-shadow: none; }

/* Фон живёт на строке, а не на ячейках.

   Это не стилистический выбор, а защита от дефекта, который случился
   дважды. Липкая первая колонка обязана иметь непрозрачный фон, иначе
   при горизонтальной прокрутке сквозь неё просвечивает текст. Когда
   этот фон задан на самой ячейке, он перебивает по специфичности любое
   состояние строки, заданное снаружи: сначала пришлось отдельным
   правилом чинить наведение, потом выделение строки в «Вакансиях» — у
   выбранной строки первая ячейка оставалась белой, и выделение
   обрывалось посреди таблицы.

   Строка красится сама, липкая ячейка наследует её фон — и любое новое
   состояние (выбрано, отмечено, только что изменено) работает без
   правки этого файла. */
.table :deep(tbody tr) { background: var(--c-surface); }
.table :deep(tbody tr:hover) { background: var(--c-surface-hover); }

/* Числовая колонка: правый край и табличные цифры, иначе разряды
   не выстраиваются и суммы невозможно сравнить взглядом. */
.table :deep(.col-num) {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* Первая колонка остаётся на месте при горизонтальной прокрутке.

   Фон наследуется от строки — см. правило выше. Так липкая ячейка
   остаётся непрозрачной, но не спорит с состояниями строки. */
.is-sticky-first .table :deep(thead th:first-child),
.is-sticky-first .table :deep(tbody td:first-child) {
  position: sticky;
  left: 0;
  z-index: 2;
  background: inherit;
}

.is-sticky-first .table :deep(thead th:first-child) {
  z-index: 3;
  background: var(--c-surface-sunken);
}
</style>
