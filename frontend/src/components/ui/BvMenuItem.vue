<script setup>
import { computed } from 'vue'

// Пункт меню. Отдельным компонентом, а не набором классов у вызывающего:
// роль для программы чтения экрана, порядок значков и правило «цифра
// справа не спорит с подписью» должны соблюдаться сами, иначе в третьем
// по счёту меню кто-нибудь сверстает пункт заново и чуть иначе.
//
// Три вида содержимого справа, и они не смешиваются: подсказка (число
// или значок), горячая клавиша и отметка выбора. Пункт, у которого
// справа стоит и число, и клавиша, перестаёт читаться за один взгляд.
const props = defineProps({
  // Ссылка делает пункт <RouterLink>: переход в другой раздел обязан
  // работать средним щелчком и «открыть в новой вкладке».
  to: { type: [String, Object], default: null },
  // Внешний адрес: hh.ru открывается новой вкладкой.
  href: { type: String, default: '' },
  // Число или значок справа: «16», «↗».
  hint: { type: String, default: '' },
  // Горячая клавиша моноширинным справа: «⌘C».
  hotkey: { type: String, default: '' },
  // Меню выбора значения: выбранный пункт помечен подложкой и галкой,
  // как в автокомплите.
  selected: { type: Boolean, default: false },
  // Разрушительное действие. По спеке всегда внизу и отделено линией —
  // за отделение отвечает разделитель, за цвет этот признак.
  danger: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const тег = computed(() => {
  if (props.disabled) return 'button'
  if (props.href) return 'a'
  if (props.to) return 'RouterLink'
  return 'button'
})

const атрибуты = computed(() => {
  if (props.disabled) return { type: 'button', disabled: true }
  if (props.href) return { href: props.href, target: '_blank', rel: 'noopener' }
  if (props.to) return { to: props.to }
  return { type: 'button' }
})
</script>

<template>
  <component
    :is="тег"
    class="item"
    :class="{ 'is-selected': selected, 'is-danger': danger, 'is-disabled': disabled }"
    role="menuitem"
    :aria-disabled="disabled || undefined"
    v-bind="атрибуты"
  >
    <span class="item__label"><slot /></span>

    <!-- Отметка выбора важнее подсказки: в меню выбора значения справа
         стоит она одна. -->
    <span v-if="selected" class="item__check" aria-hidden="true">✓</span>
    <span v-else-if="hotkey" class="item__hotkey">{{ hotkey }}</span>
    <span v-else-if="hint" class="item__hint">{{ hint }}</span>
  </component>
</template>

<style scoped>
.item {
  /* Без width: 100% — в системе box-sizing content-box, и ширина вместе
     с боковыми отступами вылезала за список на 20px. В колонке flex
     пункт растягивается сам. */
  min-height: var(--h-control-lg);
  padding: 0 10px;
  display: flex;
  align-items: center;
  gap: var(--s-3);
  border: 0;
  border-radius: var(--r-md);
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-size: var(--t-ui-size);
  font-weight: var(--w-regular);
  color: var(--c-text);
  transition: var(--t-hover);
}

.item:hover { background: var(--c-surface-hover); }

.item__label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Подсказка и клавиша — приглушённые: подпись пункта остаётся главной. */
.item__hint,
.item__hotkey,
.item__check {
  flex: 0 0 auto;
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

/* Клавиши моноширинным: «⌘C» и «⌘V» должны стоять в столбик ровно. */
.item__hotkey {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.item.is-selected {
  background: var(--c-accent-subtle);
  color: var(--c-accent);
  font-weight: var(--w-medium);
  /* Полоса слева — как у выбранного пункта автокомплита: подложка
     одна повторяет наведение, и выбор от него не отличить. */
  box-shadow: inset 2px 0 0 var(--c-accent);
}

.item.is-selected .item__check { color: var(--c-accent); }

.item.is-danger { color: var(--c-negative); }
.item.is-danger:hover { background: var(--c-negative-subtle); }

/* Недоступный пункт остаётся видимым: «JSON — недоступен для этой
   выборки» объясняет больше, чем исчезнувшая строка. */
.item.is-disabled {
  cursor: default;
  color: var(--c-text-muted);
  opacity: 0.6;
}

.item.is-disabled:hover { background: transparent; }
</style>
