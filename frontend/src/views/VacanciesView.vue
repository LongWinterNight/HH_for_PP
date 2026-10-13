<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BvAutocomplete from '@/components/ui/BvAutocomplete.vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCheckbox from '@/components/ui/BvCheckbox.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvPagination from '@/components/ui/BvPagination.vue'
import BvSelect from '@/components/ui/BvSelect.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import BvPrintMeta from '@/components/ui/BvPrintMeta.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import BvTable from '@/components/ui/BvTable.vue'
import VacancyModal from '@/components/domain/VacancyModal.vue'
import VacancyPanel from '@/components/domain/VacancyPanel.vue'
import { reports, suggest, vacancies as vacanciesApi } from '@/api/endpoints'
import { изАдреса, вАдрес, одинаковые } from '@/app/адрес'
import { ПОЛЯ_ФИЛЬТРОВ, СХЕМА, СХЕМА_СРЕЗА } from '@/views/vacancies-адрес'
import { useApi } from '@/composables/useApi'
import { useHeaderMeta, useScreenMeta } from '@/composables/useHeaderMeta'
import { useToast } from '@/composables/useToast'
import { countOf, dateTime, money, moneyExact, moneyRub, num, plural, salaryPeriod, timeAgo } from '@/utils/format'

// Список вакансий: плотная таблица, панель фильтров, панель выбранной
// вакансии. Двадцать строк подряд должны читаться без утомления, а глаз
// не должен терять строку при движении вправо — отсюда подсветка всей
// строки и липкая первая колонка.

const toast = useToast()

const filters = ref({
  search: '',
  area: '',
  experience: '',
  skill: '',
  currency: '',
  // Откуда вакансия. Пока источник один, выбор не показывается: фильтр
  // без выбора — лишний элемент на экране.
  source: '',
  salary_only: false,
  // Снятые с публикации вакансии по умолчанию не показываются: список
  // описывает текущий рынок, и закрытая вакансия в нём читалась бы как
  // предложение, на которое можно откликнуться. В базе они остаются —
  // по ним считается история.
  include_inactive: false
})

// По умолчанию сортируем по дате: первый вопрос к списку — что нового,
// а не что дороже. Сортировка по зарплате доступна всегда: между
// валютами порядок держит рублёвый эквивалент по курсу ЦБ, и требовать
// сначала выбрать валюту больше незачем.
const sort = ref('date_desc')
// «По соответствию» есть только при поиске: без запроса соответствовать
// нечему, и пункт, который ничего не делает, в списке не нужен.
const sortOptions = computed(() => [
  ...(filters.value.search ? [{ value: 'relevance', label: 'По соответствию' }] : []),
  { value: 'date_desc', label: 'Сначала новые' },
  { value: 'salary_desc', label: 'Зарплата ↓' },
  { value: 'salary_asc', label: 'Зарплата ↑' },
  { value: 'none', label: 'Без сортировки' }
])

const currencyOptions = computed(() => {
  const raw = состояниеБазы.value?.currencies ?? {}
  const list = Object.entries(raw)
    .sort((a, b) => b[1] - a[1])
    .map(([code, count]) => ({ value: code, label: `${code} · ${num(count)}` }))
  return [{ value: '', label: 'Все валюты' }, ...list]
})

// Значения опыта приходят от hh.ru в готовом виде — свои формулировки
// придумывать нельзя, иначе фильтр перестанет совпадать с данными.
const experienceOptions = [
  { value: '', label: 'Любой' },
  { value: 'Нет опыта', label: 'Нет опыта' },
  { value: 'От 1 года до 3 лет', label: 'От 1 года до 3 лет' },
  { value: 'От 3 до 6 лет', label: 'От 3 до 6 лет' },
  { value: 'Более 6 лет', label: 'Более 6 лет' }
]

const page = ref(1)
const perPage = ref(20)

// Что поиск сделал с запросом: исправил опечатку, не нашёл точных
// совпадений, искал ли по смыслу. Молча подменять запрос нельзя —
// человек должен видеть, что искали не совсем то, что он набрал.
const оПоиске = computed(() => list.data.value?.['поиск'] ?? {})
const пояснениеПоиска = computed(() => {
  if (!filters.value.search) return ''
  const части = []
  const замены = Object.entries(оПоиске.value['замены'] ?? {})
  if (замены.length) {
    части.push(`Искали также: ${замены.map(([было, стало]) => `«${было}» → ${стало}`).join('; ')}.`)
  }
  if (оПоиске.value['ослаблен']) {
    части.push('Вакансий со всеми словами запроса нет — показаны те, где есть часть из них.')
  }
  return части.join(' ')
})
const selected = ref(null)
const expanded = ref(false)

const list = useApi((options) => {
  const [sortBy, sortOrder] = ['none', 'relevance'].includes(sort.value)
    ? [sort.value, 'desc']
    : sort.value.split('_')
  return vacanciesApi.list({
    page: page.value,
    per_page: perPage.value,
    search: filters.value.search,
    area: filters.value.area,
    experience: filters.value.experience,
    skill: filters.value.skill,
    currency: filters.value.currency,
    source: filters.value.source,
    salary_only: filters.value.salary_only,
    include_inactive: filters.value.include_inactive,
    sort_by: sortBy,
    sort_order: sortOrder
  }, options)
})

