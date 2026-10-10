<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvField from '@/components/ui/BvField.vue'
import BvIconButton from '@/components/ui/BvIconButton.vue'
import BvPagination from '@/components/ui/BvPagination.vue'
import BvSelect from '@/components/ui/BvSelect.vue'
import BvTable from '@/components/ui/BvTable.vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import { professions } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { num } from '@/utils/format'
import { useRouter } from 'vue-router'

// Справочник профессий: найти профессию, увидеть, что о ней известно,
// и запустить сбор, если данных мало.
//
// Числа здесь описывают справочник, а не текущую базу: каталог собран
// прошлыми запусками и с содержимым базы не связан. Экран называет это
// прямо, потому что «68 вакансий» рядом с пустой базой выглядит как
// ошибка интерфейса, а не как свойство данных.

const router = useRouter()

const search = ref('')
const domain = ref('')
const page = ref(1)
const perPage = ref(20)
const selected = ref(null)

const list = useApi((options) => professions.list({
  search: search.value,
  domain: domain.value,
  limit: 500
}, options))

onMounted(() => list.load())

watch([search, domain], () => {
  page.value = 1
  list.load()
})

const all = computed(() => list.data.value?.professions ?? [])

// Сколько профессий не обещают пустоты. Считает сервер: на клиенте
// лежит только показанная страница справочника.
const withData = computed(() => list.data.value?.with_data ?? 0)
const catalogTotal = computed(() => list.data.value?.total ?? 0)
const total = computed(() => all.value.length)

// Пагинация на клиенте: API отдаёт справочник целиком, и гонять его
// заново ради следующей страницы незачем.
const pageItems = computed(() => {
  const start = (page.value - 1) * perPage.value
  return all.value.slice(start, start + perPage.value)
})

const domainOptions = computed(() => {
  const raw = list.data.value?.domains ?? {}
  // Каталог отдаёт направления как { IT: 'Информационные технологии' },
  // то есть значение — строка, а не объект.
  const list_ = Object.entries(raw).map(([key, value]) => ({
    value: key,
    label: typeof value === 'string' ? value : (value?.name || key)
  }))
  return [{ value: '', label: 'Все направления' }, ...list_]
})

const detail = useApi((key, options) => professions.detail(key, options))

function open(profession) {
  selected.value = profession
  detail.load(profession.key)
}

const topSkills = computed(() => {
  const p = detail.data.value
  if (!p?.top_skills) return []
  // В каталоге top_skills — просто названия, без частот: полосы строить
  // не из чего, поэтому показываем их чипами.
  return p.top_skills
})

const areas = computed(() => {
  const raw = detail.data.value?.top_areas
  if (!raw) return []
  return Object.entries(raw).map(([label, value]) => ({ label, value: Number(value) })).slice(0, 5)
})

// «Собрать по этой профессии» — главное действие экрана: название
// подставляется в запрос сбора, дальше остаётся нажать «Запустить».
function collect(profession) {
  router.push({ name: 'collection', query: { keyword: profession.name } })
}
</script>

