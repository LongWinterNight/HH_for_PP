<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppNav from '@/app/AppNav.vue'
import AppTabbar from '@/app/AppTabbar.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
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

// Последний сбор не удался. Прежде об этом знал только экран «Сбор
// данных», и только до перезапуска приложения: отказ жил в памяти
// процесса. Сбор так пролежал месяц. Теперь исход читается из базы и
// стоит в шапке — его видно с любого экрана и после перезапуска.
const отказСбора = computed(() => {
  const запуск = состояниеБазы.value?.last_run
  return запуск?.failed ? запуск : null
})

const подсказкаОтказа = computed(() => {
  const запуск = отказСбора.value
  if (!запуск) return ''
  const когда = запуск.finished_at ? ` · ${dateTime(запуск.finished_at)}` : ''
  return `${запуск.title}${когда}. ${запуск.text}`
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
          <!-- Ссылка, а не подпись: по ней сразу попадаешь туда, где
               отказ объяснён и где его можно повторить. На узком экране
               остаётся только знак — место в шапке одно. -->
          <RouterLink
            v-if="отказСбора"
            to="/collection"
            class="shell__alert"
            :title="подсказкаОтказа"
            :aria-label="`Последний сбор не удался: ${отказСбора.title}`"
          >
            <BvStatus kind="err" :label="узкий ? '' : 'Сбор не удался'" />
          </RouterLink>
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
/* Отказ сбора в шапке. Нажимается вся метка, а не только точка. */
.shell__alert {
  display: inline-flex;
  align-items: center;
  min-height: var(--h-control-sm);
  border-radius: var(--r-md);
  text-decoration: none;
  white-space: nowrap;
}

.shell__alert:focus-visible { box-shadow: var(--focus-ring); outline: none; }

/* На узком экране от метки остаётся точка в восемь пикселей. Знак
   маленький, а нажимается область вокруг него: иначе пальцем в неё не
   попасть — та же беда, что была у крестика в чипе запроса. */
.shell__alert { position: relative; }
.shell__alert::after {
  content: '';
  position: absolute;
  inset: -8px -14px;
}

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