// Счёт по валютам и число вакансий в работе — из сводки шапки. Прежде
// ради них экран запрашивал расчёт дашборда: секунду из двух.
const { состояниеБазы } = useHeaderMeta()

// Источники в базе и их вакансии. Показываем выбор и подпись у строк,
// только когда источников больше одного: до второго источника это
// сведения, которые ничего не различают.
const источники = computed(() => list.data.value?.['источники'] ?? {})
const несколькоИсточников = computed(() => Object.keys(источники.value).length > 1)

const выборИсточника = computed(() => [
  { value: '', label: 'Все источники' },
  ...Object.entries(источники.value).map(([имя, сколько]) => ({
    value: имя,
    label: `${имя} · ${num(сколько)}`,
  })),
])

// Состояние экрана живёт в адресе: выборку можно послать коллеге,
// открыть в новой вкладке и вернуть кнопкой «назад». Состав ссылки
// описан схемой в одном месте — см. vacancies-адрес.js.
const route = useRoute()
const router = useRouter()

// Флаг на время восстановления: пока состояние ставится из адреса,
// обратная запись выключена. Иначе восстановление само порождает
// переход, и «назад» возвращает туда же, откуда пришли.
let восстанавливаем = false

function применитьАдрес() {
  const из = изАдреса(route.query, СХЕМА)
  восстанавливаем = true

  for (const ключ of ПОЛЯ_ФИЛЬТРОВ) filters.value[ключ] = из[ключ]
  sort.value = из.sort
  page.value = из.page
  ожидаемаяВакансия.value = из.id

  // Значения разошлись по реактивным полям — дождаться, пока
  // наблюдатели отработают, и только потом снова включать запись.
  nextTick(() => { восстанавливаем = false })
}

// Какую вакансию просили открыть адресом. Панель откроется, когда
// список приедет: карточка берётся из загруженных строк.
const ожидаемаяВакансия = ref('')

function записатьАдрес({ вИсторию = false } = {}) {
  if (восстанавливаем) return

  const query = вАдрес(
    { ...filters.value, sort: sort.value, page: page.value, id: selected.value?.vacancy_id ?? '' },
    СХЕМА,
  )
  if (одинаковые(query, route.query)) return

  // Правка фильтра заменяет запись в истории, а не добавляет: иначе
  // десять правок подряд означают десять нажатий «назад» по одному
  // чипу. Смена страницы и открытие панели — наоборот, добавляют:
  // «назад» должно возвращать к прошлому виду.
  const переход = { path: route.path, query }
  if (вИсторию) router.push(переход)
  else router.replace(переход)
}

onMounted(async () => {
  применитьАдрес()
  list.load()
})


// Переход «назад» и «вперёд» меняет адрес мимо экрана — состояние
// подтягивается за ним.
watch(() => route.fullPath, () => {
  const из = изАдреса(route.query, СХЕМА)
  const сейчас = { ...filters.value, sort: sort.value, page: page.value, id: selected.value?.vacancy_id ?? '' }
  if (одинаковые(вАдрес(из, СХЕМА), вАдрес(сейчас, СХЕМА))) return
  применитьАдрес()
  list.load()
})

// Смена фильтра возвращает на первую страницу: остаться на восьмой
// странице нового поиска — гарантированно попасть в пустоту.
//
// Кроме восстановления из адреса: там страница пришла вместе с
// фильтрами, и сброс превращал ссылку на вторую страницу в первую.
// Человек начал искать — список встаёт по соответствию запросу: лучшее
// совпадение на пятой странице «сначала новых» не увидит никто. Запрос
// стёрт — порядок возвращается к дате. Выбранную руками сортировку
// (по зарплате) смена запроса не трогает.
watch(() => filters.value.search, (стало, было) => {
  if (восстанавливаем) return
  if (стало && !было && sort.value === 'date_desc') sort.value = 'relevance'
  if (!стало && sort.value === 'relevance') sort.value = 'date_desc'
})

watch([filters, sort, perPage], () => {
  if (восстанавливаем) return
  page.value = 1
  // Панель закрывается вместе со сменой выборки: открытая вакансия
  // принадлежала прошлому фильтру, в новом списке её может не быть — а
  // её id при этом уезжал в ссылку и открывался у получателя поверх
  // чужой выборки.
  selected.value = null
  записатьАдрес()
  list.load()
}, { deep: true })

watch(page, () => {
  if (восстанавливаем) return
  записатьАдрес({ вИсторию: true })
  list.load()
})

watch(selected, () => записатьАдрес({ вИсторию: true }))

// Строка, по которой нажали, остаётся под курсором.
//
// От 1024px панель встаёт рядом со списком и отнимает у него 380px:
// названия переносятся на вторую строку, таблица вырастает, и всё, что
// ниже начала экрана, съезжает. Нажатая строка уезжала на десятки
// пикселей из-под курсора — человек нажимал на одну вакансию, а под
// рукой оказывалась соседняя. При закрытии панели то же в обратную
// сторону.
//
// Положение строки запоминается до перестройки и возвращается после
// неё. Якорь — открываемая вакансия, а при закрытии — та, что была
// открыта: человек смотрит на неё.
function строкаВакансии(vacancy) {
  if (!vacancy) return null
  return document.querySelector(`.vac__row[data-id="${CSS.escape(String(vacancy.vacancy_id))}"]`)
}

