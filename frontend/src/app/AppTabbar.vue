<script setup>
import { computed } from 'vue'
import BvMenu from '@/components/ui/BvMenu.vue'
import BvMenuItem from '@/components/ui/BvMenuItem.vue'
import { useRoute } from 'vue-router'
import { routes } from '@/app/router'

// Нижняя полоса разделов на узком экране.
//
// Полоса внизу, а не в шапке: на телефоне низ экрана — единственное
// место, куда большой палец достаёт не перехватывая устройство.
//
// Четыре пункта и «Ещё», хотя спека адаптивности называет пять.
// Замер на 390px: пятая ячейка оставляет по 64px, а самая длинная
// подпись — «Сбор данных» — требует 78. Пять подписей помещаются
// только обрезанными многоточием, и «Сбор дан…» в полосе хуже, чем
// целое название в меню. Спрятанный раздел остаётся доступным —
// урезанной мобильной версии в продукте нет.
const В_ПОЛОСЕ = 4

const items = routes.filter((r) => r.meta?.title && r.meta.nav !== false)

const route = useRoute()

const видимые = computed(() => items.slice(0, В_ПОЛОСЕ))
const скрытые = computed(() => items.slice(В_ПОЛОСЕ))

// Текущий раздел уехал в «Ещё»: без пометки на телефоне непонятно, где
// находишься, — в полосе не подсвечен ни один пункт.
const текущийСкрыт = computed(() => скрытые.value.some((r) => r.name === route.name))
</script>

<template>
  <nav class="tabbar" aria-label="Разделы" data-print-hide>
    <RouterLink
      v-for="item in видимые"
      :key="item.name"
      :to="item.path"
      class="tabbar__item"
      active-class="is-active"
      :aria-current="$route.name === item.name ? 'page' : undefined"
    >{{ item.meta.title }}</RouterLink>

    <BvMenu
      v-if="скрытые.length"
      class="tabbar__more"
      label="Ещё"
      :count="скрытые.length"
      :active="текущийСкрыт"
      title="Разделы"
      placement="top"
      align="end"
    >
      <BvMenuItem
        v-for="item in скрытые"
        :key="item.name"
        :to="item.path"
        :selected="$route.name === item.name"
      >{{ item.meta.title }}</BvMenuItem>
    </BvMenu>
  </nav>
</template>

<style scoped>
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: var(--z-header);
  display: flex;
  align-items: stretch;
  background: var(--c-surface);
  box-shadow: inset 0 1px 0 var(--c-border);
  /* Полоса домой в iOS перекрывает нижние 34px: без отступа под неё
     пункты оказываются под системным индикатором. */
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.tabbar__item,
.tabbar__more :deep(.menu__trigger) {
  flex: 1 1 0;
  min-width: 0;
  height: var(--h-tabbar);
  display: flex;
  align-items: center;
  justify-content: center;
  /* Без боковых отступов: ячейка узкая, и «Профессии» упирались в них
     последним пикселем. Цель нажатия — вся ячейка, отступ ей не нужен. */
  padding: 0;
  border-radius: 0;
  text-align: center;
  /* Подписи на 390px тесные: кегль на ступень ниже интерфейсного,
     перенос запрещён — «Сбор» на второй строке читается как другой
     раздел. */
  font-size: var(--t-caption-size);
  line-height: 1.1;
  color: var(--c-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tabbar__item.is-active {
  color: var(--c-accent);
  font-weight: var(--w-medium);
  box-shadow: inset 0 2px 0 var(--c-accent);
}

.tabbar__more {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
}

.tabbar__more :deep(.menu__trigger) {
  gap: var(--s-1);
  background: transparent;
}

.tabbar__more :deep(.menu__list) {
  min-width: 200px;
  margin-bottom: env(safe-area-inset-bottom, 0);
}
</style>
