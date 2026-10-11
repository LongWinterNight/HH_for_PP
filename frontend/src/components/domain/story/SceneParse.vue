<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvProgress from '@/components/ui/BvProgress.vue'
import { useScene } from '@/composables/useScene'
import { moneyExact, num, salaryPeriod } from '@/utils/format'

// Разбор: что система читает из текста вакансии.
//
// По настоящему описанию идёт чтение: прочитанное темнеет, найденные
// навыки отмечаются в тексте и сразу встают чипами в соседнюю карточку.
// Места отметок приходят с сервера и найдены тем же способом, что при
// разборе, — сцена показывает поиск, а не рисует его.
//
// Ход чтения — полоса хода работ системы: это и есть процесс.
const props = defineProps({
  // story['герой'] из /api/system/story.
  hero: { type: Object, default: null }
})

const ШАГОВ = 4 // чтение, навыки вне отрывка, зарплата, условия

const отрывок = computed(() => props.hero?.['отрывок'] ?? null)
const текст = computed(() => отрывок.value?.['текст'] ?? '')

// Чтение идёт со скоростью, при которой за ним успеваешь следить, и не
// дольше шести секунд: сцена объясняет порядок, а не заставляет ждать.
const времяЧтения = computed(() => Math.min(6000, Math.max(2400, текст.value.length * 10)))

const сцена = useScene(ШАГОВ, {
  пауза: (номер) => (номер === 1 ? времяЧтения.value + 240 : 700),
  готово: () => Boolean(props.hero)
})
const { корень, шаг, идёт, безДвижения } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

// Докуда дочитано, в знаках отрывка.
const дочитано = ref(0)
let кадр = null

function читать() {
  cancelAnimationFrame(кадр)
  if (безДвижения()) {
    дочитано.value = текст.value.length
    return
  }
  const начало = performance.now()
  const дальше = (сейчас) => {
    const доля = Math.min(1, (сейчас - начало) / времяЧтения.value)
    дочитано.value = Math.round(текст.value.length * доля)
    if (доля < 1) кадр = requestAnimationFrame(дальше)
  }
  кадр = requestAnimationFrame(дальше)
}

watch(шаг, (номер) => {
  if (номер === 0) {
    cancelAnimationFrame(кадр)
    дочитано.value = 0
  } else if (номер === 1 && идёт.value) {
    читать()
  } else {
    // Сцену показали сразу итогом или чтение уже кончилось.
    cancelAnimationFrame(кадр)
    дочитано.value = текст.value.length
  }
})

onBeforeUnmount(() => cancelAnimationFrame(кадр))

// Текст кусками: обычные куски по несколько слов и куски-навыки. Мелкая
// нарезка нужна, чтобы прочитанное темнело ровно, а не абзацами.
const куски = computed(() => {
  const итог = []
  const обычный = (от, до) => {
    let позиция = от
    for (const слова of текст.value.slice(от, до).match(/\S+\s*(?:\S+\s*){0,3}|\s+/g) ?? []) {
      итог.push({ от: позиция, текст: слова })
      позиция += слова.length
    }
  }
  let позиция = 0
  for (const место of отрывок.value?.['навыки'] ?? []) {
    if (место['от'] > позиция) обычный(позиция, место['от'])
    итог.push({
      от: место['от'], до: место['до'], текст: текст.value.slice(место['от'], место['до']),
      навык: место['навык'], как: место['как']
    })
    позиция = место['до']
  }
  if (позиция < текст.value.length) обычный(позиция, текст.value.length)
  return итог
})

// Навык найден, когда чтение дошло до конца слова, которым он написан.
const найденВТексте = computed(() => {
  const найдены = new Map()
  for (const место of отрывок.value?.['навыки'] ?? []) {
    if (место['до'] <= дочитано.value && !найдены.has(место['навык'])) {
      найдены.set(место['навык'], текст.value.slice(место['от'], место['до']))
    }
  }
  return найдены
})

const навыки = computed(() => props.hero?.['навыки'] ?? [])
const изТекста = computed(() => навыки.value.filter((навык) => навык['откуда'] === 'отрывок'))
// Всё, что найдено не в показанном куске: дальше по тексту, в списке
// работодателя или по словам составного названия.
const остальные = computed(() => навыки.value.filter((навык) => навык['откуда'] !== 'отрывок'))

