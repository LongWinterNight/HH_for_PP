<script setup>
import BvButton from '@/components/ui/BvButton.vue'

// Глава экрана «Как устроено»: один шаг пути вакансии.
//
// Раздел на холсте, а не карточка: карточки системы лежат внутри него
// сеткой, как на «Дашборде», и друг в друга не вкладываются. Порядок
// глав повторяет порядок, в котором система работает с вакансией.
defineProps({
  id: { type: String, required: true },
  number: { type: Number, required: true },
  // Сколько всего шагов в пути: «шаг 3 из 7» говорит, далеко ли до конца.
  total: { type: Number, default: 7 },
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
  <section :id="`chapter-${id}`" class="chapter" :data-chapter="id" :aria-labelledby="`chapter-${id}-title`">
    <header class="chapter__head">
      <div class="chapter__titles">
        <span class="label">Шаг {{ number }} из {{ total }}</span>
        <h2 :id="`chapter-${id}-title`">{{ title }}</h2>
        <p v-if="question" class="chapter__question">{{ question }}</p>
      </div>
      <div v-if="replayable || $slots.aside" class="chapter__aside">
        <!-- Состояние, относящееся к главе: например, поднята ли модель поиска. -->
        <slot name="aside" />
        <BvButton v-if="replayable" size="sm" :disabled="playing" @click="$emit('replay')">Показать ещё раз</BvButton>
      </div>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.chapter {
  display: flex;
  flex-direction: column;
  gap: var(--gap-grid);
  min-width: 0;
  /* Переход к главе не прячет её заголовок под шапку и ленту глав. */
  scroll-margin-top: calc(var(--h-header) + var(--s-16));
}

.chapter__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.chapter__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.chapter__question { color: var(--c-text-secondary); }

.chapter__aside {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-3);
}
</style>
