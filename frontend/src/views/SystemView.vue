<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvKpiTile from '@/components/ui/BvKpiTile.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import FailureFlow from '@/components/domain/FailureFlow.vue'
import SearchExplainer from '@/components/domain/SearchExplainer.vue'
import SceneClean from '@/components/domain/story/SceneClean.vue'
import SceneCollect from '@/components/domain/story/SceneCollect.vue'
import SceneParse from '@/components/domain/story/SceneParse.vue'
import SceneSalary from '@/components/domain/story/SceneSalary.vue'
import SceneStore from '@/components/domain/story/SceneStore.vue'
import StoryChapter from '@/components/domain/story/StoryChapter.vue'
import { system } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { num, timeAgo } from '@/utils/format'
import '@/styles/story.css'

// «Как устроено»: что продукт делает с вакансией, шаг за шагом.
//
// Не рабочий экран, а объясняющий, но собран из тех же частей, что
// рабочие: плитки показателей сверху, карточки на холсте, таблицы,
// полосы шкалы величин, статусы. Одна настоящая вакансия из базы
// проходит семь глав — сбор, разбор, очистку, хранение, поиск,
// аналитику, надзор.
//
// Сцена главы проигрывается сама, когда до неё докрутили, один раз и
// останавливается на итоге. Движение — на токенах системы.

const состояние = useApi((options) => system.state(options))
const история = useApi((options) => system.story(options))

// Пока идёт сбор, числа меняются каждую минуту — экран спрашивает их
// снова. В покое опроса нет: спрашивать раз в три секунды то, что
// меняется раз в сутки, незачем.
const ПАУЗА_ПРИ_СБОРЕ = 4000
let таймер = null

const идётСбор = computed(() => Boolean(состояние.data.value?.['сбор']?.['идёт']))

function опросить() {
  остановитьОпрос()
  if (!идётСбор.value) return
  таймер = setTimeout(async () => {
    await состояние.load()
    опросить()
  }, ПАУЗА_ПРИ_СБОРЕ)
}

function остановитьОпрос() {
  if (таймер) clearTimeout(таймер)
  таймер = null
}

watch(идётСбор, опросить)

// Человек вернулся на вкладку — числа могли уйти вперёд.
function приВозврате() {
  if (document.visibilityState === 'visible') состояние.load()
}

function обновить() {
  состояние.load()
  история.load()
}

const сбор = computed(() => состояние.data.value?.['сбор'] ?? null)
const база = computed(() => состояние.data.value?.['база'] ?? null)
const разбор = computed(() => состояние.data.value?.['разбор'] ?? null)
const поиск = computed(() => состояние.data.value?.['поиск'] ?? null)
const герой = computed(() => история.data.value?.['герой'] ?? null)

const загрузка = computed(() => состояние.loading.value && !состояние.data.value)

// Одна строка под заголовком: что система делает прямо сейчас.
const сейчас = computed(() => {
  if (загрузка.value) return 'Спрашиваем состояние систем…'
  if (!состояние.data.value) return ''
  // Слова «идёт сбор» говорит метка рядом; повторять их текстом незачем.
  if (идётСбор.value) return 'Числа обновляются сами.'
  const последний = сбор.value?.['последний']
  if (!последний) return 'Сбор ещё не запускался.'
  const когда = последний['завершён'] || последний['начат']
  const исход = { completed: 'прошёл', error: 'не удался', interrupted: 'был оборван', stopped: 'остановлен' }[последний['исход']] ?? последний['исход']
  return `Последний сбор ${исход} ${timeAgo(когда)}.`
})

const число = (значение) => (значение === null || значение === undefined ? null : num(значение))

// Состояние поиска по смыслу — меткой: поднята ли модель.
const смысл = computed(() => {
  const п = поиск.value
  if (!п) return null
  if (!п['смысл_включён']) return { kind: 'stop', label: 'Смысл выключен' }
  if (п['модель_поднята']) return { kind: 'ok', label: `Модель ${п['модель']} поднята` }
  if (п['отказ_модели']) return { kind: 'stop', label: 'Только слова' }
  return { kind: 'idle', label: 'Модель поднимется при первом поиске' }
})

