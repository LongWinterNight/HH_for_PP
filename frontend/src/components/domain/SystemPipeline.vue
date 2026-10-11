<script setup>
import { computed } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import { useSteps } from '@/composables/useSteps'
import { money, moneyRub, num } from '@/utils/format'

// Путь вакансии от источника до экрана — схемой с живыми числами.
//
// Шесть узлов и пять переходов. На каждом узле — сколько чего лежит на
// этом шаге прямо сейчас: числа приходят с сервера, а не нарисованы.
//
// Движение здесь означает событие, и только его:
//   — по кнопке схема один раз проигрывает путь настоящей вакансии;
//   — пока идёт сбор, по первым переходам идёт поток.
// В остальное время схема неподвижна: у системы нет бесконечных
// анимаций, и схема, которая шевелится всегда, перестаёт что-либо
// сообщать.
const props = defineProps({
  // Ответ /api/system/state.
  state: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

const ШАГОВ = 6
const { шаг, идёт, запустить } = useSteps(ШАГОВ, { пауза: 1100 })

const сбор = computed(() => props.state?.['сбор'] ?? null)
const база = computed(() => props.state?.['база'] ?? null)
const разбор = computed(() => props.state?.['разбор'] ?? null)
const поиск = computed(() => props.state?.['поиск'] ?? null)
const пример = computed(() => props.state?.['пример'] ?? null)
const идётСбор = computed(() => Boolean(сбор.value?.['идёт']))

const число = (значение) => (значение === null || значение === undefined ? '—' : num(значение))
const доля = (часть, целое) => (целое ? `${Math.round((часть / целое) * 100)} %` : '—')

// Узлы схемы: что это, главное число и две-три подписи под ним.
const узлы = computed(() => {
  const с = сбор.value
  const р = разбор.value
  const б = база.value
  const п = поиск.value
  const последний = с?.['последний']
  return [
    {
      ключ: 'источник',
      имя: 'Источник',
      число: с?.['источник'] ?? 'hh.ru',
      единица: 'публичный API',
      строки: ['ищет в названии и описании', 'название компании в поиске не участвует']
    },
    {
      ключ: 'сбор',
      имя: 'Сбор',
      число: число(с?.['запусков']),
      единица: 'запусков',
      строки: [
        `удачных ${число(с?.['удачных'])}`,
        последний ? `последний принёс ${число(последний['новых'])} новых` : 'сбор ещё не запускался'
      ]
    },
    {
      ключ: 'разбор',
      имя: 'Разбор',
      число: число(р?.['навыков_в_словаре']),
      единица: 'навыков в словаре',
      строки: [
        `в среднем ${р?.['навыков_на_вакансию'] != null ? String(р['навыков_на_вакансию']).replace('.', ',') : '—'} навыка на вакансию`,
        `зарплата указана у ${доля(р?.['с_зарплатой'], р?.['всего'])}`
      ]
    },
    {
      ключ: 'база',
      имя: 'База',
      число: число(б?.['вакансий']),
      единица: 'вакансий',
      строки: [
        `активных ${число(б?.['активных'])}`,
        `с текстом описания ${число(б?.['с_описанием'])}`,
        б?.['не_по_запросу'] ? `скрыто не по запросу ${число(б['не_по_запросу'])}` : ''
      ].filter(Boolean)
    },
    {
      ключ: 'индексы',
      имя: 'Индексы поиска',
      число: число(п?.['документов']),
      единица: 'документов',
      строки: [
        `слов в словаре ${число(п?.['слов_в_словаре'])}`,
        п?.['векторов'] ? `векторов ${число(п['векторов'])} · ${п['модель']}` : 'векторы не посчитаны'
      ]
    },
    {
      ключ: 'экраны',
      имя: 'Экраны',
      число: '6',
      единица: 'рабочих разделов',
      строки: ['список и поиск', 'аналитика и отчёты']
    }
  ]
})

// Что происходит с вакансией на каждом шаге — словами и её же данными.
const рассказ = computed(() => {
  const в = пример.value
  if (!в) return []
  const зарплата = в['зарплата']
    ? money(в['зарплата'], в['валюта'])
      + (в['валюта'] !== 'RUB' && в['в_рублях'] ? ` → ${moneyRub(в['в_рублях'])} по курсу ЦБ` : '')
    : 'зарплата не указана'
  return [
    `Источник отдаёт вакансию по запросу «${в['запрос']}»: слова запроса нашлись в её названии или описании.`,
    'Сбор читает страницу выдачи и карточку вакансии: в карточке — полное описание и навыки, названные работодателем.',
    `Разбор находит в тексте ${в['навыков']} навыков по словарю (${в['навыки'].join(', ')}…), приводит зарплату — ${зарплата} — и читает условия: ${[в['занятость'], в['график']].filter(Boolean).join(', ') || 'не указаны'}.`,
    'В базу ложатся поля вакансии и отдельно — текст описания, один экземпляр на все её копии по городам.',
    'Вакансия попадает в два индекса: по словам — в начальных формах, и по смыслу — вектором локальной модели.',
    'Теперь она видна в списке, находится поиском и входит в медианы и частоты навыков.'
  ]
})

// Узел подсвечен, когда до него дошло проигрывание либо когда на нём
// прямо сейчас идёт работа.
function активен(i) {
  if (идёт.value) return шаг.value === i + 1
  return идётСбор.value && i === 1
}

// По переходу идёт поток: во время сбора — по первым трём, от источника
// до базы и индексов.
function поток(i) {
  return идётСбор.value && !идёт.value && i <= 3
}

// Путь показан до конца и больше не движется.
const досмотрено = computed(() => шаг.value >= ШАГОВ && !идёт.value && рассказ.value.length > 0)

const подпись = computed(() => {
  if (шаг.value > 0 && рассказ.value[шаг.value - 1]) return рассказ.value[шаг.value - 1]
  if (идётСбор.value) {
    const последний = сбор.value?.['последний']
    const запрос = последний?.['текущий_запрос'] ? ` — запрос «${последний['текущий_запрос']}»` : ''
    return `Сейчас идёт сбор${запрос}, готово ${последний?.['процент'] ?? 0} %. Собранное сразу попадает в базу и в индексы поиска.`
  }
  return ''
})
</script>

<template>
  <div class="pipe">
    <!-- Схема — упорядоченный список: программа чтения экрана читает её
         как шесть шагов по порядку, а не как набор блоков. -->
    <ol class="pipe__nodes" aria-label="Путь вакансии от источника до экрана">
      <li
        v-for="(узел, i) in узлы"
        :key="узел.ключ"
        class="pipe__node"
        :class="{ 'is-active': активен(i), 'is-flowing': поток(i), 'is-loading': loading && !state }"
      >
        <div class="pipe__card">
          <div class="pipe__head">
            <span class="pipe__name">{{ узел.имя }}</span>
            <BvStatus v-if="i === 1 && идётСбор" kind="run" label="Идёт" />
          </div>
          <span class="pipe__value">{{ узел.число }}</span>
          <span class="pipe__unit">{{ узел.единица }}</span>
          <ul class="pipe__lines">
            <li v-for="строка in узел.строки" :key="строка">{{ строка }}</li>
          </ul>
        </div>
        <!-- Переход к следующему узлу. Для чтения экрана он лишний:
             порядок уже задан списком. -->
        <span v-if="i < узлы.length - 1" class="pipe__link" aria-hidden="true">
          <span class="pipe__dot"></span>
        </span>
      </li>
    </ol>

    <div class="pipe__foot">
      <div class="pipe__story" aria-live="polite">
        <!-- Проигрывание кончилось — остаётся весь рассказ целиком: по
             нему можно пройти глазами без повторного запуска. Так же
             экран выглядит у тех, кто просил убрать движение. -->
        <ol v-if="досмотрено" class="pipe__all">
          <li v-for="(текст, i) in рассказ" :key="i">
            <span class="pipe__step">{{ узлы[i].имя }}</span>
            {{ текст }}
          </li>
        </ol>
        <template v-else-if="подпись">
          <span v-if="шаг > 0" class="pipe__step">Шаг {{ шаг }} из {{ ШАГОВ }} · {{ узлы[шаг - 1].имя }}</span>
          <p class="pipe__text">{{ подпись }}</p>
        </template>
        <p v-else-if="пример" class="pipe__text pipe__text--quiet">
          Проследите путь одной настоящей вакансии:
          «{{ пример['название'] }}», {{ пример['компания'] }}.
        </p>
        <p v-else class="pipe__text pipe__text--quiet">
          В базе пока нет вакансии, на которой можно показать путь целиком. Запустите сбор — она появится.
        </p>
      </div>
      <BvButton :disabled="!пример || идёт" @click="запустить()">
        {{ шаг > 0 ? 'Показать ещё раз' : 'Показать путь вакансии' }}
      </BvButton>
    </div>
  </div>
</template>

<style scoped>
.pipe {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

/* Шесть узлов в ряд. Колонки сжимаются до нуля: длинное число или
   подпись переносится внутри узла, а не распирает страницу. */
.pipe__nodes {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0;
}

.pipe__node {
  position: relative;
  display: flex;
  min-width: 0;
  /* Место под переход к следующему узлу. */
  padding-right: var(--s-6);
}

.pipe__node:last-child { padding-right: 0; }

.pipe__card {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--s-4);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--border);
  transition: background-color var(--dur-panel) var(--ease-standard),
              box-shadow var(--dur-panel) var(--ease-standard);
}

/* Активный узел — тем же цветом, что статус «Идёт»: это он и есть.
   Отдельного «цвета схемы» в системе нет и не появляется. */
.pipe__node.is-active .pipe__card {
  background: var(--c-status-run-bg);
  box-shadow: inset 0 0 0 2px var(--c-status-run-dot);
}

.pipe__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
  min-height: var(--h-control-sm);
}

