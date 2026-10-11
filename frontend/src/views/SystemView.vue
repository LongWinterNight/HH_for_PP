<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import FailureFlow from '@/components/domain/FailureFlow.vue'
import SearchExplainer from '@/components/domain/SearchExplainer.vue'
import SystemPipeline from '@/components/domain/SystemPipeline.vue'
import SceneClean from '@/components/domain/story/SceneClean.vue'
import SceneCollect from '@/components/domain/story/SceneCollect.vue'
import SceneParse from '@/components/domain/story/SceneParse.vue'
import SceneSalary from '@/components/domain/story/SceneSalary.vue'
import SceneStore from '@/components/domain/story/SceneStore.vue'
import StoryChapter from '@/components/domain/story/StoryChapter.vue'
import StoryRail from '@/components/domain/story/StoryRail.vue'
import { system } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { num, plural, timeAgo } from '@/utils/format'

// «Как устроено»: что продукт делает с вакансией, шаг за шагом.
//
// Не рабочий экран, а объясняющий. Одна настоящая вакансия из базы
// проходит семь глав — сбор, разбор, очистку, хранение, поиск,
// аналитику, надзор, — и каждая глава показывает свой шаг на её
// данных и на числах всей базы. Сверху — тот же путь одной схемой.
//
// Сцена главы проигрывается сама, когда до неё докрутили, один раз и
// останавливается на итоге. Непрерывно движется только то, что
// действительно идёт: поток по схеме во время сбора.

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
const поиск = computed(() => состояние.data.value?.['поиск'] ?? null)
const герой = computed(() => история.data.value?.['герой'] ?? null)

// Одна строка под заголовком: что система делает прямо сейчас.
const сейчас = computed(() => {
  if (состояние.loading.value && !состояние.data.value) return 'Спрашиваем состояние систем…'
  if (!состояние.data.value) return ''
  // Слова «идёт сбор» говорит метка рядом; повторять их текстом незачем.
  if (идётСбор.value) return 'Числа на схеме обновляются сами.'
  const последний = сбор.value?.['последний']
  if (!последний) return 'Сбор ещё не запускался — схема показывает пустую систему.'
  const когда = последний['завершён'] || последний['начат']
  const исход = { completed: 'прошёл', error: 'не удался', interrupted: 'был оборван', stopped: 'остановлен' }[последний['исход']] ?? последний['исход']
  return `Система в покое. Последний сбор ${исход} ${timeAgo(когда)}.`
})

