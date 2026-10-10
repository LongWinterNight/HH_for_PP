<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BvButton from '@/components/ui/BvButton.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvField from '@/components/ui/BvField.vue'
import BvModal from '@/components/ui/BvModal.vue'
import BvProgress from '@/components/ui/BvProgress.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import { collection, settings } from '@/api/endpoints'
import { useCollectionStatus } from '@/composables/useCollectionStatus'
import { num, vacancies as vacanciesCount } from '@/utils/format'

// Первый запуск: три шага, около двух минут.
//
// Устройство важнее последовательности экранов: вместо трёх страниц
// объяснений — один рабочий шаг, который сразу собирает данные, и два,
// которые показывают результат. Пользователь выходит отсюда не с
// прочитанной инструкцией, а с наполненной базой.
//
// Пропуск не спрятан и не наказан: он ведёт на обычное пустое
// состояние с той же кнопкой сбора.
const props = defineProps({
  open: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'done'])

const router = useRouter()
const status = useCollectionStatus()

const step = ref(1)
const keywords = ref([])
const draft = ref('')
const email = ref('')
const emailTouched = ref(false)
const startError = ref('')
// Запуск и остановка идут через сеть, и обе кнопки без признака
// работы выглядят нажатыми впустую.
const starting = ref(false)
const stopping = ref(false)

// Быстрый выбор: готовые запросы одним нажатием. Список короткий и
// намеренно разнородный — он показывает, что запрос это профессия,
// а не набор фильтров.
const QUICK = [
  'HR-менеджер',
  'Рекрутер',
  'Аналитик данных',
  'Python-разработчик',
  'Менеджер по продажам',
  'Бухгалтер'
]

onMounted(async () => {
  const saved = await settings.email().catch(() => null)
  email.value = saved?.email || ''
})

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    step.value = 1
    startError.value = ''
  }
})

const isDuplicate = computed(() => keywords.value.includes(draft.value.trim()))

// Оценка объёма и времени пересчитывается при каждом изменении набора —
// до запуска, а не по его ходу: цена действия должна быть известна
// заранее.
const estimate = computed(() => {
  const count = keywords.value.length
  if (!count) return 'Добавьте хотя бы один запрос'
  const vacancies = count * 100
  const seconds = Math.max(15, count * 17)
  return `до ${num(vacancies)} вакансий · ${count} ${count === 1 ? 'запрос' : 'запроса и более'} · примерно ${seconds} сек`
})

const canStart = computed(() => keywords.value.length > 0 && Boolean(email.value.trim()))

const state = computed(() => status.state.value ?? {})

// Шаг 2 не ждёт вхолостую: пока идёт сбор, видно текущий запрос,
// собранное число и остаток.
const collected = computed(() => state.value.vacancies_collected || 0)

watch(() => status.isRunning.value, (running, was) => {
  if (was && !running) step.value = 3
})

function add(word) {
  const value = (word ?? draft.value).trim()
  if (!value || keywords.value.includes(value)) return
  keywords.value.push(value)
  draft.value = ''
}

function remove(word) {
  keywords.value = keywords.value.filter((k) => k !== word)
}

async function start() {
  startError.value = ''
  starting.value = true
  try {
    if (email.value.trim()) await settings.saveEmail({ email: email.value.trim() })

    await collection.start({
      keywords: keywords.value,
      max_pages: 10,
      days_back: 30,
      // Первый сбор идёт в дописывающем режиме: перезаписывать в пустой
      // базе нечего, но привычка не должна закрепляться опасной.
      incremental: true,
      use_cache: true
    })

    step.value = 2
    status.startPolling()
  } catch (e) {
    startError.value = e.message || 'Сбор не запустился.'
  } finally {
    starting.value = false
  }
}

async function stop() {
  stopping.value = true
  try {
    await collection.stop()
    status.fetchStatus()
  } finally {
    stopping.value = false
  }
}

function finish(route) {
  emit('done')
  emit('close')
  if (route) router.push({ name: route })
}
</script>

