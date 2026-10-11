<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import BvChip from '@/components/ui/BvChip.vue'
import StoryNumber from '@/components/domain/story/StoryNumber.vue'
import { useScene } from '@/composables/useScene'
import { moneyExact, num, salaryPeriod } from '@/utils/format'

// Разбор: что система читает из текста вакансии.
//
// По настоящему описанию идёт чтение: прочитанное темнеет, найденные
// навыки отмечаются маркером там, где они написаны, и сразу встают в
// список справа. Места подсветки приходят с сервера и найдены тем же
// способом, что при разборе, — сцена показывает поиск, а не рисует его.
//
// После текста — то, что берётся не из него: навыки, которые назвал
// работодатель, зарплата и условия.
const props = defineProps({
  // story['герой'] из /api/system/story.
  hero: { type: Object, default: null }
})

const ШАГОВ = 4 // чтение, навыки работодателя, зарплата, условия

const отрывок = computed(() => props.hero?.['отрывок'] ?? null)
const текст = computed(() => отрывок.value?.['текст'] ?? '')

// Чтение идёт со скоростью, при которой за ним успеваешь следить: около
// семидесяти знаков в секунду, но не дольше восьми секунд на отрывок.
const времяЧтения = computed(() => Math.min(8000, Math.max(2500, текст.value.length * 14)))

const сцена = useScene(ШАГОВ, {
  пауза: (номер) => (номер === 1 ? времяЧтения.value + 300 : 1100),
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
  } else if (номер >= 1) {
    // Сцену показали сразу итогом или перескочили шаг — текст дочитан.
    if (!идёт.value || номер > 1) {
      cancelAnimationFrame(кадр)
      дочитано.value = текст.value.length
    }
  }
})

onBeforeUnmount(() => cancelAnimationFrame(кадр))

