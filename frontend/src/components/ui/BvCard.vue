<script setup>
// Карточка: блок дашборда, панель фильтров, рамка графика.
//
// Границей, а не тенью: единственная тень системы принадлежит
// всплывающему — подсказке автокомплита, меню, модалке. Карточка
// с тенью начинает выглядеть всплывающей и спорит с ними за внимание.
defineProps({
  // Подпись блока над содержимым. Идёт основным шрифтом, строчными:
  // заглавные с разрядкой заставляют разбирать слово по буквам.
  title: { type: String, default: '' },
  // Тесная карточка для плиток KPI и мелких блоков.
  tight: { type: Boolean, default: false }
})
</script>

<template>
  <section class="card" :class="{ 'card--tight': tight }">
    <header v-if="title || $slots.actions" class="card__head">
      <h2 v-if="title" class="card__title">{{ title }}</h2>
      <div v-if="$slots.actions" class="card__actions">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
}

.card--tight { padding: var(--pad-card-tight); }

.card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-4);
  flex-wrap: wrap;
}

.card__title {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  letter-spacing: var(--t-h3-ls);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.card__actions {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
</style>