<template>
  <BvModal
    :open="open"
    :title="step === 1 ? 'С чего начать работу' : step === 2 ? 'Собираем вакансии' : 'Что собралось'"
    :subtitle="`Шаг ${step} из 3`"
    size="lg"
    :close-on-overlay="false"
    @close="$emit('close')"
  >
    <!-- Шаг 1 · единственный, где от пользователя что-то требуется -->
    <template v-if="step === 1">
      <p class="ob__lead">
        Каждый запрос — отдельный поиск на hh.ru. Начните с двух-трёх:
        добавить остальные можно в любой момент.
      </p>

      <section class="ob__block">
        <h3 class="label">Запросы · {{ keywords.length }}</h3>
        <div v-if="keywords.length" class="ob__chips">
          <BvChip
            v-for="word in keywords"
            :key="word"
            variant="filter"
            removable
            :remove-label="`Убрать запрос ${word}`"
            @remove="remove(word)"
          >{{ word }}</BvChip>
        </div>

        <div class="ob__add">
          <BvField
            v-model="draft"
            label="Свой запрос"
            placeholder="впишите свой…"
            :state="isDuplicate && draft ? 'error' : 'default'"
            :message="isDuplicate && draft ? 'Такой запрос уже в списке.' : ''"
            @keydown.enter="add()"
          />
          <BvButton :disabled="!draft.trim() || isDuplicate" @click="add()">Добавить</BvButton>
        </div>
      </section>

      <section class="ob__block">
        <h3 class="label">Быстрый выбор</h3>
        <div class="ob__chips">
          <button
            v-for="word in QUICK"
            :key="word"
            type="button"
            class="ob__quick"
            :disabled="keywords.includes(word)"
            @click="add(word)"
          >+ {{ word }}</button>
        </div>
      </section>

      <BvField
        v-model="email"
        label="Email для hh.ru"
        required
        placeholder="you@company.ru"
        hint="hh.ru требует контакт в заголовке запроса. Без него API отвечает 403 и сбор не начнётся."
        @blur="emailTouched = true"
      />

      <section class="ob__estimate">
        <span class="label">Оценка</span>
        <span class="ob__estimate-value">{{ estimate }}</span>
      </section>

      <p v-if="startError" class="ob__error">{{ startError }}</p>
    </template>

    <!-- Шаг 2 · сбор идёт -->
    <template v-else-if="step === 2">
      <div class="ob__running">
        <span class="ob__count">{{ num(collected) }}</span>
        <span class="ob__count-note">вакансий собрано</span>
      </div>

      <BvProgress
        :value="state.progress || 0"
        :current="state.current_keyword ? `Сейчас: ${state.current_keyword}` : 'Готовим запросы'"
        :note="state.total_pages ? `страница ${state.current_page} из ${state.total_pages}` : 'соединяемся с hh.ru'"
      />

      <ul class="ob__queue">
        <li v-for="word in keywords" :key="word" class="ob__queue-item">
          <BvStatus
            :kind="state.current_keyword === word ? 'run' : 'idle'"
            :label="state.current_keyword === word ? 'Идёт' : 'В очереди'"
          />
          <span class="ob__queue-word">{{ word }}</span>
        </li>
      </ul>

      <p class="ob__lead">
        Диалог можно закрыть — сбор продолжится, а результат появится в разделе
        «Сбор данных» и на дашборде.
      </p>
    </template>

    <!-- Шаг 3 · результат числами, а не поздравлением -->
    <template v-else>
      <div class="ob__done">
        <BvStatus kind="ok" label="Готово" />
        <span class="ob__count">{{ vacanciesCount(collected) }}</span>
      </div>

      <p class="ob__lead">
        Данные уже легли в три раздела. Начните с аналитики: там видно, что рынок
        предлагает по вашим запросам.
      </p>

      <ul class="ob__links">
        <li><button type="button" class="ob__link" @click="finish('analytics')">Аналитика — зарплаты, регионы, опыт</button></li>
        <li><button type="button" class="ob__link" @click="finish('vacancies')">Вакансии — список с фильтрами</button></li>
        <li><button type="button" class="ob__link" @click="finish('reports')">Отчёты — выгрузка в XLSX</button></li>
      </ul>
    </template>

    <template #actions>
      <template v-if="step === 1">
        <BvButton @click="$emit('close')">Пропустить — соберу позже</BvButton>
        <BvButton variant="primary" :loading="starting" :disabled="!canStart" @click="start">Собрать вакансии</BvButton>
      </template>
      <template v-else-if="step === 2">
        <BvButton :loading="stopping" @click="stop">Остановить</BvButton>
        <BvButton variant="primary" @click="$emit('close')">Свернуть — сбор продолжится</BvButton>
      </template>
      <template v-else>
        <BvButton variant="primary" @click="finish('analytics')">Открыть аналитику</BvButton>
      </template>
    </template>
  </BvModal>
</template>

<style scoped>
.ob__lead {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
  max-width: none;
}

.ob__block {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.ob__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.ob__add {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--s-3);
  align-items: start;
}

.ob__add > :deep(.btn) { margin-top: 22px; }

/* Быстрый выбор — не чип данных, а действие: у него граница, а не
   пастельная заливка, иначе он читается как уже добавленный запрос. */
.ob__quick {
  height: var(--h-control-sm);
  padding: 0 var(--s-3);
  border: none;
  border-radius: var(--r-pill);
  background: transparent;
  box-shadow: var(--border-strong);
  color: var(--c-text);
  font-family: var(--font-sans);
  font-size: var(--t-caption-size);
  cursor: pointer;
  transition: var(--t-hover);
}

.ob__quick:hover:not(:disabled) { background: var(--c-surface-hover); }

.ob__quick:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ob__estimate {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--s-3);
  border-radius: var(--r-md);
  background: var(--c-surface-sunken);
}

.ob__estimate-value {
  font-size: var(--t-ui-size);
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
}

.ob__error {
  font-size: var(--t-caption-size);
  color: var(--c-status-err-text);
  max-width: none;
}

.ob__running,
.ob__done {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
}

.ob__count {
  font-size: var(--t-metric-size);
  line-height: var(--t-metric-lh);
  letter-spacing: var(--t-metric-ls);
  font-weight: var(--t-metric-weight);
  color: var(--c-text);
}

.ob__count-note {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.ob__queue {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.ob__queue-item {
  display: flex;
  align-items: center;
  gap: var(--s-3);
}

.ob__queue-word {
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.ob__links {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.ob__link {
  border: none;
  background: transparent;
  padding: 0;
  color: var(--c-accent);
  font-family: var(--font-sans);
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  cursor: pointer;
  text-align: left;
}

.ob__link:hover { color: var(--c-accent-hover); }
</style>