watch(selected, (стало, было) => {
  const строка = строкаВакансии(стало || было)
  if (!строка) return
  const до = строка.getBoundingClientRect().top

  nextTick(() => {
    // Строка могла исчезнуть: панель открыли адресом, а список
    // пришёл другой.
    if (!строка.isConnected) return
    const сдвиг = строка.getBoundingClientRect().top - до
    if (сдвиг) window.scrollBy({ top: сдвиг, behavior: 'instant' })
  })
}, { flush: 'pre' })

const items = computed(() => list.data.value?.items ?? [])
const total = computed(() => list.data.value?.total ?? 0)

// Ссылка с открытой панелью: карточка ищется в приехавшем списке.
//
// Вакансии по ссылке может уже не быть — адрес приходит из чужой
// переписки, а база с тех пор пересобрана. Тогда панель просто не
// открывается: список под ней рабочий, и тупика не возникает.
watch(items, () => {
  if (!ожидаемаяВакансия.value) return
  const найдена = items.value.find((v) => String(v.vacancy_id) === String(ожидаемаяВакансия.value))
  ожидаемаяВакансия.value = ''
  if (найдена) selected.value = найдена
})

// Как показывать зарплаты: в валюте вакансии или в рублёвом эквиваленте.
// Это вид, а не фильтр: он ничего не меняет в выборке и не уходит на
// сервер — исходная сумма остаётся в данных и в отклике на вакансию.
const salaryView = ref('currency')
const salaryViews = [
  { value: 'currency', label: 'В валюте' },
  { value: 'rub', label: 'В рублях' }
]

// Дата курса приезжает тем же ответом, что и вакансии.
const rateDate = computed(() => {
  const raw = list.data.value?.rate_date
  if (!raw) return null
  return new Date(raw).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
})

// Подпись показывается, только когда на странице есть что пересчитывать:
// на выборке из одних рублёвых вакансий она объясняла бы то, чего не
// видно.
const hasForeignSalary = computed(() => items.value.some((v) => salaryRubValueOf(v)))

// Порядок строк держит рублёвый эквивалент, только когда валюта не
// выбрана: внутри одной валюты сравниваются исходные суммы. Человек
// должен знать, по какому числу выстроен список, — иначе «Зарплата ↓»
// на смеси валют выглядит как сравнение номиналов.
const порядокПоЭквиваленту = computed(
  () => sort.value.startsWith('salary') && !filters.value.currency
)

// Сколько вакансий в базе всего — чтобы сказать, насколько сужен срез.
// Сколько вакансий в работе — из сводки шапки. Вычисляется, а не
// присваивается: наблюдатель с немедленным запуском, стоявший выше
// этого объявления, обращался к переменной до её появления и ронял экран.
const allTotal = computed(() => состояниеБазы.value?.active ?? null)

// Числа на экране относятся только к выбранным условиям. Пока это не
// сказано, «найдено 51» читается как «в базе 51».
// «Выборка сужена» — только когда её действительно сузили. Флажок
// архива, наоборот, расширяет список: без этой проверки экран сообщал
// бы «8342 из 1411», потому что общее число считается по открытым
// вакансиям.
const isNarrowed = computed(
  () => activeChips.value.length > 0 && allTotal.value !== null && total.value <= allTotal.value
)

// Список вышел за пределы открытых вакансий: показан архив.
const showsArchive = computed(() => filters.value.include_inactive)

// Объём выборки в шапке узкого экрана. Там нет ни заголовка списка, ни
// строки «найдено», пока человек не прокрутит вверх, — а число, на
// которое он смотрит, относится к фильтрам, а не ко всей базе.
useScreenMeta(computed(() => {
  if (!list.data.value) return ''
  return isNarrowed.value ? `${num(total.value)} из ${num(allTotal.value)}` : num(total.value)
}))

const activeChips = computed(() => {
  const chips = []
  if (filters.value.search) chips.push({ key: 'search', label: filters.value.search })
  if (filters.value.area) chips.push({ key: 'area', label: filters.value.area })
  if (filters.value.experience) chips.push({ key: 'experience', label: filters.value.experience })
  if (filters.value.skill) chips.push({ key: 'skill', label: filters.value.skill })
  if (filters.value.currency) chips.push({ key: 'currency', label: filters.value.currency })
  if (filters.value.salary_only) chips.push({ key: 'salary_only', label: 'только с зарплатой' })
  if (filters.value.include_inactive) chips.push({ key: 'include_inactive', label: 'со снятыми с публикации' })
  return chips
})

function clearChip(key) {
  // Булевы фильтры снимаются в false, остальные — в пустую строку.
  filters.value[key] = typeof filters.value[key] === 'boolean' ? false : ''
}

function resetAll() {
  filters.value = {
    search: '',
    area: '',
    experience: '',
    skill: '',
    currency: '',
    salary_only: false,
    include_inactive: false
  }
  sort.value = 'date_desc'
}

// Сколько объявлений у той же вакансии в других городах. Число
// приходит от сервера: на клиенте лежит одна страница списка, и
// посчитать по ней нельзя.
function копийУ(вакансия) {
  return вакансия.копий || 1
}

function городов(сколько) {
  const остаток = сколько % 100
  if (остаток >= 11 && остаток <= 14) return 'городах'
  const последняя = сколько % 10
  if (последняя === 1) return 'городе'
  return 'городах'
}

