<script setup>
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'

// Глава экрана «Как устроено»: один шаг пути вакансии.
//
// Карточка системы с номером шага, вопросом, на который глава отвечает,
// и сценой. Номер здесь не украшение: главы идут в том порядке, в
// каком система работает с вакансией.
defineProps({
  id: { type: String, required: true },
  number: { type: Number, required: true },
  title: { type: String, required: true },
  // Вопрос, на который отвечает глава, — словами человека, а не системы.
  question: { type: String, default: '' },
  // Сцена сейчас проигрывается: повтор на это время выключен.
  playing: { type: Boolean, default: false },
  // У главы есть сцена, которую можно проиграть ещё раз.
  replayable: { type: Boolean, default: true }
})

defineEmits(['replay'])
</script>

<template>
  <BvCard :id="`chapter-${id}`" class="chapter" :data-chapter="id">
    <header class="chapter__head">
      <span class="chapter__num" aria-hidden="true">{{ String(number).padStart(2, '0') }}</span>
      <div class="chapter__titles">
        <h2 class="chapter__title">{{ title }}</h2>
        <p v-if="question" class="chapter__question">{{ question }}</p>
      </div>
      <BvButton v-if="replayable" size="sm" :disabled="playing" @click="$emit('replay')">Повторить</BvButton>
    </header>
    <slot />
  </BvCard>
</template>

<style scoped>
/* Переход по главе из рельса не должен прятать её заголовок под шапку. */
.chapter { scroll-margin-top: calc(var(--h-header) + var(--s-16)); }

.chapter__head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--s-4);
}

.chapter__num {
  font-family: var(--font-mono);
  font-size: var(--t-caption-size);
  line-height: var(--t-h2-lh);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-muted);
}

.chapter__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.chapter__title {
  font-size: var(--t-h2-size);
  line-height: var(--t-h2-lh);
  letter-spacing: var(--t-h2-ls);
  font-weight: var(--w-strong);
  color: var(--c-text);
}

.chapter__question {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
  max-width: 72ch;
}

@media (max-width: 767px) {
  .chapter__head { grid-template-columns: minmax(0, 1fr) auto; }
  .chapter__num { display: none; }
  .chapter__title { font-size: var(--t-h3-size); line-height: var(--t-h3-lh); }
}
</style>