const ОТКУДА = {
  'текст': 'дальше в тексте',
  'работодатель': 'назвал работодатель',
  'по частям': 'по словам названия'
}

// Написано ли в тексте не так, как называется навык: «визуализаций» →
// «Визуализация». Тогда рядом с навыком стоит слово из текста.
function написано(навык) {
  const слово = найденВТексте.value.get(навык['название'])
  return слово && слово.toLowerCase() !== навык['название'].toLowerCase() ? слово : ''
}

const прочитано = computed(() => дочитано.value >= текст.value.length && текст.value.length > 0)
const ход = computed(() => ({
  подпись: шаг.value === 0 ? 'Описание ещё не прочитано' : прочитано.value ? 'Описание прочитано' : 'Читаем описание',
  итог: `найдено навыков: ${найденВТексте.value.size} из ${изТекста.value.length}`
}))

const зарплата = computed(() => props.hero?.['зарплата'] ?? null)
const знак = (валюта) => moneyExact(0, валюта)?.replace(/^0\s*/, '') ?? валюта
function вилка(от, до, валюта) {
  const части = [от, до].filter((сумма) => сумма != null).map((сумма) => num(Math.round(сумма)))
  if (!части.length) return ''
  return `${от != null && до == null ? 'от ' : ''}${части.join(' — ')} ${знак(валюта)}`
}
const вВалюте = computed(() => вилка(зарплата.value?.['от'], зарплата.value?.['до'], зарплата.value?.['валюта']))
const переводится = computed(() => Boolean(зарплата.value?.['курс'] && зарплата.value?.['от_руб']))
const вРублях = computed(() => вилка(зарплата.value?.['от_руб'], зарплата.value?.['до_руб'], 'RUB'))
const курс = computed(() => String(Math.round((зарплата.value?.['курс'] ?? 0) * 10000) / 10000).replace('.', ','))
const датаКурса = computed(() => (зарплата.value?.['дата_курса'] ?? '').split('-').reverse().join('.'))

const условия = computed(() =>
  [
    ['Занятость', props.hero?.['занятость']],
    ['График', props.hero?.['график']],
    ['Опыт', props.hero?.['опыт']]
  ].filter(([, значение]) => значение)
)
</script>

