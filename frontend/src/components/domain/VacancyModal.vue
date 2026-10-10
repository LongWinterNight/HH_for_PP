<script setup>
import { computed } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvModal from '@/components/ui/BvModal.vue'
import { dateTime, money, moneyExact, salaryPeriod, timeAgo } from '@/utils/format'

// Карточка вакансии целиком. Боковая панель показывает главное в 380
// пикселях; здесь помещается всё — три группы навыков, все поля и
// служебные данные.
//
// На телефоне модалка занимает экран полностью: карточка данных,
// обрезанная по краям на 390px, не читается.
const props = defineProps({
  open: { type: Boolean, default: false },
  vacancy: { type: Object, default: null }
})

defineEmits(['close', 'filter-skill'])

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

const salary = computed(() => {
  const v = props.vacancy
  if (!v || v.salary_from === null || v.salary_from === undefined) return null
  const from = money(v.salary_from, v.salary_currency)
  const период = salaryPeriod(v.salary_mode)
  const хвост = период ? ` ${период}` : ''
  if (!v.salary_to) return `${from}${хвост}`
  return `${from} — ${money(v.salary_to, v.salary_currency)}${хвост}`
})

function split(raw) {
  if (!raw) return []
  return raw.split(',').map((s) => s.trim()).filter(Boolean)
}

// Навыки разделены на три группы: профессиональные, личные и
// инструменты. Одним списком из тридцати позиций они не читаются.
const groups = computed(() => {
  const v = props.vacancy
  if (!v) return []
  return [
    { title: 'Профессиональные', items: split(v.hard_skills) },
    { title: 'Личные качества', items: split(v.soft_skills) },
    { title: 'Инструменты', items: split(v.tools) }
  ].filter((g) => g.items.length)
})

const facts = computed(() => {
  const v = props.vacancy
  if (!v) return []
  return [
    { k: 'Компания', v: v.employer_name || 'не указана' },
    { k: 'Регион', v: v.area || 'не указан' },
    { k: 'Опыт', v: v.experience || 'не указан' },
    { k: 'Занятость', v: v.employment || 'не указана' },
    { k: 'График', v: v.schedule || 'не указан' },
    { k: 'Опубликована', v: v.published_at ? `${dateTime(v.published_at)}, ${timeAgo(v.published_at)}` : 'дата неизвестна' }
  ]
})

function openOnHh() {
  window.open(props.vacancy.vacancy_url, '_blank', 'noopener')
}
</script>

<template>
  <BvModal
    :open="open && Boolean(vacancy)"
    :title="vacancy?.vacancy_name || ''"
    :subtitle="vacancy?.employer_name || ''"
    size="lg"
    @close="$emit('close')"
  >
    <div v-if="vacancy" class="vm">
      <div class="vm__salary">
        <span v-if="salary" class="vm__salary-value" :title="salaryExact">{{ salary }}</span>
        <span v-else class="vm__salary-empty">Зарплата не указана</span>
        <!-- Оговорка стоит перед общим примечанием: она относится к
             самому числу, а не к тому, как его понимать. -->
        <span v-if="salaryDoubt" class="vm__salary-note vm__salary-note--doubt">
          Числу нельзя верить: {{ salaryDoubt }}. Вакансия остаётся в списке, но в средние и медианы не берётся.
        </span>
        <span class="vm__salary-note">
          hh.ru не уточняет, указана сумма до вычета налогов или после
        </span>
      </div>

      <dl class="vm__facts">
        <div v-for="f in facts" :key="f.k" class="vm__fact">
          <dt class="label">{{ f.k }}</dt>
          <dd class="vm__fact-value">{{ f.v }}</dd>
        </div>
      </dl>

      <section v-for="group in groups" :key="group.title" class="vm__group">
        <h3 class="label">{{ group.title }} · {{ group.items.length }}</h3>
        <div class="vm__chips">
          <button
            v-for="skill in group.items"
            :key="skill"
            type="button"
            class="vm__skill"
            @click="$emit('filter-skill', skill)"
          >
            <BvChip>{{ skill }}</BvChip>
          </button>
        </div>
      </section>

      <p class="vm__source">
        Данные из публичного API hh.ru. Здесь показаны структурные поля; полный
        текст описания — на hh.ru. Идентификатор в базе: <span class="mono-num">{{ vacancy.vacancy_id }}</span>.
      </p>
    </div>

    <template #actions>
      <BvButton @click="$emit('close')">Закрыть</BvButton>
      <BvButton variant="primary" @click="openOnHh">Открыть на hh.ru ↗</BvButton>
    </template>
  </BvModal>
</template>

<style scoped>
.vm {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.vm__salary {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.vm__salary-value {
  font-size: var(--t-metric-size);
  line-height: var(--t-metric-lh);
  letter-spacing: var(--t-metric-ls);
  font-weight: var(--t-metric-weight);
  color: var(--c-text);
  white-space: nowrap;
}

.vm__salary-empty {
  font-size: var(--t-h2-size);
  color: var(--c-text-quiet);
}

.vm__salary-note--doubt {
  color: var(--c-status-err-text);
}

.vm__salary-note {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.vm__facts {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
  gap: var(--s-3) var(--s-6);
}

.vm__fact {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.vm__fact-value {
  margin: 0;
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.vm__group {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.vm__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

/* Чип-навык здесь — кнопка фильтра: нажатие переносит навык в список. */
.vm__skill {
  padding: 0;
  border: none;
  background: transparent;
  border-radius: var(--r-xs);
  cursor: pointer;
}

.vm__skill:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.vm__source {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}
</style>