.pipe__name {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  font-weight: var(--w-medium);
  color: var(--c-text-secondary);
}

.pipe__value {
  font-size: var(--t-h3-size);
  line-height: 1.2;
  font-weight: var(--w-strong);
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
  overflow-wrap: anywhere;
}

.pipe__unit {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.pipe__lines {
  margin: var(--s-2) 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
  overflow-wrap: anywhere;
}

/* Переход: линия между узлами и точка, которая по ней идёт. */
.pipe__link {
  position: absolute;
  top: 50%;
  right: 0;
  width: var(--s-6);
  height: 2px;
  background: var(--c-border-strong);
}

.pipe__dot {
  position: absolute;
  top: 50%;
  left: 0;
  width: 8px;
  height: 8px;
  margin: -4px 0 0 -4px;
  border-radius: var(--r-pill);
  background: var(--c-status-run-dot);
  opacity: 0;
}

/* Проигрывание: точка один раз проходит переход вслед за активным
   узлом. Один раз — animation-iteration-count по умолчанию. */
.pipe__node.is-active .pipe__dot {
  animation: pipe-pass 900ms var(--ease-standard) 150ms both;
}

/* Сбор идёт: поток не останавливается, пока идёт сбор. Это
   единственное место на экране, где движение не кончается само, — и
   оно означает ровно то, что процесс не кончился. */
.pipe__node.is-flowing .pipe__dot {
  animation: pipe-pass 1400ms linear infinite;
}

@keyframes pipe-pass {
  0% { opacity: 0; transform: translateX(0); }
  15% { opacity: 1; }
  85% { opacity: 1; }
  100% { opacity: 0; transform: translateX(var(--s-6)); }
}

.pipe__node.is-loading .pipe__value { color: var(--c-text-quiet); }

.pipe__foot {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-4);
  padding-top: var(--s-4);
  box-shadow: inset 0 1px 0 var(--c-border);
}

