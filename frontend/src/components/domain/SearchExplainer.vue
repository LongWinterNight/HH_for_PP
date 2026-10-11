<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvField from '@/components/ui/BvField.vue'
import { system } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { useSteps } from '@/composables/useSteps'
import { num, plural } from '@/utils/format'

// Поиск по шагам, на настоящем запросе и настоящих вакансиях.
//
// Человек набирает запрос и видит то, что обычно скрыто за списком:
// как запрос разобран, что нашли слова, что нашёл смысл и как два
// списка слились в один. Считает это тот же код, что ищет на экране
// «Вакансии»: объяснение, которое считает иначе, объясняло бы не его.
//
// Шаги раскрываются по очереди один раз — порядок и есть объяснение.
//
// Слияние показано перелётом: строки итога прилетают со своих мест в
// двух списках. Связь между строкой итога и её местами в списках
// нарисована линией. Раньше при наведении исходные строки просто
// подсвечивались, и это читалось как сбой — «выделение перескочило на
// другую строку»: подсветка без линии не говорит, что строки связаны.
const props = defineProps({
  // Последний замер на эталоне (state['замер']) — числа качества.
  measure: { type: Object, default: null },
  // Разобрать пример, когда до блока докрутили: пустое поле ничего не
  // объясняет, а нажмут «Разобрать» не все.
  autoplay: { type: Boolean, default: true }
})

// Разбор поднимает модель смысла, если она ещё не поднята: экран по
// этому событию перечитывает её состояние.
const emit = defineEmits(['explained'])

const ПРИМЕРЫ = ['питон разработчик', 'дизайнр интерьера', '3д макс мебель', 'рисовать баннеры для соцсетей']
const ШАГОВ = 3

const запрос = ref('')
const разбор = useApi((текст, options) => system.explain(текст, options))
const { шаг, запустить } = useSteps(ШАГОВ, { пауза: 900 })

const данные = computed(() => разбор.data.value)

// Какая вакансия выделена: от её мест в списках к строке итога идёт
// линия. Наведение показывает связь на время, нажатие закрепляет её —
// на сенсорном экране наведения нет.
const наведена = ref('')
const закреплена = ref('')
const выделена = computed(() => наведена.value || закреплена.value)

const корень = ref(null)
const холст = ref(null)
const линии = ref([])
let призраки = []
let наблюдатель = null

const безДвижения = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function убратьПризраков() {
  призраки.forEach((призрак) => призрак.remove())
  призраки = []
}

async function разобрать(текст = запрос.value) {
  const чистый = (текст || '').trim()
  if (!чистый) return
  запрос.value = чистый
  наведена.value = ''
  закреплена.value = ''
  убратьПризраков()
  шаг.value = 0
  const ответ = await разбор.load(чистый)
  if (!ответ) return
  emit('explained')
  запустить()
}

const строка = (список, ид) =>
  холст.value?.querySelector(`[data-list="${список}"][data-id="${CSS.escape(String(ид))}"]`) ?? null

// Радиус поворота линии и отступ желоба от края блока.
const ПОВОРОТ = 6
const ЖЕЛОБ = 7

/**
 * Линии от мест вакансии в двух списках к её строке в итоге.
 *
 * Идут по желобам по краям блока: от списка «по словам» — по левому,
 * от списка «по смыслу» — по правому. Так линия не пересекает ни одной
 * строки, и расклад работает одинаково, стоят списки рядом или друг
 * под другом.
 */
function провести() {
  const ид = выделена.value
  const цель = ид ? строка('итог', ид) : null
  if (!цель || !холст.value) {
    линии.value = []
    return
  }
  const рамка = холст.value.getBoundingClientRect()
  const ц = цель.getBoundingClientRect()
  const y2 = ц.top + ц.height / 2 - рамка.top

  линии.value = [['слова', 1], ['смысл', -1]].flatMap(([список, к]) => {
    const исток = строка(список, ид)
    if (!исток) return []
    const и = исток.getBoundingClientRect()
    const слева = к === 1
    const желоб = слева ? ЖЕЛОБ : рамка.width - ЖЕЛОБ
    const x1 = (слева ? и.left : и.right) - рамка.left
    const x2 = (слева ? ц.left : ц.right) - рамка.left
    const y1 = и.top + и.height / 2 - рамка.top
    const у = желоб + к * ПОВОРОТ
    return [{
      ключ: `${ид}-${список}`,
      путь: `M ${x1} ${y1} H ${у} Q ${желоб} ${y1} ${желоб} ${y1 + ПОВОРОТ} V ${y2 - ПОВОРОТ} Q ${желоб} ${y2} ${у} ${y2} H ${x2}`,
      x1, y1, x2, y2
    }]
  })
}