function подписьКопий(вакансия) {
  return `Та же вакансия размещена в ${копийУ(вакансия)} городах. `
    + 'В медиане зарплаты она считается за одну.'
}

// Вакансия снята с публикации, если источник перестал её отдавать.
// Записи, собранные до появления этого признака, считаются открытыми:
// незнание не повод объявлять их закрытыми.
function isArchived(v) {
  return v.is_active === 0 || v.is_active === false
}

function salaryOf(v) {
  if (v.salary_from === null || v.salary_from === undefined) return null
  return money(v.salary_from, v.salary_currency)
}

// Рублёвый эквивалент показывается только там, где он что-то добавляет:
// у рублёвой зарплаты вторая строка «≈ 120 000 ₽» — это шум, а не помощь.
// Валюты без курса ЦБ эквивалента не получают вовсе, и пустое место
// честнее нуля.
// В рублёвом виде главным становится эквивалент, а исходная сумма
// уходит второй строкой — но не исчезает: правило системы требует, чтобы
// валюта вакансии была на виду всегда.
function salaryMainOf(v) {
  if (salaryView.value === 'rub' && salaryRubValueOf(v)) return moneyRub(v.salary_from_rub)
  return salaryOf(v)
}

function salarySecondOf(v) {
  if (!salaryRubValueOf(v)) return null
  return salaryView.value === 'rub' ? salaryOf(v) : moneyRub(v.salary_from_rub)
}

// Есть ли вообще что показывать вторым числом: у рублёвой вакансии
// «120 000 ₽ / ≈ 120 000 ₽» — шум, а не помощь; у валюты без курса ЦБ
// эквивалента нет вовсе, и пустое место честнее нуля.
function salaryRubValueOf(v) {
  if (v.salary_currency === 'RUB' || v.salary_currency === 'RUR') return null
  return v.salary_from_rub ?? null
}

// «1 000 ₽» и «1 000 ₽ за час» — разные величины. Пока период не был
// виден, честная почасовая ставка выглядела как ошибка в данных, и
// продукт писал под ней «числу нельзя верить».
function periodOf(v) {
  return salaryPeriod(v.salary_mode)
}

// Точная сумма при наведении: сокращение показывает порядок величины,
// но человеку, которому важна цифра, не нужно ради неё уходить на hh.ru.
function salaryTitleOf(v) {
  const точно = moneyExact(v.salary_from, v.salary_currency)
  if (!точно) return null
  const до = v.salary_to ? ` — ${moneyExact(v.salary_to, v.salary_currency)}` : ''
  return `${точно}${до}`
}

// Объяснение пометки словами: знак без причины оставляет человека
// гадать, а причина у нас есть — её посчитали при сохранении.
function doubtHint(v) {
  return `Числу нельзя верить: ${v.salary_doubt}. В средние и медианы не берётся.`
}

function skillsOf(v) {
  const raw = v.all_skills || ''
  const all = raw.split(',').map((s) => s.trim()).filter(Boolean)
  return { shown: all.slice(0, 2), more: Math.max(0, all.length - 2) }
}

async function suggestVacancies(q) {
  const r = await suggest.vacancies({ q })
  return r?.suggestions ?? []
}

async function suggestAreas(q) {
  const r = await suggest.areas({ q })
  return r?.suggestions ?? []
}

async function suggestSkills(q) {
  const r = await suggest.skills({ q })
  return r?.suggestions ?? []
}

function pickSkill(skill) {
  filters.value.skill = skill
}

// Выгрузка идёт по прямой ссылке: файл отдаёт бэкенд, и браузеру
// незачем держать его в памяти вкладки.
// Загрузка идёт через якорь, а не window.open: браузер обрабатывает
// ответ как файл, окно не открывается, и window.open возвращает null —
// на этом интерфейс сообщал об ошибке, хотя файл успешно скачивался.
function собратьОтчёт() {
  // Кнопка ведёт на «Отчёты» со срезом в адресе, а не собирает файл на
  // месте. Причина — не лишний шаг ради шага: на том экране видно, что
  // попадёт в файл, сколько это строк и стоит ли вообще собирать срез
  // из пяти вакансий. Собранный впустую отчёт стоит дороже одного
  // перехода.
  //
  // Заодно у сборки остаётся один путь. Их было два, и второй тихо
  // расходился бы с первым при любой правке параметров.
  router.push({ path: '/reports', query: вАдрес(filters.value, СХЕМА_СРЕЗА) })
}

function downloadXlsx() {
  const link = document.createElement('a')
  link.href = vacanciesApi.exportUrl('xlsx')
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()

  toast.progress('Готовим XLSX', `${countOf(total.value, 'строка', 'строки', 'строк')} — файл скачается сам`)
}
</script>

