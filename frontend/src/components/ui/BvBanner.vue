<script setup>
// Инлайн-баннер: сообщение, относящееся к конкретному месту экрана.
//
// Когда сказать нужно про этот экран, а не про действие, сообщение
// живёт здесь, а не в углу с тостами. И оно не исчезает по таймеру:
// условие, которое его вызвало, никуда не делось.
//
// Четыре вида:
//   info    — состояние, о котором стоит знать: данные устарели;
//   warning — режим, который что-то испортит: перезапись базы;
//   error   — то, что уже не сработало, с путём к решению;
//   filtered — единственное место системы, где маркерный жёлтый
//              работает фоном: он помечает, что все числа на экране
//              считаны по суженной выборке.
defineProps({
  kind: {
    type: String,
    default: 'info',
    validator: (v) => ['info', 'warning', 'error', 'filtered'].includes(v)
  },
  title: { type: String, required: true },
  text: { type: String, default: '' },
  // Баннер можно убрать, если условие не мешает работе. Предупреждение
  // о необратимом закрывать нельзя — оно пропадает вместе с причиной.
  dismissible: { type: Boolean, default: false }
})

defineEmits(['dismiss'])

const MARKS = {
  info: 'i',
  warning: '!',
  error: '!',
  filtered: '◆'
}
</script>

<template>
  <div class="banner" :class="`banner--${kind}`" role="note">
    <span class="banner__mark" aria-hidden="true">{{ MARKS[kind] }}</span>

    <div class="banner__body">
      <p class="banner__title">{{ title }}</p>
      <p v-if="text" class="banner__text">{{ text }}</p>

      <div v-if="$slots.actions" class="banner__actions">
        <slot name="actions" />
      </div>
    </div>

    <button
      v-if="dismissible"
      type="button"
      class="banner__close"
      aria-label="Скрыть сообщение"
      @click="$emit('dismiss')"
    >✕</button>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  padding: var(--s-4);
  border-radius: var(--r-md);
  background: var(--c-surface);
  box-shadow: var(--border);
}

/* Знак берёт цвет от вида, фон баннера остаётся спокойным: цветная
   плашка во всю ширину спорит с двумя окрашенными местами экрана. */
.banner__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  border-radius: var(--r-xs);
  box-shadow: var(--border-strong);
  font-family: var(--font-mono);
  font-size: var(--t-label-size);
  font-weight: var(--w-strong);
  color: var(--c-text);
}

/* Предупреждение подаётся формой: знак, метка и двойная рамка. Жёлтый
   в системе занят маркером, и второй жёлтый со смыслом «внимание»
   был бы неотличим от него. */
.banner--warning { box-shadow: var(--border-warning); }

.banner--error {
  background: var(--c-status-err-bg);
  box-shadow: none;
}

.banner--error .banner__mark {
  color: var(--c-status-err-text);
  box-shadow: inset 0 0 0 1px var(--c-negative);
}

/* Суженная выборка — тот самый случай, когда маркер работает фоном:
   он помечает весь экран, а не отдельное значение. */
.banner--filtered {
  background: var(--c-marker-subtle);
  box-shadow: none;
}

.banner__body {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
  flex: 1 1 auto;
}

.banner__title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
  max-width: none;
}

.banner__text {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
  max-width: none;
}

.banner__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin-top: var(--s-1);
}

.banner__close {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  padding: 0;
  color: var(--c-text-muted);
  font-size: var(--t-caption-size);
  cursor: pointer;
}

.banner__close:hover { color: var(--c-text); }
</style>
