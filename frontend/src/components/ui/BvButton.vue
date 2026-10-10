<script setup>
// Кнопка системы. Четыре вида и три высоты — 40 / 32 / 28.
//
// Главная (primary) на экране одна: та, ради которой пользователь пришёл.
// Это правило применения, компонент его не стережёт, но и не поощряет —
// вид приходится называть явно.
//
// Выключенная кнопка по правилам форм сопровождается объяснением рядом,
// поэтому у неё есть слот причины: без него disabled выглядит поломкой.
//
// У кнопки в работе место под знак занятости зарезервировано заранее:
// главное действие держит min-width, и при переходе «Запустить сбор» →
// «Собираем…» ширина не меняется. Прыгающая кнопка уводит курсор с
// цели ровно в тот момент, когда по ней собирались нажать второй раз.
defineProps({
  variant: {
    type: String,
    default: 'secondary',
    validator: (v) => ['primary', 'secondary', 'quiet', 'danger'].includes(v)
  },
  size: {
    type: String,
    default: 'lg',
    validator: (v) => ['lg', 'md', 'sm'].includes(v)
  },
  type: { type: String, default: 'button' },
  disabled: { type: Boolean, default: false },
  // Кнопка в работе: показывает, что действие идёт, и не даёт нажать
  // повторно. Ширина при этом не меняется — см. правило ниже.
  loading: { type: Boolean, default: false }
})
</script>

<template>
  <button
    :type="type"
    class="btn"
    :class="[`btn--${variant}`, `btn--${size}`, { 'is-loading': loading }]"
    :disabled="disabled || loading"
    :aria-busy="loading ? 'true' : undefined"
  >
    <span v-if="loading" class="btn__spinner" aria-hidden="true"></span>
    <!-- Содержимое обёрнуто: у второстепенной кнопки знак занятости встаёт
         поверх него, и скрывать нужно именно содержимое. Текстовый узел
         из слота скрыть нельзя — стилю не за что зацепиться. -->
    <span class="btn__label"><slot /></span>
  </button>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  border: none;
  border-radius: var(--r-md);
  font-family: var(--font-sans);
  font-weight: var(--w-medium);
  white-space: nowrap;
  cursor: pointer;
  transition: var(--t-hover);
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* Главное действие держит ширину: место под знак занятости отведено
   заранее, поэтому переход в работу не двигает кнопку под курсором. */
.btn--primary {
  min-width: 168px;
}

/* Обёртка содержимого не меняет раскладку: она наследует выравнивание и
   промежуток кнопки, поэтому текст с иконкой стоят как стояли. */
.btn__label {
  display: inline-flex;
  align-items: center;
  gap: inherit;
}

/* Знак занятости: кольцо с разрывом. Вращение отключается системной
   настройкой — правило prefers-reduced-motion в токенах гасит длительность,
   поэтому здесь достаточно обычной анимации. */
.btn__spinner {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  opacity: 0.8;
  animation: btn-spin 0.7s linear infinite;
}

@keyframes btn-spin {
  to { transform: rotate(360deg); }
}

/* Кнопка в работе остаётся читаемой: она не выключена по смыслу, а
   занята, и приглушать её как недоступную неверно. */
.btn.is-loading:disabled {
  opacity: 1;
  cursor: progress;
}

/* Ширина не должна прыгать ни у одной кнопки, а не только у главной.
   Главное действие держит min-width и показывает знак занятости рядом с
   текстом: «Запустить сбор» → «Собираем…». У второстепенных запаса нет —
   их ширина равна тексту, — поэтому там знак занятости встаёт поверх
   содержимого, а не рядом с ним. Кнопка остаётся ровно той же ширины,
   курсор не уезжает с цели. */
.btn:not(.btn--primary).is-loading {
  position: relative;
}

.btn:not(.btn--primary).is-loading .btn__label {
  visibility: hidden;
}

.btn:not(.btn--primary) .btn__spinner {
  position: absolute;
  left: 50%;
  top: 50%;
  margin: -7px 0 0 -7px;
}

/* --- Высоты. Ниже 28px система не опускается: на касании цель
       добирается отступом вокруг, а не уменьшением кнопки. --- */
.btn--lg { height: var(--h-control-lg); padding: 0 var(--s-4); font-size: var(--t-ui-size); }
.btn--md { height: var(--h-control-md); padding: 0 var(--s-3); font-size: var(--t-ui-size); }
.btn--sm { height: var(--h-control-sm); padding: 0 10px; font-size: var(--t-caption-size); }

/* --- Главная: одно из двух окрашенных мест экрана --- */
.btn--primary {
  background: var(--c-accent);
  color: var(--c-surface);
}
.btn--primary:hover:not(:disabled) { background: var(--c-accent-hover); }

/* --- Вторичная: граница вместо заливки, чтобы не спорить с главной --- */
.btn--secondary {
  background: transparent;
  box-shadow: var(--border-strong);
  color: var(--c-text);
}
.btn--secondary:hover:not(:disabled) { background: var(--c-surface); }

/* --- Текстовая: действие второго порядка, «Все вакансии →» --- */
.btn--quiet {
  background: transparent;
  color: var(--c-text-secondary);
  padding-left: var(--s-2);
  padding-right: var(--s-2);
}
.btn--quiet:hover:not(:disabled) {
  background: var(--c-surface-hover);
  color: var(--c-text);
}

/* --- Опасная: только для необратимого, и всегда за подтверждением
       вводом слова. Красная заливка сама по себе ничего не защищает. --- */
.btn--danger {
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--c-negative);
  color: var(--c-negative);
}
.btn--danger:hover:not(:disabled) { background: var(--c-status-err-bg); }
</style>
