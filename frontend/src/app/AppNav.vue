<script setup>
import { computed } from 'vue'
import BvMenu from '@/components/ui/BvMenu.vue'
import BvMenuItem from '@/components/ui/BvMenuItem.vue'
import { useRoute } from 'vue-router'
import { routes } from '@/app/router'
import { useViewport } from '@/composables/useViewport'

// Пункты берутся из роутера: список названий существует в одном месте.
// Служебные экраны помечены meta.nav: false и в навигацию не попадают.
const items = routes.filter((r) => r.meta?.title && r.meta.nav !== false)

// Сколько разделов помещается в строку. Шесть влезают от 1024px; ниже
// в строке остаются три, остальные уходят в «Ещё».
//
// Раньше полоса просто прокручивалась, и на 768px за краем оказывались
// четыре раздела из шести — прокрутку внутри шапки человек не ищет.
// Порядок при этом не меняется: место пункта должно запоминаться.
const В_СТРОКЕ = 3

const route = useRoute()
const { режим } = useViewport()

const видимые = computed(() => (режим.value === 'широкий' ? items : items.slice(0, В_СТРОКЕ)))
const скрытые = computed(() => (режим.value === 'широкий' ? [] : items.slice(В_СТРОКЕ)))

// Текущий раздел уехал в «Ещё»: кнопка должна показать это сама.
const текущийСкрыт = computed(() => скрытые.value.some((r) => r.name === route.name))
</script>

<template>
  <nav class="nav" aria-label="Разделы">
    <RouterLink
      v-for="item in видимые"
      :key="item.name"
      :to="item.path"
      class="nav__item"
      active-class="is-active"
      :aria-current="$route.name === item.name ? 'page' : undefined"
    >{{ item.meta.title }}</RouterLink>

    <BvMenu
      v-if="скрытые.length"
      label="Ещё"
      :count="скрытые.length"
      :active="текущийСкрыт"
      title="Разделы"
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
.nav {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.nav__item {
  height: var(--h-control-md);
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  border-radius: var(--r-md);
  flex: 0 0 auto;
  white-space: nowrap;
  font-size: var(--t-ui-size);
  font-weight: var(--w-regular);
  color: var(--c-text-muted);
  transition: var(--t-hover);
}

.nav__item:hover {
  background: var(--c-surface-hover);
  color: var(--c-text);
}

/* Активный пункт — одно из ровно двух окрашенных мест на экране.
   Второе — главная кнопка действия. */
.nav__item.is-active {
  background: var(--c-accent-subtle);
  color: var(--c-accent);
  font-weight: var(--w-medium);
}

/* Лишние пункты прячет сам браузер, не дожидаясь скрипта.
   Состав списка меняет скрипт (три пункта и «Ещё» вместо шести), но он
   узнаёт о новой ширине почти через секунду после неё. Всё это время
   шесть пунктов стояли в строке шириной 390 и распирали страницу на
   350 px вбок — при повороте телефона экран уезжал. Число в селекторе
   — то же, что В_СТРОКЕ в скрипте: с четвёртого пункта. */
@media (max-width: 1023.98px) {
  .nav__item:nth-of-type(n + 4) { display: none; }
}

/* На телефоне пункт сжимается, а не вылезает. Пока скрипт не сменил
   шапку на нижнюю панель, три пункта стоят рядом с логотипом и в 390
   не помещаются на 66 px. Когда места хватает, правило ничего не
   меняет: сжимается только то, что не поместилось. */
@media (max-width: 767.98px) {
  .nav__item {
    flex-shrink: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}
</style>