// Состояние поиска по смыслу — меткой: поднята ли модель.
const смысл = computed(() => {
  const п = поиск.value
  if (!п) return null
  if (!п['смысл_включён']) return { kind: 'stop', label: 'Смысл выключен' }
  if (п['модель_поднята']) return { kind: 'ok', label: `Модель ${п['модель']} поднята` }
  if (п['отказ_модели']) return { kind: 'stop', label: 'Модель недоступна — только слова' }
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

// Что система узнала о вакансии-примере на каждом шаге — строкой в рельсе.
const факты = computed(() => {
  const г = герой.value
  if (!г) return {}
  const з = г['зарплата'] ?? {}
  const х = г['хранение'] ?? {}
  const распределение = история.data.value?.['зарплаты']
  const рубли = з['от_руб'] != null ? `≈ ${num(Math.round(з['от_руб']))} ₽` : ''
  const навыков = г['навыки']?.length ?? 0
  return {
    collect: г['запрос'] ? `найдена запросом «${г['запрос']}»` : '',
    parse: [`${навыков} ${plural(навыков, 'навык', 'навыка', 'навыков')}`, рубли].filter(Boolean).join(' · '),
    clean: 'активна и найдена по запросу — остаётся в списке',
    store: `${х['полей']} ${plural(х['полей'], 'поле', 'поля', 'полей')} · ${num(х['байт_сжато'])} байт текста`
      + (х['размерность'] ? ` · вектор из ${num(х['размерность'])} чисел` : ''),
    search: х['размерность'] ? 'лежит в двух индексах: слова и смысл' : 'лежит в индексе слов',
    salary: з['в_распределении'] && распределение
      ? `её ${рубли} — одна из ${num(распределение['вакансий'])} зарплат распределения`
      : 'в распределение зарплат не входит'
  }
})

// --- какая глава сейчас читается -----------------------------------------

const активная = ref(ГЛАВЫ[0].id)
let кадр = null

function определитьГлаву() {
  кадр = null
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
          Одна настоящая вакансия проходит весь путь — от запроса к источнику до зарплатной медианы.
          На каждом шаге видно, что система делает с ней и со всей базой. Все числа — живые.
        </p>
        <p v-if="сейчас" class="sys__now" aria-live="polite">
          <BvStatus v-if="идётСбор" kind="run" label="Идёт сбор" />
          {{ сейчас }}
        </p>
      </div>
      <BvButton :loading="состояние.loading.value || история.loading.value" @click="обновить()">Обновить числа</BvButton>
    </header>

    <div v-if="состояние.error.value && !состояние.data.value" class="sys__state">
      <p class="sys__state-title">Состояние систем не получено</p>
      <p class="sys__state-text">{{ состояние.error.value }}</p>
      <BvButton :loading="состояние.loading.value" @click="обновить()">Повторить</BvButton>
    </div>

    <template v-else>
      <BvCard title="Весь путь одной схемой">
        <SystemPipeline :state="состояние.data.value" :loading="состояние.loading.value" />
      </BvCard>

      <p v-if="история.error.value && !история.data.value" class="sys__warn" role="alert">
        Данные для глав не получены: {{ история.error.value }} Главы ниже показаны без примеров.
      </p>

      <div class="sys__body">
        <aside class="sys__rail">
          <StoryRail :chapters="ГЛАВЫ" :active="активная" :hero="герой" :facts="факты" @go="перейти" />
        </aside>

        <div class="sys__chapters">
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
            <p v-if="смысл" class="sys__model"><BvStatus :kind="смысл.kind" :label="смысл.label" /></p>
            <p class="sys__lead">
              Слова ловят точные названия — «Corona», «1С», — которые модель смысла размывает. Смысл ловит синонимы
              и перефразы, которых в тексте буквально нет. Ни один способ не лучше другого на всех запросах, поэтому
              работают оба.
            </p>
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
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.sys {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
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

.sys__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.sys__now {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.sys__lead {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
  max-width: 78ch;
}

.sys__model { max-width: none; }

.sys__warn {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-status-err-text);
  max-width: none;
}

/* Рельс глав слева, главы справа. Рельс не уезжает при прокрутке. */
.sys__body {
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
  gap: var(--s-8);
  align-items: start;
}

.sys__rail {
  position: sticky;
  top: calc(var(--h-header) + var(--s-6));
  min-width: 0;
  /* Рельс длиннее окна прокручивается сам, а не обрезается. */
  max-height: calc(100vh - var(--h-header) - var(--s-12));
  overflow-y: auto;
  scrollbar-width: thin;
}

.sys__chapters {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  min-width: 0;
}

.sys__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-3);
  text-align: center;
  padding: var(--s-12) var(--s-6);
}

.sys__state-title {
  font-size: var(--t-h3-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.sys__state-text {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-muted);
}

/* Узкий экран: рельс — лентой под шапкой, на фоне страницы. */
@media (max-width: 1199px) {
  .sys__body { grid-template-columns: minmax(0, 1fr); gap: var(--s-4); }

  .sys__rail {
    top: var(--h-header);
    z-index: 5;
    max-height: none;
    overflow: visible;
    margin-inline: calc(var(--s-2) * -1);
    padding: var(--s-2);
    background: var(--c-canvas);
    box-shadow: inset 0 -1px 0 var(--c-border);
  }
}
</style>