// Текст кусками: обычные куски по несколько слов и куски-навыки. Мелкая
// нарезка нужна, чтобы прочитанное темнело ровно, а не абзацами.
const куски = computed(() => {
  const итог = []
  const обычный = (от, до) => {
    const часть = текст.value.slice(от, до)
    let позиция = от
    for (const слова of часть.match(/\S+\s*(?:\S+\s*){0,3}|\s+/g) ?? []) {
      итог.push({ от: позиция, текст: слова })
      позиция += слова.length
    }
  }
  let позиция = 0
  for (const место of отрывок.value?.['навыки'] ?? []) {
    if (место['от'] > позиция) обычный(позиция, место['от'])
    итог.push({
      от: место['от'], текст: текст.value.slice(место['от'], место['до']),
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

const зарплата = computed(() => props.hero?.['зарплата'] ?? null)
const вВалюте = computed(() => {
  const з = зарплата.value
  if (!з || (з['от'] == null && з['до'] == null)) return ''
  const части = [з['от'], з['до']].filter((сумма) => сумма != null).map((сумма) => num(Math.round(сумма)))
  const знак = moneyExact(0, з['валюта'])?.replace(/^0\s*/, '') ?? з['валюта']
  return `${з['от'] != null && з['до'] == null ? 'от ' : ''}${части.join(' – ')} ${знак}`
})
const переводится = computed(() => Boolean(зарплата.value?.['курс'] && зарплата.value?.['от_руб']))
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
  <div ref="корень" class="parse">
    <p v-if="!hero" class="parse__note">В базе нет вакансии с текстом и навыками — показать разбор не на чем.</p>

    <template v-else>
      <div class="parse__main">
        <figure class="parse__text">
          <figcaption class="parse__caption">
            <span class="parse__name">{{ hero['название'] }}</span>
            <span class="parse__where">{{ [hero['компания'], hero['регион']].filter(Boolean).join(' · ') }}</span>
          </figcaption>
          <!-- Текст читает программа чтения экрана целиком: подсветка — для глаз. -->
          <p class="parse__body">
            <span v-if="!отрывок['с_начала']" class="parse__cut">… </span>
            <template v-for="кусок in куски" :key="кусок.от">
              <mark
                v-if="кусок.навык"
                class="parse__skill"
                :class="{ 'is-found': кусок.от + кусок.текст.length <= дочитано }"
                :title="кусок.как === 'форма слова' ? `${кусок.текст} → ${кусок.навык}` : кусок.навык"
              >{{ кусок.текст }}</mark>
              <span v-else class="parse__piece" :class="{ 'is-read': кусок.от < дочитано }">{{ кусок.текст }}</span>
            </template>
            <span v-if="!отрывок['до_конца']" class="parse__cut"> …</span>
          </p>
          <!-- Сколько прочитано — полосой под текстом. -->
          <span class="parse__progress" aria-hidden="true">
            <span class="parse__progress-bar" :style="{ width: `${текст.length ? (дочитано / текст.length) * 100 : 0}%` }"></span>
          </span>
        </figure>

        <div class="parse__found" aria-live="polite">
          <section class="parse__group">
            <h3 class="parse__group-title">
              Прочитано в тексте
              <span class="parse__count">{{ найденВТексте.size }} из {{ изТекста.length }}</span>
            </h3>
            <ul class="parse__chips">
              <li
                v-for="навык in изТекста"
                :key="навык['название']"
                class="parse__chip"
                :class="{ 'is-shown': найденВТексте.has(навык['название']) }"
              >
                <BvChip>{{ навык['название'] }}</BvChip>
                <span v-if="написано(навык)" class="parse__as">написано «{{ написано(навык) }}»</span>
              </li>
            </ul>
          </section>

          <section v-if="остальные.length" class="parse__group parse__reveal" :class="{ 'is-shown': шаг >= 2 }">
            <h3 class="parse__group-title">Найдено не в этом отрывке</h3>
            <ul class="parse__chips">
              <li v-for="навык in остальные" :key="навык['название']" class="parse__chip is-shown">
                <BvChip>{{ навык['название'] }}</BvChip>
                <span class="parse__as">{{ ОТКУДА[навык['откуда']] ?? навык['откуда'] }}</span>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <div class="parse__facts">
        <section class="parse__fact parse__reveal" :class="{ 'is-shown': шаг >= 3 }">
          <h3 class="parse__group-title">Зарплата</h3>
          <p v-if="!вВалюте" class="parse__note">В вакансии не указана — в зарплатные числа она не войдёт.</p>
          <p v-else-if="переводится" class="parse__formula">
            <span class="parse__sum">{{ вВалюте }}</span>
            <span class="parse__op">× {{ курс }}</span>
            <span class="parse__op">=</span>
            <span class="parse__sum parse__sum--result">
              ≈ <StoryNumber :value="зарплата['от_руб']" :active="шаг >= 3" />
              <template v-if="зарплата['до_руб']"> – <StoryNumber :value="зарплата['до_руб']" :active="шаг >= 3" /></template> ₽
            </span>
          </p>
          <p v-else class="parse__formula"><span class="parse__sum parse__sum--result">{{ вВалюте }}</span></p>
          <p v-if="вВалюте" class="parse__note">
            <template v-if="переводится">Курс ЦБ на {{ датаКурса }}: в сравнениях участвует рублёвая сумма, в списке видна исходная. </template>
            {{ salaryPeriod(зарплата['период']) ? `Оплата ${salaryPeriod(зарплата['период'])}.` : 'Оплата за месяц.' }}
            <template v-if="зарплата['до_налога'] !== null">
              {{ зарплата['до_налога'] ? 'Сумма до вычета налога.' : 'Сумма на руки.' }}
            </template>
          </p>
        </section>

        <section class="parse__fact parse__reveal" :class="{ 'is-shown': шаг >= 4 }">
          <h3 class="parse__group-title">Условия</h3>
          <dl v-if="условия.length" class="parse__terms">
            <template v-for="[имя, значение] in условия" :key="имя">
              <dt>{{ имя }}</dt>
              <dd>{{ значение }}</dd>
            </template>
          </dl>
          <p v-else class="parse__note">Источник условий не передал.</p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.parse {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.parse__main {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: var(--s-8);
  align-items: start;
}

.parse__text {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
  padding: var(--s-5);
  border-radius: var(--r-md);
  background: var(--c-surface-sunken);
}

.parse__caption {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.parse__name {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
  overflow-wrap: anywhere;
}

.parse__where,
.parse__note,
.parse__as,
.parse__count {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

.parse__body {
  font-size: var(--t-body-size);
  line-height: 26px;
  max-width: none;
  overflow-wrap: anywhere;
}

/* Непрочитанное бледнее прочитанного: чтение видно как волна по тексту. */
.parse__piece,
.parse__cut { color: var(--c-text-quiet); }
.parse__piece { transition: color 260ms var(--ease-standard); }
.parse__piece.is-read { color: var(--c-text-secondary); }

/* Найденный навык — маркером по слову: единственный жёлтый на экране
   значит «это слово система нашла в тексте». Заливка проходит по слову
   слева направо, как рука с маркером. */
.parse__skill {
  color: var(--c-text-quiet);
  background-color: transparent;
  background-image: linear-gradient(var(--c-marker-subtle), var(--c-marker-subtle));
  background-repeat: no-repeat;
  background-size: 0% 100%;
  border-radius: 3px;
  padding: 1px 2px;
  margin: 0 -2px;
  transition: background-size 320ms var(--ease-enter), color 200ms var(--ease-standard);
}

.parse__skill.is-found {
  color: var(--c-text);
  background-size: 100% 100%;
}

.parse__progress {
  height: 2px;
  border-radius: var(--r-pill);
  background: var(--c-border);
  overflow: hidden;
}

.parse__progress-bar {
  display: block;
  height: 100%;
  background: var(--c-text);
}

.parse__found {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  min-width: 0;
}

.parse__group,
.parse__fact {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.parse__group-title {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  font-size: var(--t-caption-size);
  font-weight: var(--w-medium);
  color: var(--c-text-secondary);
}

.parse__count {
  font-weight: var(--w-regular);
  font-variant-numeric: tabular-nums;
}

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
  gap: var(--s-2);
  min-width: 0;
  opacity: 0.18;
  transform: translateX(-6px);
  transition: opacity var(--dur-panel) var(--ease-enter), transform var(--dur-panel) var(--ease-enter);
}

.parse__chip.is-shown { opacity: 1; transform: none; }

.parse__reveal {
  opacity: 0;
  transform: translateY(8px);
  transition: opacity var(--dur-enter) var(--ease-enter), transform var(--dur-enter) var(--ease-enter);
}

.parse__reveal.is-shown { opacity: 1; transform: none; }

.parse__facts {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: var(--s-8);
  padding-top: var(--s-5);
  box-shadow: inset 0 1px 0 var(--c-border);
}

.parse__formula {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-2) var(--s-3);
  max-width: none;
  font-variant-numeric: tabular-nums;
}

.parse__sum {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  color: var(--c-text-secondary);
  white-space: nowrap;
}

.parse__sum--result {
  font-weight: var(--w-strong);
  color: var(--c-text);
}

.parse__op {
  font-family: var(--font-mono);
  font-size: var(--t-ui-size);
  color: var(--c-text-muted);
  white-space: nowrap;
}

.parse__terms {
  margin: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--s-1) var(--s-4);
  font-size: var(--t-ui-size);
}

.parse__terms dt { color: var(--c-text-muted); }
.parse__terms dd { margin: 0; color: var(--c-text); overflow-wrap: anywhere; }
.parse__note { max-width: 70ch; }

@media (max-width: 1023px) {
  .parse__main,
  .parse__facts { grid-template-columns: minmax(0, 1fr); gap: var(--s-5); }
  .parse__chips { flex-direction: row; flex-wrap: wrap; gap: var(--s-2) var(--s-4); }
}

@media (max-width: 767px) {
  .parse__text { padding: var(--s-4); }
  .parse__sum { font-size: var(--t-body-size); }
}

@media (prefers-reduced-motion: reduce) {
  .parse__piece,
  .parse__skill,
  .parse__chip,
  .parse__reveal { transition: none; }
}
</style>