watch(выделена, () => nextTick(провести))

/**
 * Слияние перелётом: строки итога прилетают из списков.
 *
 * Копия исходной строки летит со своего места на место в итоге и
 * растворяется, а под ней проявляется настоящая строка. Вакансия,
 * найденная обоими способами, собирается из двух копий — в этом и
 * состоит слияние.
 */
function слить() {
  const первые = итог.value['первые']
  if (!холст.value || !первые.length) return
  if (безДвижения() || !Element.prototype.animate) {
    закреплена.value = лучшаяДляПоказа()
    return
  }
  убратьПризраков()
  const рамка = холст.value.getBoundingClientRect()
  const ход = { duration: 950, easing: 'cubic-bezier(0.45, 0, 0.2, 1)' }
  let последняя = null

  первые.forEach((запись, i) => {
    const цель = строка('итог', запись['ид'])
    if (!цель) return
    const ц = цель.getBoundingClientRect()
    const задержка = 250 + i * 130
    const истоки = ['слова', 'смысл'].map((список) => строка(список, запись['ид'])).filter(Boolean)

    for (const исток of истоки) {
      const и = исток.getBoundingClientRect()
      const призрак = исток.cloneNode(true)
      призрак.classList.add('exp__ghost')
      призрак.classList.remove('is-marked')
      призрак.removeAttribute('data-list')
      призрак.setAttribute('aria-hidden', 'true')
      Object.assign(призрак.style, {
        left: `${и.left - рамка.left}px`, top: `${и.top - рамка.top}px`, width: `${и.width}px`, height: `${и.height}px`
      })
      холст.value.appendChild(призрак)
      призраки.push(призрак)
      призрак.animate(
        [
          { transform: 'none', width: `${и.width}px`, opacity: 0 },
          { transform: 'none', width: `${и.width}px`, opacity: 1, offset: 0.12 },
          {
            transform: `translate(${ц.left - и.left}px, ${ц.top - и.top}px)`,
            width: `${ц.width}px`, opacity: 1, offset: 0.86
          },
          { transform: `translate(${ц.left - и.left}px, ${ц.top - и.top}px)`, width: `${ц.width}px`, opacity: 0 }
        ],
        { ...ход, delay: задержка, fill: 'both' }
      ).onfinish = () => призрак.remove()
    }

    // Настоящая строка проявляется под прилетевшей копией. Той, что
    // пришла с места ниже показанных, лететь неоткуда — она опускается.
    последняя = цель.animate(
      истоки.length
        ? [{ opacity: 0 }, { opacity: 0, offset: 0.72 }, { opacity: 1 }]
        : [{ opacity: 0, transform: 'translateY(-8px)' }, { opacity: 1, transform: 'none' }],
      { ...ход, delay: задержка, fill: 'backwards' }
    )
  })

  // Перелёт кончился — одна связь остаётся нарисованной: приём виден и
  // тем, кто не догадается навести.
  if (последняя) {
    последняя.onfinish = () => {
      if (!закреплена.value) закреплена.value = лучшаяДляПоказа()
    }
  }
}

// Строка, на которой связь нагляднее всего: найденная обоими способами.
function лучшаяДляПоказа() {
  const первые = итог.value['первые']
  const обоими = первые.find((запись) => строка('слова', запись['ид']) && строка('смысл', запись['ид']))
  const одним = первые.find((запись) => строка('слова', запись['ид']) || строка('смысл', запись['ид']))
  return (обоими ?? одним)?.['ид'] ?? ''
}

watch(шаг, (номер) => {
  if (номер === 3) nextTick(слить)
})

function закрепить(ид) {
  закреплена.value = закреплена.value === ид ? '' : ид
}

onMounted(() => {
  window.addEventListener('resize', провести)
  if (!props.autoplay || typeof IntersectionObserver === 'undefined' || !корень.value) return
  наблюдатель = new IntersectionObserver(
    ([запись]) => {
      if (!запись.isIntersecting) return
      наблюдатель.disconnect()
      // Пример с опечаткой: на нём видны и исправление, и оба способа.
      if (!данные.value && !разбор.loading.value) разобрать(ПРИМЕРЫ[1])
    },
    { rootMargin: '0px 0px -25% 0px', threshold: 0 }
  )
  наблюдатель.observe(корень.value)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', провести)
  наблюдатель?.disconnect()
  убратьПризраков()
})

