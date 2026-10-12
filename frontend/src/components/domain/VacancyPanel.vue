<script setup>
import { computed } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvIconButton from '@/components/ui/BvIconButton.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import { dateTime, money, moneyExact, salaryPeriod, timeAgo } from '@/utils/format'

// Панель выбранной вакансии. От 1024px стоит рядом со списком и липнет
// к шапке, ниже — открывается нижним листом: на телефоне боковая панель
// оставляет от таблицы полосу в треть экрана.
//
// Описание вакансии в панели не показывается — только структурные
// поля; текст лежит в базе сжатым и нужен разбору навыков, а читать его
// удобнее на hh.ru. Об этом сказано прямо в панели: иначе пустое место
// читается как ошибка загрузки, а не как решение.
const props = defineProps({
  vacancy: { type: Object, default: null }
})

defineEmits(['close', 'filter-skill', 'expand'])

// Записи, собранные до появления признака активности, считаются
// открытыми: незнание не повод объявлять вакансию закрытой.
const isArchived = computed(
  () => props.vacancy?.is_active === 0 || props.vacancy?.is_active === false
)

const salary = computed(() => {
  const v = props.vacancy
  if (!v || v.salary_from === null || v.salary_from === undefined) return null
  const from = money(v.salary_from, v.salary_currency)
  const период = salaryPeriod(v.salary_mode)
  const хвост = период ? ` ${период}` : ''
  if (!v.salary_to) return `${from}${хвост}`
  return `${from} — ${money(v.salary_to, v.salary_currency)}${хвост}`
})

// Сокращение говорит о порядке величины — этого хватает, чтобы
// сравнить вакансии. Точную цифру человек видит при наведении, не уходя
// на hh.ru.
const salaryExact = computed(() => {
  const v = props.vacancy
  if (!v || v.salary_from === null || v.salary_from === undefined) return null
  const from = moneyExact(v.salary_from, v.salary_currency)
  return v.salary_to ? `${from} — ${moneyExact(v.salary_to, v.salary_currency)}` : from
})

const salaryDoubt = computed(() => props.vacancy?.salary_doubt || null)

const skills = computed(() => {
  const raw = props.vacancy?.all_skills
  if (!raw) return []
  return raw.split(',').map((s) => s.trim()).filter(Boolean)
})

// Навыки, найденные моделью. Лежат отдельно от навыков словаря и в
// частоты не входят: модель не пишет числа в аналитику. Каждый несёт
// цитату — то, из чего он получен: правило то же, что у рублёвого
// эквивалента, который показывается вместе с датой курса.
const отМодели = computed(() => {
  const найденные = props.vacancy?.ai_skills
  if (!Array.isArray(найденные)) return []
  const словарные = new Set(skills.value.map((навык) => навык.toLowerCase()))
  // То, что словарь уже нашёл сам, вторым списком не повторяется.
  return найденные.filter((навык) => навык?.['название'] && !словарные.has(навык['название'].toLowerCase()))
})

const details = computed(() => {
  const v = props.vacancy
  if (!v) return []
  return [
    { k: 'Опыт', v: v.experience || 'не указан' },
    { k: 'Занятость', v: v.employment || 'не указана' },
    { k: 'График', v: v.schedule || 'не указан' },
    { k: 'Регион', v: v.area || 'не указан' },
    { k: 'Опубликована', v: v.published_at ? `${dateTime(v.published_at)}, ${timeAgo(v.published_at)}` : 'дата неизвестна' }
  ]
})
</script>