<template>
  <section class="prof">
    <header class="prof__head">
      <div class="prof__titles">
        <h1>Профессии</h1>
        <p class="prof__meta">
          Справочник профессий hh.ru: найдите профессию, посмотрите, что о ней известно,
          и запустите сбор, если данных мало.
        </p>
      </div>
    </header>

    <div class="prof__filters card" data-print-hide>
      <BvField v-model="search" label="Поиск по справочнику" placeholder="Название профессии" />
      <BvSelect v-model="domain" label="Направление" :options="domainOptions" />
    </div>

    <!-- Оговорка о происхождении чисел стоит до таблицы, а не после:
         после неё её уже не прочитают. Раньше здесь было написано
         обратное — что числа относятся к справочнику; теперь они
         считаются по базе, и объяснять нужно другое: почему у
         большинства профессий их нет. -->
    <BvBanner
      kind="info"
      :title="`Данные есть по ${withData} профессиям из ${num(catalogTotal)}`"
      text="Справочник перечисляет профессии рынка целиком — он нужен и тому, кто ещё выбирает направление. База наполняется сборами по конкретным запросам, поэтому у большинства профессий вакансий пока нет. Выберите профессию и запустите сбор, чтобы они появились."
    />

    <div class="prof__body" :class="{ 'has-panel': selected }">
      <div class="prof__list">
        <div v-if="list.error.value" class="prof__state card">
          <p class="prof__state-title">Справочник не загружен</p>
          <p class="prof__state-text">{{ list.error.value }}</p>
          <BvButton size="md" :loading="list.loading.value" @click="list.load()">Повторить</BvButton>
        </div>

        <div v-else-if="!list.loading.value && total === 0" class="prof__state card">
          <p class="prof__state-title">Ничего не найдено</p>
          <p class="prof__state-text">В справочнике нет профессий с таким названием. Попробуйте короче: «аналитик» вместо «аналитик данных».</p>
        </div>

        <BvTable v-else label="Справочник профессий" sticky-first>
          <thead>
            <tr>
              <th>Профессия</th>
              <th>Сфера</th>
              <th class="col-num">В базе</th>
              <th class="col-num">Навыков</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in pageItems"
              :key="p.key"
              class="prof__row"
              :class="{ 'is-selected': selected && selected.key === p.key }"
              tabindex="0"
              @click="open(p)"
              @keydown.enter="open(p)"
            >
              <td class="prof__name">{{ p.name }}</td>
              <td class="prof__sphere">{{ p.sphere || '—' }}</td>
              <!-- Пустая профессия видна до клика: иначе человек
                   выбирает её и попадает в пустоту, а справочник
                   выглядит сломанным. -->
              <td class="col-num">
                <template v-if="p.vacancies_count">{{ num(p.vacancies_count) }}</template>
                <span v-else class="prof__none">не собирали</span>
              </td>
              <td class="col-num">{{ num(p.total_skills || 0) }}</td>
            </tr>
          </tbody>
        </BvTable>

        <BvPagination
          v-if="total > 0"
          :page="page"
          :per-page="perPage"
          :total="total"
          @update:page="page = $event"
          @update:per-page="perPage = $event"
        />
      </div>

      <div v-if="selected" class="sheet-backdrop" @click="selected = null"></div>

      <aside v-if="selected" class="prof__panel card" aria-label="Выбранная профессия">
        <header class="prof__panel-head">
          <div class="prof__titles">
            <h2 class="prof__panel-name">{{ selected.name }}</h2>
            <span class="prof__panel-sphere">{{ selected.sphere }}</span>
          </div>
          <BvIconButton label="Закрыть панель" @click="selected = null">✕</BvIconButton>
        </header>

        <div class="prof__facts">
          <div class="prof__fact">
            <span class="label">В базе</span>
            <span class="prof__fact-value">{{ num(selected.vacancies_count) }}</span>
          </div>
          <div class="prof__fact">
            <span class="label">Навыков описано</span>
            <span class="prof__fact-value">{{ num(selected.total_skills || 0) }}</span>
          </div>
        </div>

        <!-- Пустая профессия не тупик: человеку говорят, почему пусто.
             Действие не дублируется — кнопка сбора стоит внизу панели и
             видна в любом состоянии. -->
        <section v-if="!selected.vacancies_count" class="prof__block">
          <h3 class="label">Данных по этой профессии нет</h3>
          <p class="prof__empty-text">
            Справочник перечисляет профессии рынка целиком, а база наполняется
            сборами по конкретным запросам. По «{{ selected.name }}» сбор ещё не
            запускали — поэтому вакансий и нет.
          </p>
        </section>

        <!-- Навыки, регионы и работодатели описывают профессию по тому
             сбору, при котором составлялся справочник, а не по текущей
             базе. Источник назван: иначе «встречается в Петербурге» под
             строкой «в базе 0» читается как противоречие. -->
        <section v-if="topSkills.length" class="prof__block">
          <h3 class="label">Что чаще всего требуют</h3>
          <p class="prof__source">по данным справочника</p>
          <div class="prof__chips">
            <BvChip v-for="s in topSkills" :key="s">{{ s }}</BvChip>
          </div>
        </section>

        <section v-if="areas.length" class="prof__block">
          <h3 class="label">Где встречается чаще</h3>
          <p class="prof__source">по данным справочника</p>
          <BvBarList :items="areas" />
        </section>

        <BvButton variant="primary" @click="collect(selected)">Собрать по этой профессии</BvButton>
        <p class="prof__hint">
          Название подставится в запрос сбора — останется нажать «Запустить сбор».
        </p>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.prof {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.prof__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.prof__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.prof__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr));
  gap: var(--s-4);
}

.prof__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--gap-grid);
  align-items: start;
}

@media (min-width: 1024px) {
  .prof__body.has-panel { grid-template-columns: minmax(0, 1fr) 380px; }
  .prof__panel { position: sticky; top: calc(var(--h-header) + var(--s-4)); }
}

/* Ниже 1024px панель превращается в нижний лист: боковая колонка на
   телефоне оставила бы от таблицы полосу в треть экрана.
   Высота ограничена dvh — в Safari адресная строка сворачивается, и
   лист, заданный в vh, уезжает под неё. Нижний отступ учитывает
   жестовую черту iPhone: без него кнопки под ней недоступны. */
@media (max-width: 1023px) {
  .prof__panel {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: var(--z-overlay);
    max-height: 85dvh;
    overflow-y: auto;
    border-radius: var(--r-lg) var(--r-lg) 0 0;
    padding-bottom: calc(var(--pad-card) + env(safe-area-inset-bottom, 0px));
    box-shadow: var(--shadow-overlay);
  }
}

/* Подложка под нижним листом: она отделяет лист от страницы и даёт
   способ закрыть его нажатием мимо — на телефоне это привычнее,
   чем целиться в крестик. На широком экране панель стоит рядом со
   списком, и подложка не нужна. */
.sheet-backdrop {
  display: none;
}

@media (max-width: 1023px) {
  .sheet-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: var(--z-dropdown);
    background: rgba(5, 0, 56, 0.32);
  }
}

.prof__list {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
}

.prof__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-3);
  text-align: center;
  padding: var(--s-12) var(--s-6);
}

.prof__state-title {
  font-size: var(--t-h3-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.prof__state-text {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-muted);
}

.prof__row { cursor: pointer; }

.prof__row:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.prof__row.is-selected :deep(td) { background: var(--c-accent-subtle); }
.prof__row.is-selected :deep(td:first-child) { box-shadow: inset 3px 0 0 var(--c-accent), inset 0 -1px 0 var(--c-border); }

.prof__source {
  margin: 0 0 var(--s-2);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-quiet);
}

.prof__none {
  color: var(--c-text-quiet);
  font-size: var(--t-caption-size);
}

.prof__empty-text {
  margin: var(--s-2) 0 var(--s-3);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

.prof__name {
  color: var(--c-text);
  font-weight: var(--w-medium);
  min-width: 220px;
}

.prof__sphere { color: var(--c-text-muted); }

.prof__panel {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.prof__panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-3);
}

.prof__panel-name {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.prof__panel-sphere {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.prof__facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-4);
}

.prof__fact {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.prof__fact-value {
  font-size: var(--t-h2-size);
  line-height: var(--t-h2-lh);
  font-weight: var(--w-strong);
  color: var(--c-text);
}

.prof__block {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.prof__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.prof__hint {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}
</style>