// Группы запроса: внутри группы — варианты одного и того же, между
// группами — «и».
const группы = computed(() => (данные.value?.['разбор']?.['группы'] ?? []).map((варианты) =>
  варианты.map((вариант) => (вариант.endsWith('*') ? `${вариант.slice(0, -1)}…` : вариант))
))
const замены = computed(() => Object.entries(данные.value?.['разбор']?.['замены'] ?? {}))

const слова = computed(() => данные.value?.['слова'] ?? { 'найдено': 0, 'первые': [] })
const смысл = computed(() => данные.value?.['смысл'] ?? { 'найдено': 0, 'первые': [] })
const итог = computed(() => данные.value?.['итог'] ?? { 'найдено': 0, 'первые': [] })

const дробь = (число) => String(число ?? '').replace('.', ',')

// Вклад места в оценку слияния: 1 / (k + место).
function вклад(место) {
  const k = данные.value?.k ?? 60
  return место ? 1 / (k + место) : 0
}

// Какую долю оценки дал каждый список — шириной частей полосы. Сами
// вклады — сотые доли единицы: как множитель роста они оставляли полосу
// почти пустой.
function доли(запись) {
  const слова = вклад(запись['место_по_словам'])
  const смысл = вклад(запись['место_по_смыслу'])
  const сумма = слова + смысл || 1
  return { слова: `${(слова / сумма) * 100}%`, смысл: `${(смысл / сумма) * 100}%` }
}

function откуда(запись) {
  const части = []
  if (запись['место_по_словам']) части.push(`слова №${запись['место_по_словам']}`)
  if (запись['место_по_смыслу']) части.push(`смысл №${запись['место_по_смыслу']}`)
  return части.join(' + ')
}

// Почему смысл не участвовал — словами, а не пустым столбцом.
const оСмысле = computed(() => {
  const с = смысл.value
  if (с['участвовал']) return ''
  if (!с['доступен']) return 'Модель векторов не поднята — поиск идёт только по словам.'
  return `Ни одна вакансия не близка запросу настолько, чтобы считаться найденной (порог ${дробь(с['порог'])}).`
})

// Числа замера — полосами. Порядок задан: от одного способа к двум.
const качество = computed(() => {
  const способы = props.measure?.['способы']
  if (!способы) return []
  return Object.entries(способы).map(([имя, числа]) => ({
    // Модель названа в пояснении под полосами: в подписи строки она
    // не помещалась и обрезалась многоточием.
    label: имя === 'слова' ? 'только слова' : имя.startsWith('смысл') ? 'только смысл' : 'слова и смысл',
    value: Math.round(числа['ndcg'] * 1000) / 1000
  }))
})
</script>