<template>
  <aside v-if="vacancy" class="panel card" aria-label="Выбранная вакансия">
    <header class="panel__head">
      <div class="panel__titles">
        <h2 class="panel__name">{{ vacancy.vacancy_name }}</h2>
        <span class="panel__company">
          {{ vacancy.employer_name }}
          <!-- Открытая карточка обязана сказать, что вакансии больше
               нет: иначе человек пойдёт откликаться на закрытую. -->
          <BvStatus v-if="isArchived" kind="stop" label="Снята" />
        </span>
      </div>
      <BvIconButton label="Закрыть панель" @click="$emit('close')">✕</BvIconButton>
    </header>

    <div class="panel__salary">
      <span v-if="salary" class="panel__salary-value" :title="salaryExact">{{ salary }}</span>
      <span v-else class="panel__salary-empty">Зарплата не указана</span>
      <!-- В панели есть место на целую фразу, поэтому здесь не знак, а
           объяснение: почему числу не верим и что из-за этого меняется.
           Обычное примечание о налогах при этом не теряется — оно
           остаётся верным и для сомнительного числа. -->
      <span v-if="salaryDoubt" class="panel__salary-note panel__salary-note--doubt">
        Числу нельзя верить: {{ salaryDoubt }}. Вакансия остаётся в списке, но в средние и медианы не берётся.
      </span>
      <span class="panel__salary-note">hh.ru не уточняет, указана сумма до вычета налогов или после</span>
    </div>

    <dl class="panel__details">
      <div v-for="d in details" :key="d.k" class="panel__row">
        <dt class="label">{{ d.k }}</dt>
        <dd class="panel__value">{{ d.v }}</dd>
      </div>
    </dl>

    <section v-if="skills.length" class="panel__skills">
      <h3 class="label">Навыки · {{ skills.length }}</h3>
      <div class="panel__chips">
        <button
          v-for="skill in skills"
          :key="skill"
          type="button"
          class="panel__skill"
          @click="$emit('filter-skill', skill)"
        >
          <BvChip>{{ skill }}</BvChip>
        </button>
      </div>
      <p class="panel__hint">Нажатие на навык добавляет его в фильтр списка.</p>
    </section>

    <section v-if="отМодели.length" class="panel__skills">
      <h3 class="label">Найдено моделью · {{ отМодели.length }}</h3>
      <div class="panel__chips">
        <!-- Без пастели: пастель — категория навыка словаря. Навык модели
             в словарь ещё не принят, и чип это показывает. -->
        <BvChip
          v-for="навык in отМодели"
          :key="навык['название']"
          variant="count"
          :title="`В тексте: «${навык['как_в_тексте']}»`"
        >{{ навык['название'] }}</BvChip>
      </div>
      <p class="panel__hint">
        Эти навыки прочитала в описании модель. В статистику они не входят, пока не попадут в словарь;
        при наведении видно, из каких слов вакансии навык получен.
      </p>
    </section>

    <BvButton size="md" @click="$emit('expand')">Открыть карточку целиком</BvButton>

    <footer class="panel__foot">
      <a class="panel__link" :href="vacancy.vacancy_url" target="_blank" rel="noopener">Открыть на hh.ru ↗</a>
      <span class="mono-num">ID {{ vacancy.vacancy_id }}</span>
    </footer>

    <p class="panel__source">
      Данные из публичного API hh.ru. Здесь показаны структурные поля; полный текст
      описания — на hh.ru.
    </p>
  </aside>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
}

.panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-3);
}

.panel__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.panel__name {
  font-size: var(--t-h3-size);
  line-height: var(--t-h3-lh);
  letter-spacing: var(--t-h3-ls);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.panel__company {
  font-size: var(--t-ui-size);
  color: var(--c-text-secondary);
}

.panel__salary {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.panel__salary-value {
  font-size: var(--t-h2-size);
  line-height: var(--t-h2-lh);
  letter-spacing: var(--t-h2-ls);
  font-weight: var(--w-strong);
  color: var(--c-text);
  white-space: nowrap;
}

.panel__salary-empty {
  font-size: var(--t-h3-size);
  color: var(--c-text-quiet);
}

.panel__salary-note {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

/* Тот же тон, которым система говорит об оговорках к числам — им же
   набраны строки «без указанной зарплаты» в отчёте. Цвет здесь не
   единственный носитель смысла: причина написана словами. */
.panel__salary-note--doubt {
  color: var(--c-status-err-text);
}

.panel__details {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.panel__row {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: var(--s-3);
  align-items: baseline;
}

.panel__value {
  margin: 0;
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.panel__skills {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.panel__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

/* Чип-навык внутри панели — кнопка фильтра, поэтому у него есть фокус
   и он объявляется программам чтения как действие. */
.panel__skill {
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: var(--r-xs);
}

.panel__skill:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.panel__hint,
.panel__source {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.panel__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding-top: var(--s-3);
  box-shadow: inset 0 1px 0 var(--c-border);
}

.panel__link {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
}
</style>