<template>
  <section class="vac">
    <!-- Колонтитул печати: на бумаге список без условий выборки
         недоказуем — по нему не понять, что именно отобрано. -->
    <BvPrintMeta
      :slice="`${num(total)} вакансий`"
      :filters="activeChips.length ? activeChips.map((c) => c.label).join(', ') : 'без фильтров'"
    />
    <header class="vac__head">
      <div class="vac__titles">
        <h1>Вакансии</h1>
        <p class="vac__meta">
          <template v-if="list.loading.value">Загружаем список…</template>
          <template v-else>
            <!-- Слово склоняется по числу: «1 вакансия», «2 вакансии»,
                 «5 вакансий». Строкой оно стояло в единственной форме и
                 врало на большинстве чисел. Стоит всегда, а не только
                 без фильтров: «Найдено 12» без слова читается как
                 обрывок. -->
            Найдено <b>{{ num(total) }}</b>&nbsp;{{ plural(total, 'вакансия', 'вакансии', 'вакансий') }}<template v-if="allTotal !== null && !activeChips.length"> в базе</template>
          </template>
        </p>
      </div>
      <div class="vac__head-actions">
        <!-- Вид, а не фильтр: выборка не меняется, меняется только то,
             каким числом она показана. Поэтому переключатель стоит в
             шапке рядом с действием, а не в панели фильтров. Показываем
             его, лишь когда в выборке есть что пересчитывать. -->
        <BvSegmented
          v-if="hasForeignSalary"
          v-model="salaryView"
          :options="salaryViews"
          label="Как показывать зарплаты"
          data-print-hide
        />
        <BvButton :disabled="!total" @click="downloadXlsx">
          Скачать XLSX
        </BvButton>
        <BvButton
          variant="primary"
          :disabled="!total"
          @click="собратьОтчёт"
        >
          Собрать отчёт
        </BvButton>
      </div>
    </header>

    <!-- Панель фильтров. Главная кнопка тут не нужна: список обновляется
         сам при изменении условий, и «Применить» была бы лишним шагом
         между намерением и результатом. -->
    <div class="vac__filters card" data-print-hide>
      <div class="vac__filters-row">
        <BvAutocomplete
          v-model="filters.search"
          label="Поиск"
          placeholder="Профессия, навык или задача"
          :suggest="suggestVacancies"
        />
        <BvAutocomplete
          v-model="filters.area"
          label="Регион"
          placeholder="Москва, Санкт-Петербург"
          :suggest="suggestAreas"
        />
        <BvSelect v-model="filters.experience" label="Опыт" :options="experienceOptions" />
        <BvAutocomplete
          v-model="filters.skill"
          label="Навык"
          placeholder="Название навыка"
          :suggest="suggestSkills"
        />
        <BvSelect v-model="filters.currency" label="Валюта" :options="currencyOptions" />
        <!-- Выбор источника появляется со вторым источником: пока сайт
             один, «Все источники» — выбор без выбора. -->
        <BvSelect
          v-if="несколькоИсточников"
          v-model="filters.source"
          label="Источник"
          :options="выборИсточника"
        />
        <BvSelect v-model="sort" label="Сортировка" :options="sortOptions" />
      </div>

      <div class="vac__filters-foot">
        <!-- Переключатели держатся вместе: подвал разнесён по краям, и
             без обёртки второй флажок уехал бы к чипам. -->
        <div class="vac__toggles">
          <BvCheckbox v-model="filters.salary_only" label="Только с указанной зарплатой" />
          <!-- Архив выключен по умолчанию: список отвечает на вопрос «что
               сейчас на рынке», а снятая вакансия — это история. Включённый
               флажок виден и в чипах над таблицей, чтобы числа на экране
               нельзя было принять за текущие. -->
          <BvCheckbox
            v-model="filters.include_inactive"
            label="Показывать снятые с публикации"
          />
        </div>

        <div v-if="activeChips.length" class="vac__chips">
          <BvChip
            v-for="chip in activeChips"
            :key="chip.key"
            variant="filter"
            removable
            :remove-label="`Убрать условие: ${chip.label}`"
            @remove="clearChip(chip.key)"
          >{{ chip.label }}</BvChip>
          <BvButton variant="quiet" size="sm" @click="resetAll">Сбросить всё</BvButton>
        </div>
      </div>
    </div>

    <!-- Единственное место системы, где маркерный жёлтый работает фоном:
         он помечает, что все числа на экране считаны по суженной выборке. -->
    <p v-if="пояснениеПоиска" class="vac__search-note" role="status">{{ пояснениеПоиска }}</p>

    <BvBanner
      v-if="isNarrowed"
      kind="filtered"
      :title="`Выборка сужена: ${num(total)} из ${num(allTotal)} вакансий`"
      :text="`Активны условия: ${activeChips.map((c) => c.label).join(', ')}. Числа на экране относятся только к ним.`"
    >
      <template #actions>
        <BvButton size="md" @click="resetAll">Сбросить</BvButton>
      </template>
    </BvBanner>

    <!-- Архив меняет смысл всех чисел на экране, поэтому сообщение
         живёт здесь, а не только в чипе фильтра. -->
    <BvBanner
      v-if="showsArchive"
      kind="info"
      title="Показаны и снятые с публикации вакансии"
      text="Список описывает не текущий рынок, а всё, что когда-либо попадало в базу. Снятые помечены в строке словом «Снята»."
    >
      <template #actions>
        <BvButton size="md" @click="filters.include_inactive = false">Только открытые</BvButton>
      </template>
    </BvBanner>

    <div class="vac__body" :class="{ 'has-panel': selected }">
      <div class="vac__list">
        <!-- Ошибка называет, что делать, и не прячет уже загруженное. -->
        <div v-if="list.error.value" class="vac__state card">
          <p class="vac__state-title">Список не загружен</p>
          <p class="vac__state-text">{{ list.error.value }}</p>
          <BvButton size="md" :loading="list.loading.value" @click="list.load()">Повторить</BvButton>
        </div>

        <div v-else-if="!list.loading.value && total === 0" class="vac__state card">
          <p class="vac__state-title">Ничего не найдено</p>
          <p class="vac__state-text">
            Под эти условия не подходит ни одна собранная вакансия.
            Снимите часть фильтров или расширьте поиск.
          </p>
          <BvButton size="md" @click="resetAll">Сбросить фильтры</BvButton>
        </div>

        <BvTable v-else label="Список вакансий" sticky-first>
          <thead>
            <tr>
              <th>Вакансия</th>
              <th class="col-num">Зарплата</th>
              <th class="col-area">Регион</th>
              <th class="col-exp">Опыт</th>
              <th class="col-when">Опубликована</th>
              <th class="col-skills">Навыки</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="v in items"
              :key="v.vacancy_id"
              class="vac__row"
              :class="{ 'is-selected': selected && selected.vacancy_id === v.vacancy_id }"
              :data-id="v.vacancy_id"
              tabindex="0"
              @click="selected = v"
              @keydown.enter="selected = v"
            >
              <td class="vac__name">
                <!-- Содержимое лежит в отдельном блоке: раскладку колонок
                     браузер считает по табличным правилам, а ячейка с
                     display: flex из них выпадает. -->
                <div class="vac__name-box">
                <span class="vac__name-text">{{ v.vacancy_name }}</span>
                <span class="vac__company">
                  {{ v.employer_name }}
                  <!-- Пометка стоит в строке, а не только в фильтре:
                       иначе снятая вакансия ничем не отличается от
                       открытой, и разницу видит только тот, кто помнит,
                       что включил флажок. -->
                  <BvStatus v-if="isArchived(v)" kind="stop" label="Снята" />
                  <!-- Одна вакансия, размещённая в нескольких городах,
                       занимает в списке столько же строк. Скрывать их
                       нельзя — человеку, который ищет работу в Самаре,
                       нужна именно его строка, — но без пометки список
                       выглядит как повтор одного и того же по ошибке.
                       В зарплатных числах такая вакансия считается за
                       одну: иначе она весит как тридцать. -->
                  <!-- Откуда вакансия. Подпись нужна только когда
                       источников несколько: иначе она повторяет одно и
                       то же у каждой строки. -->
                  <span v-if="несколькоИсточников && v.source" class="vac__source">{{ v.source }}</span>
                  <!-- Почему вакансия в выдаче. Без подписи найденное
                       «по смыслу» выглядит ошибкой поиска: слов запроса
                       в строке нет, а она стоит третьей. -->
                  <span v-if="v.search_why" class="vac__why">найдено {{ v.search_why }}</span>
                  <span v-if="копийУ(v) > 1" class="vac__copies" :title="подписьКопий(v)">
                    ещё в {{ копийУ(v) - 1 }} {{ городов(копийУ(v) - 1) }}
                  </span>
                </span>
                <!-- Сведения свёрнутых колонок. Когда таблице тесно —
                     открыта панель вакансии или экран узкий, — колонки
                     не прокручиваются вбок, а переезжают сюда. Какие
                     именно показаны, решает ширина таблицы (стили ниже). -->
                <span class="vac__folded">
                  <span v-if="v.area" class="vac__in vac__in--area">{{ v.area }}</span>
                  <span v-if="v.experience" class="vac__in vac__in--exp">{{ v.experience }}</span>
                  <span v-if="v.published_at" class="vac__in vac__in--when" :title="dateTime(v.published_at)">{{ timeAgo(v.published_at) }}</span>
                </span>
                <div v-if="skillsOf(v).shown.length" class="vac__skills vac__in vac__in--skills">
                  <BvChip v-for="s in skillsOf(v).shown" :key="s">{{ s }}</BvChip>
                  <BvChip v-if="skillsOf(v).more" variant="count">+{{ skillsOf(v).more }}</BvChip>
                </div>
                </div>
              </td>
              <td class="col-num" :title="salaryTitleOf(v)">
                <!-- Сомнительной зарплате нельзя верить, но и скрывать
                     вакансию нельзя: запись настоящая, а правило
                     основано на догадке. Поэтому число остаётся на
                     месте, помеченное знаком и объяснением при
                     наведении. Знак, а не только приглушённый цвет:
                     цвет никогда не единственный носитель смысла. -->
                <template v-if="salaryOf(v)">
                  <span v-if="v.salary_doubt" class="vac__doubt" :title="doubtHint(v)">
                    {{ salaryMainOf(v) }}<span class="vac__doubt-mark" aria-hidden="true">?</span>
                  </span>
                  <template v-else>{{ salaryMainOf(v) }}</template>
                  <!-- Период рядом с суммой: «1 000 ₽» и «1 000 ₽ за час»
                       — разные величины. -->
                  <span v-if="periodOf(v)" class="vac__period">{{ periodOf(v) }}</span>
                  <!-- Второе число приглушено, но присутствует всегда:
                       какой бы вид ни выбрали, валюта вакансии остаётся
                       на виду — человек откликается в её валюте. -->
                  <span v-if="salarySecondOf(v)" class="vac__rub">{{ salarySecondOf(v) }}</span>
                </template>
                <span v-else class="vac__empty">не указана</span>
              </td>
              <td class="col-area">{{ v.area }}</td>
              <td class="vac__exp col-exp">{{ v.experience || '—' }}</td>
              <!-- Срок, а не дата: при сортировке «сначала новые» порядок
                   должен читаться в самой строке, а «01.09.2026» через
                   месяц ничего не говорит о свежести. Точная дата — в
                   подсказке и в панели вакансии. -->
              <td class="col-when">
                <span v-if="v.published_at" :title="dateTime(v.published_at)">
                  {{ timeAgo(v.published_at) }}
                </span>
                <span v-else class="vac__empty">дата неизвестна</span>
              </td>
              <td class="col-skills">
                <div class="vac__skills">
                  <BvChip v-for="s in skillsOf(v).shown" :key="s">{{ s }}</BvChip>
                  <BvChip v-if="skillsOf(v).more" variant="count">+{{ skillsOf(v).more }}</BvChip>
                </div>
              </td>
            </tr>
          </tbody>
        </BvTable>

        <!-- Подпись стоит там же, где числа, которые она объясняет:
             «≈ 139 362 ₽» без даты курса ничем не подтверждено. Курс
             берётся на дату сбора, а не на сегодня, — иначе число
             менялось бы каждый день без единой новой вакансии. -->
        <p v-if="rateDate && (hasForeignSalary || порядокПоЭквиваленту)" class="vac__rate-note">
          <template v-if="порядокПоЭквиваленту">
            Порядок — по рублёвому эквиваленту: суммы в разных валютах иначе не сравнить.
            Выберите валюту, чтобы сортировать по исходным суммам.
          </template>
          Рублёвый эквивалент посчитан по официальному курсу ЦБ РФ на {{ rateDate }}.
          Отклик на вакансию идёт в её валюте.
        </p>

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

      <VacancyPanel
        v-if="selected"
        :vacancy="selected"
        class="vac__panel"
        @close="selected = null"
        @filter-skill="pickSkill"
        @expand="expanded = true"
      />
    </div>

    <!-- Карточка целиком: в панели помещается главное, здесь — все
         группы навыков и поля. -->
    <VacancyModal
      :open="expanded"
      :vacancy="selected"
      @close="expanded = false"
      @filter-skill="(skill) => { pickSkill(skill); expanded = false }"
    />
  </section>