// Главы в порядке пути вакансии. Вопрос — тот, на который глава отвечает.
const ГЛАВЫ = [
  { id: 'collect', number: 1, title: 'Сбор', question: 'Откуда берутся вакансии и что принёс каждый запрос последнего сбора.' },
  { id: 'parse', number: 2, title: 'Разбор', question: 'Что система читает из текста одной вакансии — и где именно.' },
  { id: 'clean', number: 3, title: 'Очистка', question: 'Что из собранного не попадает в список и числа. Ничего не удаляется.' },
  { id: 'store', number: 4, title: 'Хранение', question: 'В каком виде вакансия лежит в базе и кому нужен каждый вид.' },
  { id: 'search', number: 5, title: 'Поиск', question: 'Почему по запросу находится именно это: слова и смысл ищут порознь, списки сливаются.' },
  { id: 'salary', number: 6, title: 'Аналитика', question: 'Почему в зарплатах стоит медиана, а не средняя.' },
  { id: 'watch', number: 7, title: 'Надзор', question: 'Что произойдёт, если сбор упадёт, и кто об этом узнает.' }
]

const РАЗДЕЛЫ = ГЛАВЫ.map((глава) => ({ value: глава.id, label: глава.title }))

// --- какая глава сейчас читается -----------------------------------------

const активная = ref(ГЛАВЫ[0].id)
let кадр = null
// Пока страница едет к выбранной главе, переключатель не перескакивает
// по главам, которые она проезжает.
let едемДо = 0

function определитьГлаву() {
  кадр = null
  if (performance.now() < едемДо) return
  // Читается та глава, чей заголовок последним прошёл верхнюю треть окна.
  const черта = window.innerHeight * 0.38
  let найдена = ГЛАВЫ[0].id
  for (const глава of ГЛАВЫ) {
    const узел = document.getElementById(`chapter-${глава.id}`)
    if (узел && узел.getBoundingClientRect().top <= черта) найдена = глава.id
  }
  активная.value = найдена
}

function приПрокрутке() {
  if (кадр === null) кадр = requestAnimationFrame(определитьГлаву)
}

function перейти(ид) {
  const плавно = !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  активная.value = ид
  едемДо = performance.now() + (плавно ? 900 : 0)
  document.getElementById(`chapter-${ид}`)?.scrollIntoView({ behavior: плавно ? 'smooth' : 'auto', block: 'start' })
}

// --- сцены ---------------------------------------------------------------

const сцены = { collect: ref(null), parse: ref(null), clean: ref(null), store: ref(null), salary: ref(null), watch: ref(null) }
const идёт = (ид) => Boolean(сцены[ид]?.value?.идёт)
const повторить = (ид) => сцены[ид]?.value?.повторить()

onMounted(() => {
  обновить()
  document.addEventListener('visibilitychange', приВозврате)
  window.addEventListener('scroll', приПрокрутке, { passive: true })
  window.addEventListener('resize', приПрокрутке, { passive: true })
})

onBeforeUnmount(() => {
  остановитьОпрос()
  if (кадр !== null) cancelAnimationFrame(кадр)
  document.removeEventListener('visibilitychange', приВозврате)
  window.removeEventListener('scroll', приПрокрутке)
  window.removeEventListener('resize', приПрокрутке)
})
</script>

