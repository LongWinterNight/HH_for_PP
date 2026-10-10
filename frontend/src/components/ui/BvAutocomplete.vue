<script setup>
import { computed, ref, useId, watch } from 'vue'
import { num } from '@/utils/format'

// Поле с подсказками: поиск по названию, региону, навыку.
//
// Подсказка приходит с числом вакансий: она сразу говорит, стоит ли
// выбирать вариант, — «Москва · 182» полезнее, чем просто «Москва».
//
// Выбранный клавишами пункт помечен подложкой и полосой слева, но не
// меняет цвет текста: при переборе стрелками строка иначе «прыгает»
// по насыщенности и глаз теряет место.
//
// Показывается не больше семи пунктов, дальше прокрутка: длинный
// список подсказок перестаёт быть подсказкой.
const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, required: true },
  placeholder: { type: String, default: '' },
  // Функция-загрузчик: (запрос) => Promise<[{ label, value, count }]>
  suggest: { type: Function, required: true },
  // Задержка перед запросом. Проверять по каждой букве — спорить
  // с человеком, который ещё не дописал.
  delay: { type: Number, default: 250 }
})

const emit = defineEmits(['update:modelValue', 'select'])

const id = useId()
const listId = `${id}-list`
const items = ref([])
const open = ref(false)
const active = ref(-1)
const loading = ref(false)
let timer = null

// Выбор подсказки меняет значение поля, а изменение значения
// запускает новый запрос — и список открывается поверх только что
// выбранного варианта. Один пропуск разрывает этот круг.
let skipNextLookup = false

const hasItems = computed(() => items.value.length > 0)

watch(() => props.modelValue, (value) => {
  clearTimeout(timer)

  if (skipNextLookup) {
    skipNextLookup = false
    return
  }

  if (!value || value.length < 2) {
    items.value = []
    open.value = false
    return
  }
  timer = setTimeout(fetchItems, props.delay)
})

async function fetchItems() {
  loading.value = true
  try {
    const result = await props.suggest(props.modelValue)
    items.value = result ?? []
    active.value = -1
    open.value = items.value.length > 0
  } finally {
    loading.value = false
  }
}

function choose(item) {
  skipNextLookup = true
  emit('update:modelValue', item.value)
  emit('select', item)
  open.value = false
  active.value = -1
}

function onKeydown(event) {
  if (!open.value || !hasItems.value) return

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    active.value = (active.value + 1) % items.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    active.value = active.value <= 0 ? items.value.length - 1 : active.value - 1
  } else if (event.key === 'Enter' && active.value >= 0) {
    event.preventDefault()
    choose(items.value[active.value])
  } else if (event.key === 'Escape') {
    open.value = false
    active.value = -1
  }
}

// Закрытие по уходу фокуса откладывается: без задержки щелчок по
// подсказке не успевает сработать — список исчезает раньше.
function onBlur() {
  setTimeout(() => { open.value = false }, 120)
}
</script>

<template>
  <div class="ac">
    <label class="ac__label label" :for="id">{{ label }}</label>

    <div class="ac__box">
      <input
        :id="id"
        class="ac__input"
        type="text"
        role="combobox"
        autocomplete="off"
        :value="modelValue"
        :placeholder="placeholder"
        :aria-expanded="open"
        :aria-controls="listId"
        :aria-activedescendant="active >= 0 ? `${id}-opt-${active}` : undefined"
        @input="$emit('update:modelValue', $event.target.value)"
        @keydown="onKeydown"
        @focus="open = hasItems"
        @blur="onBlur"
      >
    </div>

    <ul v-if="open" :id="listId" class="ac__list" role="listbox" :aria-label="label">
      <li
        v-for="(item, index) in items"
        :id="`${id}-opt-${index}`"
        :key="item.value"
        class="ac__item"
        :class="{ 'is-active': index === active }"
        role="option"
        :aria-selected="index === active"
        @mousedown.prevent="choose(item)"
        @mouseenter="active = index"
      >
        <span class="ac__text">{{ item.label }}</span>
        <span class="ac__count">{{ num(item.count) }}</span>
      </li>
      <li class="ac__hint">↑ ↓ выбрать · enter применить</li>
    </ul>
  </div>
</template>

<style scoped>
.ac {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.ac__box {
  display: flex;
  align-items: center;
  height: var(--h-control-lg);
  border-radius: var(--r-md);
  background: var(--c-surface-sunken);
  box-shadow: var(--border);
  transition: var(--t-hover);
}

.ac__input {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  padding: 0 var(--s-3);
  border: none;
  border-radius: inherit;
  background: transparent;
  color: var(--c-text);
  font-family: var(--font-sans);
  /* 16px на мобильном: иначе iOS увеличивает страницу при фокусе. */
  font-size: max(var(--t-ui-size), 16px);
}

@media (min-width: 768px) {
  .ac__input { font-size: var(--t-ui-size); }
}

.ac__input::placeholder { color: var(--c-text-quiet); }
.ac__input:focus { outline: none; }

.ac__box:has(.ac__input:focus-visible) {
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1px var(--c-accent), var(--focus-ring);
}

/* Единственная тень системы принадлежит всплывающему — вот ему. */
.ac__list {
  position: absolute;
  top: calc(100% + var(--s-1));
  left: 0;
  right: 0;
  z-index: var(--z-dropdown);
  margin: 0;
  padding: var(--s-1);
  list-style: none;
  border-radius: var(--r-md);
  background: var(--c-surface-raised);
  box-shadow: var(--border), var(--shadow-popover);
  /* Семь пунктов по 32px плюс строка подсказки. */
  max-height: calc(32px * 7 + 28px);
  overflow-y: auto;
}

.ac__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  height: 32px;
  padding: 0 var(--s-2);
  border-radius: var(--r-sm);
  font-size: var(--t-ui-size);
  color: var(--c-text);
  cursor: pointer;
}

/* Подложка и полоса слева: цвет текста не меняется, чтобы строка не
   прыгала по насыщенности при переборе клавишами. */
.ac__item.is-active {
  background: var(--c-accent-subtle);
  box-shadow: inset 3px 0 0 var(--c-accent);
}

.ac__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ac__count {
  flex: 0 0 auto;
  color: var(--c-text-muted);
  font-variant-numeric: tabular-nums;
  font-size: var(--t-caption-size);
}

.ac__hint {
  padding: var(--s-1) var(--s-2) 2px;
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}
</style>