</template>

<style scoped>
.vac {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.vac__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.vac__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.vac__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.vac__meta b {
  color: var(--c-text);
  font-weight: var(--w-medium);
  font-variant-numeric: tabular-nums;
}

.vac__filters {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.vac__filters-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(200px, 100%), 1fr));
  gap: var(--s-4);
}

.vac__filters-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
}

.vac__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

/* От 1024px панель вакансии стоит рядом со списком и липнет к шапке.
   Ниже — идёт под списком: боковая колонка на телефоне оставила бы от
   таблицы полосу в треть экрана. */
.vac__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--gap-grid);
  align-items: start;
}

@media (min-width: 1024px) {
  .vac__body.has-panel {
    grid-template-columns: minmax(0, 1fr) 380px;
  }

  .vac__panel {
    position: sticky;
    top: calc(var(--h-header) + var(--s-4));
  }
}

/* Ниже 1024px панель превращается в нижний лист: боковая колонка на
   телефоне оставила бы от таблицы полосу в треть экрана.
   Высота ограничена dvh — в Safari адресная строка сворачивается, и
   лист, заданный в vh, уезжает под неё. Нижний отступ учитывает
   жестовую черту iPhone: без него кнопки под ней недоступны. */
@media (max-width: 1023px) {
  .vac__panel {
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

.vac__list {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
  /* Список меряет свою ширину: по ней таблица решает, какие колонки
     показать. Ширина экрана тут не годится — панель вакансии забирает
     у списка 380 точек на любом экране. */
  container: vaclist / inline-size;
}

/* Таблице тесно — колонки сворачиваются в строку компании, а не уходят
   под прокрутку вбок. Раньше шесть колонок требовали 1052 точки при
   любой ширине, и с открытой панелью «Опубликована» и «Навыки»
   оказывались за краем. Порядок сворачивания — от того, что есть в
   панели и реже нужно при сравнении строк, к тому, что нужно чаще:
   срок, опыт, регион, навыки. */
.vac__folded {
  display: none;
  flex-wrap: wrap;
  gap: 2px var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.vac__in,
.vac__skills.vac__in--skills { display: none; }

/* Точка стоит после сведения, а не перед ним: сворачиваются колонки с
   конца, срок публикации — первым, и он же в строке последний. Видимые
   сведения поэтому всегда идут подряд до конца строки, и точка после
   каждого, кроме последнего, встаёт верно при любом их числе. */
.vac__folded .vac__in:not(:last-child)::after {
  content: '·';
  margin-left: var(--s-2);
  color: var(--c-text-quiet);
}

/* Пороги посчитаны по самым широким строкам базы, а не по удачной
   выборке: название 272, зарплата с эквивалентом до 130, регион 133,
   опыт 157, срок 127, навыки 272. По выборке с короткими навыками всё
   помещалось и при меньшей ширине, а на общем списке прокрутка
   возвращалась. */
@container vaclist (max-width: 1100px) {
  .vac__folded { display: flex; }
  .col-when { display: none; }
  .vac__in--when { display: inline; }
}

@container vaclist (max-width: 970px) {
  .col-exp { display: none; }
  .vac__in--exp { display: inline; }
}

@container vaclist (max-width: 815px) {
  .col-area { display: none; }
  .vac__in--area { display: inline; }
  /* Название с подстрокой переносится, и держать под него 240 точек
     уже незачем. Селектор с тегом — чтобы перекрыть общее правило ниже. */
  td.vac__name { min-width: 200px; }
}

@container vaclist (max-width: 640px) {
  .col-skills { display: none; }

  /* Под названием чипы переносятся: в одну строку они держали бы
     ширину колонки и возвращали прокрутку. */
  .vac__skills.vac__in--skills {
    display: flex;
    flex-wrap: wrap;
    max-width: none;
    margin-top: var(--s-1);
    /* Ширину колонки блок не задаёт: один длинный навык («Работа с
       дебиторской задолженностью») иначе распирал её на 270 точек. Он
       усекается многоточием, как и в колонке навыков. */
    contain: inline-size;
  }

  .vac__in--skills :deep(.chip) { max-width: 100%; }

  td.vac__name { min-width: 0; }
}

.vac__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-3);
  text-align: center;
  padding: var(--s-12) var(--s-6);
}

.vac__state-title {
  font-size: var(--t-h3-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.vac__state-text {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-muted);
}

.vac__row { cursor: pointer; }

.vac__row:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* Выбранная строка помечена подложкой и полосой слева: полоса видна
   и в чёрно-белой печати, и при дальтонизме. */
/* Выделение задаётся на строке, а не на ячейках: фон липкой первой
   колонки наследуется от строки, и правило, заданное на td, до неё
   не доходило — выделение обрывалось на границе первой колонки. */
.vac__row.is-selected { background: var(--c-accent-subtle); }
.vac__row.is-selected :deep(td:first-child) { box-shadow: inset 3px 0 0 var(--c-accent), inset 0 -1px 0 var(--c-border); }

/* Ширину ограничивает содержимое, а не сама ячейка.

   Прежде на этой ячейке стоял max-width: 420px, и получался разрыв:
   таблица отводила колонке 543 пикселя, ячейка растягивалась только до
   452, а между ними оставалась полоса без содержимого и без фона.
   Подсветка строки на ней обрывалась, и выглядело это как пропавший
   столбец. Ячейка теперь занимает свою колонку целиком, а длинные
   названия сдерживает ограничение на тексте. */
/* Ячейка остаётся табличной: раскладку колонок считает браузер, и
   ячейка с display: flex из этого расчёта выпадает — колонке отводилось
   543 пикселя, а ячейка растягивалась только до 452, оставляя полосу без
   содержимого и без фона. Подсветка строки на ней обрывалась, и
   выглядело это как пропавший столбец. */
.vac__name {
  min-width: 240px;
}

.vac__name-box {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.vac__name-text {
  color: var(--c-text);
  font-weight: var(--w-medium);
  max-width: 420px;
}

/* Пометка о копиях приглушена: это уточнение к строке, а не её
   содержание. Курсор подсказки говорит, что объяснение есть. */
/* Источник — уточнение к строке, как и пометка о копиях. */
.vac__source {
  margin-left: var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-quiet);
  white-space: nowrap;
}

.vac__copies {
  margin-left: var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-quiet);
  white-space: nowrap;
  cursor: help;
}

.vac__company {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  max-width: 420px;
  /* Пометка «Снята» стоит рядом с компанией и переносится вместе с ней:
     на узком экране колонка названия сжимается до 240px, и без переноса
     статус выдавил бы таблицу за пределы своей прокрутки. */
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

/* Переключатели списка идут одной группой, чипы фильтров — отдельно.
   На узком экране группа переносится целиком, а не рассыпается. */
.vac__toggles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-3) var(--s-5);
}

