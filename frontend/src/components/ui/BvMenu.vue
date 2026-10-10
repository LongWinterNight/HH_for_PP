<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useViewport } from '@/composables/useViewport'

// Меню — четвёртый вид оверлея системы: дропдаун для действий над
// объектом и для выбора значения.
//
// Модалка сюда не годится — она затемняет страницу и держит фокус в
// ловушке, а меню должно закрываться так же легко, как открылось.
// Правила закрытия при этом те же, что у остальных оверлеев: Esc,
// нажатие вне, выбор пункта; фокус возвращается на кнопку.
//
// До 768px список превращается в нижний лист во всю ширину: дропдаун
// шириной в пол-экрана, висящий у верхнего края, на телефоне
// недосягаем большим пальцем, а его край упирается в границу окна.
//
// Разделители в списке — обычные <hr>: разделы по спеке отделяются
// линией, а разрушительное действие всегда идёт последним и отдельно.
defineProps({
  // Подпись кнопки: «Ещё», «Действия».
  label: { type: String, required: true },
  // Число скрытых пунктов рядом с подписью. Без него человек не знает,
  // стоит ли открывать: «Ещё» может прятать один раздел, а может пять.
  count: { type: Number, default: 0 },
  // Заголовок нижнего листа: у листа во всю ширину должно быть видно,
  // чьи это действия. В дропдауне не показывается — там связь с
  // кнопкой видна глазом.
  title: { type: String, default: '' },
  // Текущий раздел спрятан внутри меню. Кнопка тогда выглядит как
  // активный пункт навигации: иначе на 768px, стоя в «Сборе данных»,
  // человек не видит, где находится, пока не откроет список.
  active: { type: Boolean, default: false },
  // Меню у нижнего края страницы раскрывается вверх.
  placement: {
    type: String,
    default: 'bottom',
    validator: (v) => ['bottom', 'top'].includes(v)
  },
  // Выровнять список по правому краю кнопки: у края экрана иначе
  // вылезает за пределы окна.
  align: {
    type: String,
    default: 'start',
    validator: (v) => ['start', 'end'].includes(v)
  }
})

const открыто = ref(false)
const корень = ref(null)
const список = ref(null)

const { режим } = useViewport()
const лист = computed(() => режим.value === 'узкий')

watch(открыто, async (значение) => {
  if (значение) {
    await nextTick()
    пункты()[0]?.focus()
    document.addEventListener('keydown', поКлавише, true)
    document.addEventListener('pointerdown', поНажатиюВне, true)
    // Под листом страница не прокручивается: он перекрывает её низ, и
    // уехавший под него список потом ищут вслепую.
    if (лист.value) document.body.style.overflow = 'hidden'
  } else {
    отписаться()
  }
})

onBeforeUnmount(отписаться)

function отписаться() {
  document.removeEventListener('keydown', поКлавише, true)
  document.removeEventListener('pointerdown', поНажатиюВне, true)
  document.body.style.overflow = ''
}

function пункты() {
  return [...(список.value?.querySelectorAll('[role="menuitem"]:not([disabled])') ?? [])]
}

function открыть() {
  открыто.value = true
}

function закрыть({ вернутьФокус = true } = {}) {
  if (!открыто.value) return
  открыто.value = false
  if (вернутьФокус) корень.value?.querySelector('.menu__trigger')?.focus()
}

function поНажатиюВне(событие) {
  if (!корень.value?.contains(событие.target)) закрыть({ вернутьФокус: false })
}

// Стрелка вниз на закрытой кнопке открывает меню и ставит фокус на
// первый пункт: это ожидаемый путь с клавиатуры, Enter и пробел кнопка
// обрабатывает сама.
function поСтрелкеСКнопки(событие) {
  if (открыто.value) return
  событие.preventDefault()
  открыть()
}

function поКлавише(событие) {
  if (событие.key === 'Escape') {
    событие.preventDefault()
    закрыть()
    return
  }

  if (событие.key !== 'ArrowDown' && событие.key !== 'ArrowUp') return

  const элементы = пункты()
  if (!элементы.length) return

  событие.preventDefault()
  const текущий = элементы.indexOf(document.activeElement)
  const шаг = событие.key === 'ArrowDown' ? 1 : -1
  const следующий = (текущий + шаг + элементы.length) % элементы.length
  элементы[следующий].focus()
}

// Выбор пункта закрывает меню: иначе оно остаётся висеть над уже
// изменившимся экраном. Фокус при этом не возвращается на кнопку —
// человек ушёл в раздел или запустил действие, и место там важнее.
function поВыбору(событие) {
  if (событие.target.closest('[aria-disabled="true"], [disabled]')) return
  закрыть({ вернутьФокус: false })
}
</script>

