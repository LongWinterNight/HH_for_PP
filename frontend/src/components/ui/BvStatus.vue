<script setup>
import { computed } from 'vue'

// Единственный источник вида статуса на всю систему: состояние сбора,
// строка истории запусков, шаг процесса, состояние отчёта.
//
// Внешний вид целиком приходит из tokens.css, где .status описан вместе
// с двумя подачами: от 1024px пилюля с подложкой, ниже — точка и слово.
// Здесь только выбор тона и форма точки, поэтому четырёх вариантов
// статуса под четыре экрана в проекте не заведётся.
//
// Слово обязательно и присутствует в обеих подачах: цвет никогда не
// единственный носитель смысла.
const props = defineProps({
  kind: {
    type: String,
    required: true,
    validator: (v) => ['idle', 'run', 'ok', 'err', 'stop'].includes(v)
  },
  // Одно слово. Длинное состояние ломает колонку таблицы — это уже
  // случалось с формулировкой «Удалится через 2 дня».
  label: { type: String, required: true }
})

// «Остановлен» делит тон с ожиданием и отличается формой точки —
// пустая с обводкой, а не оттенком: разницу оттенков в строке таблицы
// не видит никто.
const toneClass = computed(() => (props.kind === 'stop' ? 'is-idle' : `is-${props.kind}`))
</script>

<template>
  <span class="status" :class="toneClass">
    <span class="dot" :class="[`dot--${kind}`, { 'dot--hollow': kind === 'stop' }]" aria-hidden="true"></span>
    {{ label }}
  </span>
</template>

<style scoped>
.dot--ok { background: var(--c-status-ok-dot); }
.dot--run { background: var(--c-status-run-dot); }
.dot--err { background: var(--c-status-err-dot); }
.dot--idle { background: var(--c-status-idle-dot); }

/* «Не начат» и «остановлен» различаются формой точки, а не оттенком:
   разницу оттенков в строке таблицы не видит никто. */
.dot--hollow {
  background: transparent;
  box-shadow: var(--c-status-idle-ring);
}

/* В широкой подаче у нейтральных статусов нет подложки, и без контура
   пилюля превращалась бы в обычный текст: форму держит обводка. */
@media (min-width: 1024px) {
  .status.is-idle { box-shadow: var(--c-status-idle-ring); }
}
</style>
