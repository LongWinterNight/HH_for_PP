<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppNav from '@/app/AppNav.vue'
import AppTabbar from '@/app/AppTabbar.vue'
import { useHeaderMeta } from '@/composables/useHeaderMeta'
import { useViewport } from '@/composables/useViewport'
import { num, dateTime, timeAgoShort } from '@/utils/format'

const route = useRoute()
const { режим } = useViewport()
const { состояниеБазы, подписьЭкрана, обновить } = useHeaderMeta()

const узкий = computed(() => режим.value === 'узкий')

// На узком экране логотип уступает место названию раздела: полоса
// разделов ушла вниз, и без названия непонятно, где находишься.
const названиеЭкрана = computed(() => route.meta?.title ?? '')

// Счётчик базы: сколько вакансий и когда собирали. На узком экране
// его вытесняет подпись экрана — там место одно, и объём выборки
// человеку нужнее размера базы.
const счётчикБазы = computed(() => {
  const данные = состояниеБазы.value
  if (!данные?.vacancies) return ''
  const давность = данные.last_collected_at ? ` · ${timeAgoShort(данные.last_collected_at)}` : ''
  return `${num(данные.vacancies)}${давность}`
})

const точнаяДата = computed(() => {
  const когда = состояниеБазы.value?.last_collected_at
  return когда ? `Последний сбор: ${dateTime(когда)}` : ''
})

// Обновление при смене раздела, а не по таймеру: сбор мог закончиться,
// пока человек ходил по экранам, а давность измеряется часами.
watch(() => route.fullPath, обновить, { immediate: true })
</script>

<template>
  <div class="shell" :class="{ 'shell--tabbar': узкий }">
    <!-- Шапка на бумагу не идёт: ссылки там не нажать, а липкая
         шапка вдобавок перекрывала бы колонтитул печати. -->
    <header class="shell__header" data-print-hide>
      <div class="shell__header-inner">
        <span v-if="узкий" class="shell__screen">{{ названиеЭкрана }}</span>

        <template v-else>
          <RouterLink to="/" class="brand" aria-label="BaseVacancy, на дашборд">
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
              <circle cx="10" cy="10" r="7.4" fill="none" stroke="currentColor" stroke-width="2.2" />
              <path d="M10 10 L14.6 5.4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
            </svg>
            <span class="brand__name">BASEVACANCY</span>
          </RouterLink>

          <AppNav />
        </template>

        <div class="shell__meta">
          <slot name="meta" />
          <span v-if="узкий && подписьЭкрана" class="shell__summary">{{ подписьЭкрана }}</span>
          <span v-else-if="счётчикБазы" class="shell__summary" :title="точнаяДата">{{ счётчикБазы }}</span>
        </div>
      </div>
    </header>

    <main class="shell__main">
      <slot />
    </main>

    <AppTabbar v-if="узкий" />
  </div>
</template>

<style scoped>
.shell {
  /* dvh, а не vh: в Safari на iOS адресная строка сворачивается, и
     экран, заданный в vh, уезжает под неё. */
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--c-canvas);
}

/* Шапка держится сверху: навигация нужна на любой глубине таблицы. */
.shell__header {
  position: sticky;
  top: 0;
  z-index: var(--z-header);
  background: var(--c-surface);
  box-shadow: inset 0 -1px 0 var(--c-border);
}

.shell__header-inner {
  max-width: var(--container-max);
  margin: 0 auto;
  height: var(--h-header);
  padding: 0 clamp(var(--s-4), 2.5vw, var(--s-8));
  display: flex;
  align-items: center;
  gap: var(--s-4);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  flex: 0 0 auto;
  color: var(--c-text);
}

.brand:hover { color: var(--c-text); }

.brand__name {
  font-size: var(--t-ui-size);
  font-weight: var(--w-strong);
  letter-spacing: 0.02em;
  white-space: nowrap;
}

/* Название раздела в шапке узкого экрана. Не заголовок: h1 у экрана
   уже есть в теле, а второй сбивает структуру для чтения с экрана.
   Здесь ориентир «где я», а не начало текста. */
.shell__screen {
  min-width: 0;
  font-size: var(--t-ui-size);
  font-weight: var(--w-strong);
  color: var(--c-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shell__meta {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--s-3);
  flex: 0 0 auto;
}

/* Объём выборки или счётчик базы. Цифры моноширинные: подпись меняется
   при каждом переходе, и прыгающая ширина дёргает шапку. */
.shell__summary {
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-muted);
  white-space: nowrap;
}

.shell__main {
  max-width: var(--container-max);
  margin: 0 auto;
  padding: var(--s-8) clamp(var(--s-4), 2.5vw, var(--s-8)) var(--s-24);
  display: flex;
  flex-direction: column;
  gap: var(--s-8);
}

/* Под нижней полосой: последняя строка экрана не должна оказаться
   под пунктами разделов. */
.shell--tabbar .shell__main {
  padding-bottom: calc(var(--s-24) + var(--h-tabbar));
}
</style>