<template>
  <div ref="корень" class="exp">
    <form class="exp__form" @submit.prevent="разобрать()">
      <BvField
        v-model="запрос"
        label="Запрос"
        placeholder="Профессия, навык или задача словами"
        hint="Тот же поиск, что на экране «Вакансии», — с показом каждого шага."
      />
      <!-- Главное действие экрана — единственная окрашенная кнопка. -->
      <BvButton variant="primary" type="submit" :loading="разбор.loading.value" :disabled="!запрос.trim()">
        Разобрать запрос
      </BvButton>
    </form>

    <div class="exp__examples">
      <span class="exp__examples-label">Например:</span>
      <BvButton v-for="пример in ПРИМЕРЫ" :key="пример" size="sm" @click="разобрать(пример)">{{ пример }}</BvButton>
    </div>

    <p v-if="разбор.error.value" class="exp__error" role="alert">{{ разбор.error.value }}</p>

    <div v-if="данные" ref="холст" class="exp__steps" aria-live="polite">
      <!-- Шаг 1 · разбор запроса -->
      <section v-if="шаг >= 1" class="exp__step">
        <h3 class="exp__step-title"><span class="exp__num">1</span> Запрос разобран</h3>
        <div class="exp__groups">
          <template v-for="(варианты, i) in группы" :key="i">
            <span v-if="i > 0" class="exp__and">и</span>
            <span class="exp__group" :style="{ '--i': i }">
              <template v-for="(вариант, j) in варианты" :key="вариант">
                <span v-if="j > 0" class="exp__or">или</span>
                <span class="exp__term">{{ вариант }}</span>
              </template>
            </span>
          </template>
        </div>
        <p class="exp__note">
          Слова приведены к начальной форме — так же, как в индексе.
          <template v-if="замены.length">
            Добавлено:
            <template v-for="([было, стало], i) in замены" :key="было">
              <template v-if="i > 0">; </template>«{{ было }}» → {{ стало }}
            </template>.
          </template>
          <template v-if="данные['разбор']['ослаблен']">
            Вакансий со всеми словами нет — условие ослаблено до «любое из слов».
          </template>
        </p>
      </section>

      <!-- Шаг 2 · два способа -->
      <section v-if="шаг >= 2" class="exp__step">
        <h3 class="exp__step-title"><span class="exp__num">2</span> Два способа ищут независимо</h3>
        <div class="exp__lists">
          <div class="exp__list">
            <h4 class="exp__list-title">
              По словам
              <span class="exp__count">{{ num(слова['найдено']) }}</span>
            </h4>
            <p v-if="!слова['первые'].length" class="exp__empty">Слов запроса в вакансиях нет.</p>
            <ol v-else class="exp__rows">
              <li
                v-for="(запись, i) in слова['первые']"
                :key="запись['ид']"
                class="exp__row exp__row--source"
                :class="{ 'is-marked': выделена === запись['ид'] }"
                :style="{ '--i': i }"
                data-list="слова"
                :data-id="запись['ид']"
                @mouseenter="наведена = запись['ид']"
                @mouseleave="наведена = ''"
                @click="закрепить(запись['ид'])"
              >
                <span class="exp__place">{{ запись['место_по_словам'] }}</span>
                <span class="exp__name">
                  {{ запись['название'] }}
                  <span class="exp__company">{{ запись['компания'] }}</span>
                </span>
                <span class="exp__why">{{ запись['почему'] }}</span>
              </li>
            </ol>
          </div>

          <div class="exp__list">
            <h4 class="exp__list-title">
              По смыслу
              <span class="exp__count">{{ num(смысл['найдено']) }}</span>
            </h4>
            <p v-if="оСмысле" class="exp__empty">{{ оСмысле }}</p>
            <ol v-else class="exp__rows">
              <li
                v-for="(запись, i) in смысл['первые']"
                :key="запись['ид']"
                class="exp__row exp__row--source"
                :class="{ 'is-marked': выделена === запись['ид'] }"
                :style="{ '--i': i }"
                data-list="смысл"
                :data-id="запись['ид']"
                @mouseenter="наведена = запись['ид']"
                @mouseleave="наведена = ''"
                @click="закрепить(запись['ид'])"
              >
                <span class="exp__place">{{ запись['место_по_смыслу'] }}</span>
                <span class="exp__name">
                  {{ запись['название'] }}
                  <span class="exp__company">{{ запись['компания'] }}</span>
                </span>
                <!-- Близость — полосой: по числу 0,634 не видно, много это или мало. -->
                <span class="exp__near" :title="`близость ${дробь(запись['близость'])}`">
                  <span class="exp__near-bar" :style="{ width: `${Math.round((запись['близость'] ?? 0) * 100)}%` }"></span>
                </span>
              </li>
            </ol>
            <p v-if="!оСмысле" class="exp__note">
              Модель {{ смысл['модель'] }} на видеокарте этой машины; тексты наружу не уходят.
              Ниже близости {{ дробь(смысл['порог']) }} вакансия найденной не считается.
            </p>
          </div>
        </div>
      </section>

      <!-- Шаг 3 · слияние -->
      <section v-if="шаг >= 3" class="exp__step exp__step--merge">
        <h3 class="exp__step-title"><span class="exp__num">3</span> Списки слиты по местам</h3>
        <p v-if="!итог['первые'].length" class="exp__empty">
          Ничего не найдено: слов запроса в вакансиях нет, и по смыслу ни одна не подошла.
        </p>
        <template v-else>
          <ol class="exp__rows exp__rows--merged">
            <li
              v-for="(запись, i) in итог['первые']"
              :key="запись['ид']"
              class="exp__row exp__row--merged"
              :class="{ 'is-marked': выделена === запись['ид'] }"
              data-list="итог"
              :data-id="запись['ид']"
              tabindex="0"
              @mouseenter="наведена = запись['ид']"
              @mouseleave="наведена = ''"
              @focus="наведена = запись['ид']"
              @blur="наведена = ''"
              @click="закрепить(запись['ид'])"
              @keydown.enter.prevent="закрепить(запись['ид'])"
              @keydown.space.prevent="закрепить(запись['ид'])"
            >
              <span class="exp__place">{{ i + 1 }}</span>
              <span class="exp__name">
                {{ запись['название'] }}
                <span class="exp__company">{{ запись['компания'] }}</span>
              </span>
              <span class="exp__from">{{ откуда(запись) }}</span>
              <!-- Из чего сложилась оценка: вклад каждого списка одной полосой. -->
              <span class="exp__score" aria-hidden="true">
                <span class="exp__score-part exp__score-part--words" :style="{ width: доли(запись).слова }"></span>
                <span class="exp__score-part exp__score-part--sense" :style="{ width: доли(запись).смысл }"></span>
              </span>
            </li>
          </ol>
          <p class="exp__note">
            Каждый список даёт вакансии 1 / ({{ данные.k }} + место), вклады складываются: найденное обоими способами
            встаёт выше найденного одним. Полоса справа — чья доля в оценке: тёмная часть от слов, светлая от смысла.
            Линия показывает, с каких мест строка пришла в итог: слева — из списка по словам, справа — по смыслу.
            Наведите на любую строку или нажмите на неё, чтобы увидеть её путь.
            Всего найдено {{ num(итог['найдено']) }} {{ plural(итог['найдено'], 'вакансия', 'вакансии', 'вакансий') }}
            за {{ данные['мс'] }} мс.
          </p>
        </template>
      </section>

      <svg v-if="линии.length" class="exp__wires" aria-hidden="true">
        <g v-for="линия in линии" :key="линия.ключ">
          <path class="exp__wire" :d="линия.путь" pathLength="1" />
          <circle class="exp__wire-end" :cx="линия.x1" :cy="линия.y1" r="3" />
          <circle class="exp__wire-end exp__wire-end--to" :cx="линия.x2" :cy="линия.y2" r="3" />
        </g>
      </svg>
    </div>

    <!-- Качество: чем и на чём меряли. Без оговорок число обещало бы
         больше, чем за ним стоит. -->
    <section v-if="качество.length" class="exp__quality">
      <h3 class="exp__step-title">Насколько это точно</h3>
      <BvBarList :items="качество" :format="(v) => v.toFixed(3).replace('.', ',')" />
      <p class="exp__note">
        Качество первых десяти мест (nDCG@10, от 0 до 1) на эталоне: {{ measure['запросов'] }}
        {{ plural(measure['запросов'], 'запрос', 'запроса', 'запросов') }}, {{ num(measure['пар']) }} размеченных пар,
        замер от {{ measure['когда'].split('-').reverse().join('.') }}. Разметка — {{ measure['разметка'] }}.
      </p>
    </section>
  </div>
