<script setup>
// Чип: навык вакансии, выбранный фильтр, счётчик остатка.
//
// Пастель здесь означает категорию, а не величину: в чёрно-белой
// печати пять пастельных оттенков сливаются, поэтому текстовая метка
// внутри чипа обязательна и цвет ничего не сообщает в одиночку.
//
// Счётчик остатка («+12») никогда не усекается — усекается название
// навыка: знание о том, что скрыто ещё двенадцать, дороже полного
// написания одного из них.
defineProps({
  variant: {
    type: String,
    default: 'skill',
    validator: (v) => ['skill', 'filter', 'count'].includes(v)
  },
  // Кнопка снятия у чипа фильтра.
  removable: { type: Boolean, default: false },
  removeLabel: { type: String, default: 'Убрать' }
})

defineEmits(['remove'])
</script>

<template>
  <span class="chip" :class="`chip--${variant}`">
    <span class="chip__text"><slot /></span>
    <button
      v-if="removable"
      type="button"
      class="chip__remove"
      :aria-label="removeLabel"
      @click="$emit('remove')"
    >✕</button>
  </span>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  max-width: 100%;
  height: var(--h-control-sm);
  padding: 0 var(--s-2);
  border-radius: var(--r-xs);
  font-size: var(--t-caption-size);
  color: var(--c-text);
}

.chip__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Навык — пастельная категория. */
.chip--skill { background: var(--c-cat-1); }

/* Выбранный фильтр — подложка активного состояния: он относится
   к управлению экраном, а не к данным строки. */
.chip--filter {
  background: var(--c-accent-subtle);
  color: var(--c-accent);
}

/* Счётчик остатка: не категория и не фильтр, поэтому без пастели. */
.chip--count {
  background: transparent;
  box-shadow: var(--border);
  color: var(--c-text-muted);
  font-variant-numeric: tabular-nums;
  flex: 0 0 auto;
}

.chip__remove {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  padding: 0;
  color: inherit;
  font-size: var(--t-caption-size);
  line-height: 1;
  cursor: pointer;
  opacity: 0.7;
}

.chip__remove:hover { opacity: 1; }

/* Знак остаётся маленьким, а нажимается область вокруг него: крестик в
   11×13 px пальцем не попасть, а увеличить сам знак значило бы раздуть
   чип. Область выходит за границы кнопки на невидимый псевдоэлемент. */
.chip__remove { position: relative; }
.chip__remove::after {
  content: '';
  position: absolute;
  inset: -12px -10px;
}
</style>