<template>
  <div ref="корень" class="st-stack">
    <p v-if="!hero" class="st-note">В базе нет вакансии с текстом и навыками — показать разбор не на чем.</p>

    <template v-else>
      <div class="st-grid st-grid--wide st-grid--stretch">
        <BvCard title="Описание вакансии">
          <template #actions>
            <span class="st-scope">отрывок из {{ num(отрывок['знаков_всего']) }} знаков</span>
          </template>

          <div class="st-vac">
            <span class="st-vac__name">{{ hero['название'] }}</span>
            <span class="st-vac__company">{{ [hero['компания'], hero['регион']].filter(Boolean).join(' · ') }}</span>
          </div>

          <!-- Текст читает программа чтения экрана целиком: отметки — для глаз. -->
          <p class="parse__body">
            <span v-if="!отрывок['с_начала']" class="parse__piece">… </span>
            <template v-for="кусок in куски" :key="кусок.от">
              <mark
                v-if="кусок.навык"
                class="st-hit"
                :class="{ 'is-on': кусок.до <= дочитано }"
                :title="кусок.как === 'форма слова' ? `${кусок.текст} → ${кусок.навык}` : кусок.навык"
              >{{ кусок.текст }}</mark>
              <span v-else class="parse__piece" :class="{ 'is-read': кусок.от < дочитано }">{{ кусок.текст }}</span>
            </template>
            <span v-if="!отрывок['до_конца']" class="parse__piece"> …</span>
          </p>

          <BvProgress :value="дочитано" :max="текст.length || 1" :current="ход.подпись" :note="ход.итог" />
        </BvCard>

        <BvCard title="Навыки">
          <template #actions>
            <span class="st-scope">{{ навыки.length }} всего</span>
          </template>

          <section class="parse__group" aria-live="polite">
            <h4 class="label">Прочитаны в отрывке</h4>
            <ul class="parse__chips">
              <li
                v-for="навык in изТекста"
                :key="навык['название']"
                class="parse__chip st-dim"
                :class="{ 'is-on': найденВТексте.has(навык['название']) }"
              >
                <BvChip>{{ навык['название'] }}</BvChip>
                <span v-if="написано(навык)" class="parse__as">в тексте «{{ написано(навык) }}»</span>
              </li>
            </ul>
          </section>

          <section v-if="остальные.length" class="parse__group st-in" :class="{ 'is-on': шаг >= 2 }">
            <h4 class="label">Найдены не в этом отрывке</h4>
            <ul class="parse__chips">
              <li v-for="навык in остальные" :key="навык['название']" class="parse__chip">
                <BvChip>{{ навык['название'] }}</BvChip>
                <span class="parse__as">{{ ОТКУДА[навык['откуда']] ?? навык['откуда'] }}</span>
              </li>
            </ul>
          </section>
        </BvCard>
      </div>

      <div class="st-grid st-grid--wide st-grid--stretch">
        <BvCard title="Зарплата" class="st-in" :class="{ 'is-on': шаг >= 3 }">
          <template v-if="вВалюте" #actions>
            <span class="st-scope">
              {{ salaryPeriod(зарплата['период']) ?? 'за месяц' }}<template v-if="зарплата['до_налога'] !== null">
                · {{ зарплата['до_налога'] ? 'до вычета налога' : 'на руки' }}</template>
            </span>
          </template>

          <p v-if="!вВалюте" class="st-note">В вакансии не указана — в зарплатные числа она не войдёт.</p>
          <template v-else>
            <!-- Исходная сумма главная, рублёвая — со знаком ≈: так же, как в таблице вакансий. -->
            <div class="parse__salary">
              <span class="st-figure">{{ вВалюте }}</span>
              <span v-if="переводится" class="parse__rub">≈ {{ вРублях }}</span>
            </div>
            <p v-if="переводится" class="st-note">
              Курс ЦБ на <span class="mono-num">{{ датаКурса }}</span> — {{ курс }} ₽ за {{ знак(зарплата['валюта']) }}.
              В сравнениях участвует рублёвая сумма, в списке видна исходная: отклик идёт в валюте вакансии.
            </p>
          </template>
        </BvCard>

        <BvCard title="Условия" class="st-in" :class="{ 'is-on': шаг >= 4 }">
          <dl v-if="условия.length" class="parse__terms">
            <template v-for="[имя, значение] in условия" :key="имя">
              <dt class="label">{{ имя }}</dt>
              <dd>{{ значение }}</dd>
            </template>
          </dl>
          <p v-else class="st-note">Источник условий не передал.</p>
        </BvCard>
      </div>
    </template>
  </div>
</template>

<style scoped>
.parse__body {
  max-width: none;
  overflow-wrap: anywhere;
}

/* Непрочитанное бледнее прочитанного: чтение видно как волна по тексту. */
.parse__piece {
  color: var(--c-text-quiet);
  transition: color var(--dur-panel) var(--ease-standard);
}

.parse__piece.is-read { color: var(--c-text-secondary); }

/* Навык, до которого чтение не дошло, бледен вместе с остальным текстом. */
mark.st-hit:not(.is-on) { color: var(--c-text-quiet); }

.parse__group {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.parse__group h4 { margin: 0; }

.parse__chips {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

/* Место под навык занято заранее: список не прыгает, когда он найден. */
.parse__chip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-1) var(--s-2);
  min-width: 0;
}

.parse__as {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.parse__salary {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.parse__rub {
  font-size: var(--t-body-size);
  color: var(--c-text-muted);
  font-variant-numeric: tabular-nums;
}

.parse__terms {
  margin: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: baseline;
  gap: var(--s-2) var(--s-5);
}

.parse__terms dd {
  margin: 0;
  font-size: var(--t-ui-size);
  color: var(--c-text);
  overflow-wrap: anywhere;
}

@media (prefers-reduced-motion: reduce) {
  .parse__piece { transition: none; }
}
</style>