</template>

<style scoped>
.exp {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.exp__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--s-3);
  align-items: start;
}

/* Кнопка встаёт на уровень поля, а не его подписи. */
.exp__form :deep(.btn) { margin-top: calc(var(--t-caption-lh) + var(--s-1)); }

.exp__examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.exp__examples-label,
.exp__note,
.exp__empty {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.exp__error {
  font-size: var(--t-caption-size);
  color: var(--c-status-err-text);
}

/* По краям блока — желоба, по которым идут линии связи. */
.exp__steps {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  padding-inline: var(--s-4);
}

/* Линии связи: от мест в списках к строке итога. */
.exp__wires {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  pointer-events: none;
}

.exp__wire {
  fill: none;
  stroke: var(--c-text);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  animation: exp-draw 380ms var(--ease-standard) forwards;
}

.exp__wire-end { fill: var(--c-text); }
.exp__wire-end--to {
  opacity: 0;
  animation: exp-dot 120ms var(--ease-standard) 340ms forwards;
}

@keyframes exp-draw { to { stroke-dashoffset: 0; } }
@keyframes exp-dot { to { opacity: 1; } }

/* Копия строки, летящая из списка в итог. */
.exp__ghost {
  position: absolute;
  z-index: 2;
  margin: 0;
  pointer-events: none;
  background: var(--c-surface);
  box-shadow: var(--border-strong);
  will-change: transform, width;
  /* Копия не повторяет появление строки, с которой снята. */
  animation: none;
}

.exp__step {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
  animation: exp-in var(--dur-enter) var(--ease-enter) both;
}

@keyframes exp-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

/* Шаг слияния не въезжает целиком: его строки прилетают из списков, и
   их места замеряются сразу, без поправки на собственное движение. */
.exp__step--merge { animation: none; }

/* Группы запроса и строки списков появляются по одной. */
.exp__group,
.exp__and,
.exp__row--source {
  animation: exp-in var(--dur-enter) var(--ease-enter) both;
  animation-delay: calc(var(--i, 0) * 70ms + 120ms);
}

.exp__step-title {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.exp__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--r-pill);
  box-shadow: var(--border-strong);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-secondary);
}