.pipe__story {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
  /* Высота под три строки рассказа: кнопка рядом не прыгает, когда
     подпись сменяется более длинной. */
  min-height: calc(var(--t-body-lh) * 3 + var(--t-caption-lh));
}

.pipe__step {
  font-size: var(--t-caption-size);
  font-weight: var(--w-medium);
  font-variant-numeric: tabular-nums;
  color: var(--c-status-run-text);
}

.pipe__text {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text);
  max-width: 72ch;
}

.pipe__text--quiet { color: var(--c-text-secondary); }

.pipe__all {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
  max-width: 96ch;
}

.pipe__all .pipe__step { margin-right: var(--s-2); }

.pipe__foot :deep(.btn) { flex: 0 0 auto; }

/* До 1024px шесть узлов в ряд — это шесть столбиков по сто пикселей:
   схема встаёт в два ряда по три. */
@media (max-width: 1199px) {
  .pipe__nodes { grid-template-columns: repeat(3, minmax(0, 1fr)); row-gap: var(--s-4); }
  .pipe__node:nth-child(3n) { padding-right: 0; }
  .pipe__node:nth-child(3n) .pipe__link { display: none; }
}

/* На телефоне схема — столбец, переходы идут вниз. */
@media (max-width: 767px) {
  .pipe__nodes { grid-template-columns: minmax(0, 1fr); row-gap: 0; }
  .pipe__node,
  .pipe__node:nth-child(3n) { padding-right: 0; padding-bottom: var(--s-6); }
  .pipe__node:last-child { padding-bottom: 0; }

  .pipe__link,
  .pipe__node:nth-child(3n) .pipe__link {
    display: block;
    top: auto;
    right: auto;
    bottom: 0;
    left: var(--s-6);
    width: 2px;
    height: var(--s-6);
  }

  .pipe__node:last-child .pipe__link { display: none; }

  .pipe__dot { top: 0; left: 50%; }

  .pipe__node.is-active .pipe__dot { animation-name: pipe-pass-down; }
  .pipe__node.is-flowing .pipe__dot { animation-name: pipe-pass-down; }

  .pipe__foot { flex-direction: column; }
  .pipe__story { min-height: 0; }
}

@keyframes pipe-pass-down {
  0% { opacity: 0; transform: translateY(0); }
  15% { opacity: 1; }
  85% { opacity: 1; }
  100% { opacity: 0; transform: translateY(var(--s-6)); }
}

/* Движение — подсказка, а не содержание. Тем, кто просил его убрать,
   схема показывает то же самое без точек и переходов цвета. */
@media (prefers-reduced-motion: reduce) {
  .pipe__card { transition: none; }
  .pipe__node.is-active .pipe__dot,
  .pipe__node.is-flowing .pipe__dot { animation: none; opacity: 0; }
}
</style>