.vac__exp { white-space: nowrap; }

/* Срок публикации не переносится: «3 дня назад» в две строки поднимает
   всю строку таблицы. Ширину держит содержимое — max-width на ячейке
   выбил бы её из табличной раскладки (см. правило в BvTable). */
.col-when { white-space: nowrap; }

.vac__empty { color: var(--c-text-quiet); }

/* Сомнительное число: приглушено и помечено знаком. Курсор подсказки
   говорит, что объяснение есть, — иначе знак читается как опечатка. */
.vac__doubt {
  color: var(--c-text-quiet);
  cursor: help;
  white-space: nowrap;
}

.vac__head-actions {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  flex-wrap: wrap;
}

.vac__rate-note {
  margin: var(--s-2) 0 0;
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.vac__period {
  display: block;
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  white-space: nowrap;
}

.vac__rub {
  display: block;
  font-size: var(--t-caption-size);
  color: var(--c-text-quiet);
  white-space: nowrap;
}

.vac__doubt-mark {
  margin-left: 2px;
  font-size: 0.85em;
  vertical-align: super;
}

.vac__skills {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  min-width: 0;
  max-width: 240px;
  /* Колонка сжимается, когда открыта панель вакансии: без обрезки
     чипы вылезали бы за правый край таблицы. */
  overflow: hidden;
}

/* Усекается название навыка, счётчик остатка — никогда: знание о
   двенадцати скрытых дороже полного написания одного из них. */
.vac__skills :deep(.chip) { min-width: 0; }
.vac__skills :deep(.chip--count) { flex: 0 0 auto; }

/* Почему вакансия найдена: тихая подпись в строке компании. */
.vac__why {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  white-space: nowrap;
}

/* Что поиск сделал с запросом. Не баннер: это пояснение, а не событие. */
.vac__search-note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
  max-width: none;
}
</style>