<template>
  <section class="sys">
    <header class="sys__head">
      <div class="sys__titles">
        <h1>Как устроено</h1>
        <p class="sys__meta">
          Путь вакансии от запроса к источнику до зарплатной медианы — на одной настоящей вакансии из базы.
          <template v-if="сейчас">{{ сейчас }}</template>
        </p>
      </div>
      <div class="sys__actions">
        <BvStatus v-if="идётСбор" kind="run" label="Идёт сбор" />
        <BvButton :loading="состояние.loading.value || история.loading.value" @click="обновить()">Обновить числа</BvButton>
      </div>
    </header>

    <BvBanner
      v-if="состояние.error.value && !состояние.data.value"
      kind="error"
      title="Состояние систем не получено"
      :text="состояние.error.value"
    >
      <template #actions>
        <BvButton size="sm" :loading="состояние.loading.value" @click="обновить()">Повторить</BvButton>
      </template>
    </BvBanner>

    <template v-else>
      <!-- Тот же ряд плиток, которым открываются рабочие экраны. -->
      <div class="st-grid st-grid--kpi">
        <BvKpiTile
          no-trend
          label="Вакансий в базе"
          :value="число(база?.['вакансий'])"
          :note="база ? `активных ${num(база['активных'])}` : ''"
          :loading="загрузка"
        />
        <BvKpiTile
          no-trend
          label="Навыков в словаре"
          :value="число(разбор?.['навыков_в_словаре'])"
          :note="разбор ? `и ${num(разбор['написаний'])} вариантов написания` : ''"
          :loading="загрузка"
        />
        <BvKpiTile
          no-trend
          label="Вакансий в поиске"
          :value="число(поиск?.['документов'])"
          :note="поиск ? `векторов смысла ${num(поиск['векторов'])}` : ''"
          :loading="загрузка"
        />
        <BvKpiTile
          no-trend
          label="Сборов"
          :value="число(сбор?.['запусков'])"
          :note="сбор ? `из них удачных ${num(сбор['удачных'])}` : ''"
          :loading="загрузка"
        />
      </div>

      <!-- Лента глав стоит под шапкой при прокрутке: по ней видно, где ты, и можно перейти. -->
      <div class="sys__nav" data-print-hide>
        <BvSegmented :model-value="активная" :options="РАЗДЕЛЫ" label="Главы: путь вакансии" @update:model-value="перейти" />
      </div>

      <BvBanner
        v-if="герой"
        kind="info"
        :title="`Вакансия-пример: ${герой['название']}`"
        :text="`${[герой['компания'], герой['регион']].filter(Boolean).join(' · ')}. На ней показаны разбор и хранение; найдена запросом «${герой['запрос']}».`"
      />
      <BvBanner
        v-else-if="история.error.value"
        kind="error"
        title="Данные для глав не получены"
        :text="`${история.error.value} Главы ниже показаны без примеров.`"
      />

      <StoryChapter v-bind="ГЛАВЫ[0]" :playing="идёт('collect')" @replay="повторить('collect')">
        <SceneCollect :ref="сцены.collect" :data="история.data.value?.['сбор'] ?? null" :hero-query="герой?.['запрос'] ?? ''" />
      </StoryChapter>

      <StoryChapter v-bind="ГЛАВЫ[1]" :playing="идёт('parse')" @replay="повторить('parse')">
        <SceneParse :ref="сцены.parse" :hero="герой" />
      </StoryChapter>

      <StoryChapter v-bind="ГЛАВЫ[2]" :playing="идёт('clean')" @replay="повторить('clean')">
        <SceneClean :ref="сцены.clean" :data="история.data.value?.['очистка'] ?? null" />
      </StoryChapter>

      <StoryChapter v-bind="ГЛАВЫ[3]" :playing="идёт('store')" @replay="повторить('store')">
        <SceneStore :ref="сцены.store" :hero="герой" />
      </StoryChapter>

      <StoryChapter v-bind="ГЛАВЫ[4]" :replayable="false">
        <template v-if="смысл" #aside>
          <BvStatus :kind="смысл.kind" :label="смысл.label" />
        </template>
        <SearchExplainer :measure="состояние.data.value?.['замер'] ?? null" @explained="состояние.load()" />
      </StoryChapter>

      <StoryChapter v-bind="ГЛАВЫ[5]" :playing="идёт('salary')" @replay="повторить('salary')">
        <SceneSalary :ref="сцены.salary" :data="история.data.value?.['зарплаты'] ?? null" />
      </StoryChapter>

      <StoryChapter v-bind="ГЛАВЫ[6]" :playing="идёт('watch')" @replay="повторить('watch')">
        <FailureFlow
          :ref="сцены.watch"
          :watchdog="состояние.data.value?.['надзор'] ?? null"
          :guard="история.data.value?.['защита'] ?? null"
        />
      </StoryChapter>
    </template>
  </section>
</template>

<style scoped>
.sys {
  display: flex;
  flex-direction: column;
  gap: var(--s-8);
}

.sys__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.sys__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.sys__meta { color: var(--c-text-secondary); }

.sys__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-3);
}

/* Лента глав липнет под шапку. Подложка — цвет холста: карточки
   проезжают под ней, а не сквозь неё. */
.sys__nav {
  position: sticky;
  top: var(--h-header);
  z-index: 5;
  display: flex;
  margin: calc(var(--s-3) * -1) 0;
  padding: var(--s-3) 0;
  background: var(--c-canvas);
}

/* Главы отделены друг от друга заметнее, чем карточки внутри главы. */
.sys :deep(.chapter) { margin-top: var(--s-6); }
</style>