<template>
  <div ref="корень" class="menu" :class="[`menu--${placement}`, `menu--${align}`]">
    <button
      type="button"
      class="menu__trigger"
      :class="{ 'is-open': открыто, 'is-active': active }"
      :aria-expanded="открыто"
      aria-haspopup="menu"
      @click="открыто ? закрыть() : открыть()"
      @keydown.down="поСтрелкеСКнопки"
    >
      <span>{{ label }}</span>
      <span v-if="count" class="menu__count">{{ count }}</span>
    </button>

    <!-- Затемнение только у листа: дропдаун страницу не перекрывает и
         гасить её незачем. -->
    <div v-if="открыто && лист" class="menu__scrim" @click="закрыть()"></div>

    <div
      v-if="открыто"
      ref="список"
      class="menu__list"
      :class="{ 'menu__list--sheet': лист }"
      role="menu"
      :aria-label="title || label"
      @click="поВыбору"
    >
      <div v-if="лист" class="menu__handle" aria-hidden="true"></div>
      <p v-if="лист && title" class="menu__title">{{ title }}</p>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.menu {
  position: relative;
  flex: 0 0 auto;
}

.menu__trigger {
  height: var(--h-control-md);
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  border: 0;
  border-radius: var(--r-md);
  background: transparent;
  cursor: pointer;
  font-size: var(--t-ui-size);
  font-weight: var(--w-regular);
  color: var(--c-text-muted);
  white-space: nowrap;
  transition: var(--t-hover);
}

.menu__trigger:hover,
.menu__trigger.is-open {
  background: var(--c-surface-hover);
  color: var(--c-text);
}

/* Тот же вид, что у активного пункта навигации: место текущего раздела
   должно читаться одинаково, лежит он в строке или в меню. */
.menu__trigger.is-active {
  background: var(--c-accent-subtle);
  color: var(--c-accent);
  font-weight: var(--w-medium);
}

.menu__trigger.is-active .menu__count {
  background: var(--c-surface-raised);
  color: var(--c-accent);
}

/* Число скрытых пунктов — подпись, а не сигнал: цвет акцента здесь
   спорил бы с активным пунктом навигации. */
.menu__count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-pill);
  background: var(--c-surface-hover);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-muted);
}

.menu__list {
  position: absolute;
  z-index: var(--z-dropdown);
  min-width: 200px;
  padding: var(--s-1);
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-radius: var(--r-md);
  /* Слот поверхности дропдауна, а не общей: всплывающее лежит выше
     страницы и в тёмной подаче светлее её. */
  background: var(--c-surface-raised);
  box-shadow: var(--border), var(--shadow-popover);
}

/* Размещение относительно кнопки — только у дропдауна. Лист стоит на
   экране, и без этой оговорки правила с двумя классами перебивали его
   inset: лист уезжал под нижний край окна на высоту кнопки. */
.menu--bottom .menu__list:not(.menu__list--sheet) { top: calc(100% + var(--s-2)); }
.menu--top .menu__list:not(.menu__list--sheet) { bottom: calc(100% + var(--s-2)); }
.menu--start .menu__list:not(.menu__list--sheet) { left: 0; }
.menu--end .menu__list:not(.menu__list--sheet) { right: 0; }

/* Разделы отделяются линией: разрушительное действие по спеке всегда
   внизу и отдельно от остальных. */
.menu__list :deep(hr) {
  height: 1px;
  margin: var(--s-1) 0;
  border: 0;
  background: var(--c-border);
}

.menu__scrim {
  position: fixed;
  inset: 0;
  z-index: var(--z-overlay);
  /* Затемнение слабее, чем у модалки: лист — это продолжение экрана,
     а не разговор поверх него. */
  background: rgba(5, 0, 56, 0.24);
}

/* Нижний лист до 768px. Позиция фиксированная, а не абсолютная от
   кнопки: лист принадлежит экрану, а не месту, откуда его позвали. */
.menu__list--sheet {
  position: fixed;
  z-index: var(--z-modal);
  inset: auto 0 0 0;
  min-width: 0;
  padding: var(--s-2) var(--s-4) calc(var(--s-4) + env(safe-area-inset-bottom, 0));
  gap: var(--s-1);
  border-radius: var(--r-lg) var(--r-lg) 0 0;
  box-shadow: var(--shadow-overlay);
  /* Длинный список прокручивается внутри листа, а не растёт за экран. */
  max-height: 70dvh;
  overflow-y: auto;
}

/* Ручка сверху: показывает, что лист пришёл снизу и туда же уйдёт. */
.menu__handle {
  width: 36px;
  height: 4px;
  margin: 0 auto var(--s-2);
  border-radius: var(--r-pill);
  background: var(--c-border-strong);
}

.menu__title {
  margin: 0 0 var(--s-1);
  padding: 0 10px;
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}
</style>
