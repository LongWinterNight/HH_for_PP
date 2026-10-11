<script setup>
import { computed, nextTick, ref, watch } from 'vue'

// Рельс глав: где сейчас вакансия и что с ней уже сделано.
//
// Главы экрана — шаги одного пути, и рельс показывает его целиком:
// пройденное, текущее и то, что впереди. Под пройденными главами
// остаётся по строке — что система на этом шаге узнала о вакансии. К
// концу экрана рядом с текстом собирается её полная история.
//
// На широком экране рельс стоит сбоку и не уезжает при прокрутке; на
// узком — лентой под шапкой, с одной строкой о текущей главе.
const props = defineProps({
  // [{ id, number, title }] — в порядке пути.
  chapters: { type: Array, required: true },
  active: { type: String, default: '' },
  // Вакансия-пример: её название стоит в заголовке рельса.
  hero: { type: Object, default: null },
  // { id главы: что узнали о вакансии на этом шаге }.
  facts: { type: Object, default: () => ({}) }
})

defineEmits(['go'])

const номерАктивной = computed(() => props.chapters.findIndex((глава) => глава.id === props.active))
const фактАктивной = computed(() => props.facts[props.active] ?? '')

// Лента на узком экране прокручивается сама: текущая глава должна быть
// видна, даже если до неё не дотянулись пальцем.
const лента = ref(null)
watch(() => props.active, async () => {
  await nextTick()
  const кнопка = лента.value?.querySelector('.is-active')
  const полоса = лента.value
  if (!кнопка || !полоса || полоса.scrollWidth <= полоса.clientWidth) return
  полоса.scrollTo({ left: кнопка.offsetLeft - полоса.clientWidth / 2 + кнопка.offsetWidth / 2, behavior: 'auto' })
})
</script>

<template>
  <nav class="rail" aria-label="Главы: путь вакансии">
    <div v-if="hero" class="rail__hero">
      <span class="rail__label">Вакансия-пример</span>
      <span class="rail__name">{{ hero['название'] }}</span>
      <span class="rail__company">{{ hero['компания'] }}</span>
    </div>

    <ol ref="лента" class="rail__list">
      <li
        v-for="(глава, i) in chapters"
        :key="глава.id"
        class="rail__item"
        :class="{ 'is-active': глава.id === active, 'is-past': i < номерАктивной }"
      >
        <button
          type="button"
          class="rail__link"
          :aria-current="глава.id === active ? 'step' : undefined"
          @click="$emit('go', глава.id)"
        >
          <span class="rail__dot" aria-hidden="true"></span>
          <span class="rail__num" aria-hidden="true">{{ String(глава.number).padStart(2, '0') }}</span>
          <span class="rail__title">{{ глава.title }}</span>
        </button>
        <!-- Что узнали о вакансии на этом шаге: остаётся под пройденной главой. -->
        <div v-if="facts[глава.id]" class="rail__fact" :class="{ 'is-shown': i <= номерАктивной }">
          <p>{{ facts[глава.id] }}</p>
        </div>
      </li>
    </ol>

    <p v-if="фактАктивной" class="rail__now" aria-live="polite">{{ фактАктивной }}</p>
  </nav>
</template>

<style scoped>
.rail {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
}

.rail__hero {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding-bottom: var(--s-4);
  box-shadow: inset 0 -1px 0 var(--c-border);
}

.rail__label {
  font-size: var(--t-label-alt-size);
  line-height: var(--t-label-alt-lh);
  color: var(--c-text-muted);
}

.rail__name {
  font-size: var(--t-ui-size);
  line-height: var(--t-ui-lh);
  font-weight: var(--w-medium);
  color: var(--c-text);
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.rail__company {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
}

.rail__item {
  position: relative;
  padding-bottom: var(--s-3);
}

/* Отрезок пути от этой главы к следующей. Пройденный — темнее. */
.rail__item::before {
  content: '';
  position: absolute;
  left: 11px;
  top: 22px;
  bottom: -6px;
  width: 1px;
  background: var(--c-border-strong);
  transition: background-color var(--dur-panel) var(--ease-standard);
}

.rail__item:last-child::before { display: none; }
.rail__item.is-past::before { background: var(--c-text); }

.rail__link {
  display: grid;
  grid-template-columns: 24px auto minmax(0, 1fr);
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  min-height: var(--h-control-sm);
  padding: 0 var(--s-2) 0 0;
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  font: inherit;
  text-align: left;
  color: var(--c-text-muted);
  cursor: pointer;
  transition: var(--t-hover);
}

.rail__link:hover { color: var(--c-text); }
.rail__link:focus-visible { outline: none; box-shadow: var(--focus-ring); }

.rail__dot {
  justify-self: center;
  width: 9px;
  height: 9px;
  border-radius: var(--r-pill);
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1.5px var(--c-border-strong);
  transition: background-color var(--dur-panel) var(--ease-standard), box-shadow var(--dur-panel) var(--ease-standard),
    transform var(--dur-panel) var(--ease-enter);
}

.rail__item.is-past .rail__dot { background: var(--c-text); box-shadow: none; }

/* Текущая глава — как активный пункт навигации: единственное место
   рельса, где есть цвет. */
.rail__item.is-active .rail__dot {
  background: var(--c-accent);
  box-shadow: 0 0 0 4px var(--c-accent-subtle);
  transform: scale(1.1);
}

.rail__num {
  font-family: var(--font-mono);
  font-size: var(--t-label-alt-size);
  font-variant-numeric: tabular-nums;
}

.rail__title {
  font-size: var(--t-ui-size);
  line-height: var(--t-ui-lh);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail__item.is-past .rail__link { color: var(--c-text-secondary); }
.rail__item.is-active .rail__link { color: var(--c-text); font-weight: var(--w-medium); }

/* Строка о вакансии раскрывается, когда до главы дошли. */
.rail__fact {
  display: grid;
  grid-template-rows: 0fr;
  padding-left: calc(24px + var(--s-2));
  opacity: 0;
  transition: grid-template-rows var(--dur-enter) var(--ease-enter), opacity var(--dur-enter) var(--ease-enter);
}

.rail__fact.is-shown { grid-template-rows: 1fr; opacity: 1; }

.rail__fact p {
  min-height: 0;
  overflow: hidden;
  font-size: var(--t-label-alt-size);
  line-height: var(--t-label-alt-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.rail__now { display: none; }

/* Узкий экран: главы лентой, о вакансии — одна строка под лентой. */
@media (max-width: 1199px) {
  .rail { gap: var(--s-1); }
  .rail__hero { display: none; }

  .rail__list {
    flex-direction: row;
    gap: var(--s-1);
    overflow-x: auto;
    scrollbar-width: none;
    /* Прокрутка ленты не должна утягивать за собой страницу. */
    overscroll-behavior-x: contain;
  }

  .rail__list::-webkit-scrollbar { display: none; }

  .rail__item { flex: 0 0 auto; padding-bottom: 0; }
  .rail__item::before,
  .rail__fact,
  .rail__dot { display: none; }

  .rail__link {
    grid-template-columns: auto auto;
    height: var(--h-control-md);
    padding: 0 var(--s-3);
  }

  .rail__item.is-active .rail__link { background: var(--c-accent-subtle); color: var(--c-accent); }

  .rail__now {
    display: block;
    padding: 0 var(--s-3);
    font-size: var(--t-label-alt-size);
    line-height: var(--t-label-alt-lh);
    color: var(--c-text-muted);
    max-width: none;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

@media (prefers-reduced-motion: reduce) {
  .rail__item::before,
  .rail__dot,
  .rail__fact,
  .rail__link { transition: none; }
}
</style>