/* Группы запроса: рамка вокруг вариантов одного и того же. */
.exp__groups {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.exp__group {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-1) var(--s-2);
  border-radius: var(--r-md);
  box-shadow: var(--border-strong);
}

.exp__term {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--t-caption-size);
  color: var(--c-text);
  overflow-wrap: anywhere;
}

.exp__and,
.exp__or {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.exp__lists {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--s-6);
}

.exp__list {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.exp__list-title {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  font-size: var(--t-caption-size);
  font-weight: var(--w-medium);
  color: var(--c-text-secondary);
}

.exp__count {
  font-variant-numeric: tabular-nums;
  font-weight: var(--w-regular);
  color: var(--c-text-muted);
}

.exp__rows {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  position: relative;
}

.exp__row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--s-2);
  min-height: var(--h-control-md);
  padding: var(--s-1) var(--s-2);
  border-radius: var(--r-sm);
  box-shadow: inset 0 -1px 0 var(--c-border);
  transition: var(--t-hover);
}

/* Строка, по которой видно происхождение итога: та же подложка, что у
   наведения в таблицах. */
.exp__row.is-marked {
  background: var(--c-surface-hover);
  box-shadow: inset 2px 0 0 var(--c-text), inset 0 -1px 0 var(--c-border);
}

.exp__place {
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-muted);
}

.exp__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.exp__company {
  margin-left: var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.exp__why,
.exp__from {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  white-space: nowrap;
}

/* Близость: трек и заполнение — те же, что у полосы прогресса. */
.exp__near {
  width: 56px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--c-surface-sunken);
  overflow: hidden;
}

.exp__near-bar {
  display: block;
  height: 100%;
  border-radius: var(--r-pill);
  background: var(--c-text-secondary);
}

.exp__row--source,
.exp__row--merged { cursor: pointer; }

.exp__row--merged { grid-template-columns: 24px minmax(0, 1fr) auto 72px; }

.exp__row--merged:focus-visible { outline: none; box-shadow: var(--focus-ring); }

/* Оценка слияния: две части одной полосы, шириной по вкладу списка.
   Различаются тоном одной шкалы, а не цветами: в системе категории не
   кодируются цветом. */
.exp__score {
  display: flex;
  height: 6px;
  border-radius: var(--r-pill);
  overflow: hidden;
  background: var(--c-surface-sunken);
}

.exp__score-part { flex: 0 0 auto; min-width: 0; }
.exp__score-part--words { background: var(--c-text); }
.exp__score-part--sense { background: var(--c-text-muted); }

/* Близость растёт от нуля: длина полосы — мера, и её рост читается как измерение. */
.exp__near-bar {
  transform-origin: left center;
  animation: exp-grow 600ms var(--ease-enter) both;
  animation-delay: 260ms;
}

@keyframes exp-grow { from { transform: scaleX(0); } }

.exp__quality {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding-top: var(--s-5);
  box-shadow: inset 0 1px 0 var(--c-border);
}

@media (max-width: 767px) {
  .exp__form { grid-template-columns: minmax(0, 1fr); }
  .exp__form :deep(.btn) { margin-top: 0; }
  .exp__lists { grid-template-columns: minmax(0, 1fr); gap: var(--s-5); }
  /* Происхождение уходит под название: в одну строку всё не помещается. */
  .exp__row--merged { grid-template-columns: 24px minmax(0, 1fr); row-gap: 2px; }
  .exp__row--merged .exp__from { grid-column: 2; }
  .exp__row--merged .exp__score { grid-column: 2; }
  .exp__company { display: none; }
}

@media (max-width: 767px) {
  .exp__steps { padding-inline: var(--s-3); }
}

@media (prefers-reduced-motion: reduce) {
  .exp__step,
  .exp__group,
  .exp__and,
  .exp__row--source,
  .exp__near-bar { animation: none; }
  .exp__wire { animation: none; stroke-dashoffset: 0; }
  .exp__wire-end--to { animation: none; opacity: 1; }
  .exp__row { transition: none; }
}
</style>
