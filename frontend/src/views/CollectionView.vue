<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvCheckbox from '@/components/ui/BvCheckbox.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvConfirmDialog from '@/components/ui/BvConfirmDialog.vue'
import BvField from '@/components/ui/BvField.vue'
import BvProgress from '@/components/ui/BvProgress.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import BvTable from '@/components/ui/BvTable.vue'
import { collection, settings } from '@/api/endpoints'
import { объяснитьОтказ } from '@/utils/collectionErrors'
import { useApi } from '@/composables/useApi'
import { useCollectionStatus } from '@/composables/useCollectionStatus'
import { useToast } from '@/composables/useToast'
import { useHeaderMeta } from '@/composables/useHeaderMeta'
import { dateTime, num, plural, timeAgo, vacancies as vacanciesCount } from '@/utils/format'

// Сбор данных. Экран отвечает на три вопроса: что собираем, что
// происходит прямо сейчас и что было раньше.
//
// Слово «парсер» здесь не появляется — ни в заголовках, ни в кнопках,
// ни в ошибках: пользователь запускает сбор данных, а не парсер.

const route = useRoute()
const router = useRouter()

const keywords = ref([])
const newKeyword = ref('')
const maxPages = ref('10')
const daysBack = ref('30')
const useCache = ref(true)

// Инкрементальный режим включён по умолчанию, и это не мелочь: без него
// сбор перезаписывает таблицу целиком. В API значение по умолчанию
// обратное, поэтому интерфейс всегда передаёт его явно.
const incremental = ref(true)
// Глубокий сбор: запрос, упёршийся в предел выдачи, режется на срезы.
// Включён по умолчанию — без него по популярному слову видно пятую часть
// рынка. Снимают галочку, когда нужен быстрый поверхностный проход.
const глубоко = ref(true)

const email = ref('')
const emailSaved = ref(false)

// Пауза между запросами к источнику. Значение приходит из настроек, а не
// подставляется на глаз: раньше настройка существовала, но до клиента не
// доходила — он всегда работал с задержкой по умолчанию.
const requestDelay = ref('1')
const delaySaved = ref(false)
const confirmOpen = ref(false)
const startError = ref('')

// Запрос на запуск летит секунду-другую: без признака занятости кнопку
// успевают нажать дважды, и второй запуск отвергается уже сервером.
const starting = ref(false)
// Остановка тоже идёт через сеть: без признака кнопка молчит, и человек
// жмёт её второй раз, думая, что промахнулся.
const stopping = ref(false)

const toast = useToast()
const status = useCollectionStatus()
const history = useApi((options) => collection.history(options))

// Чего не хватает в базе. Профессии, которые набрались попутно, по
// чужим запросам: в базе они есть случайно и неполно. Предложение —
// только строка в списке запросов; сбор по ней запускает человек.
const пробелы = useApi((options) => collection.suggestions(options))
const предложения = computed(() => пробелы.data.value?.['предложения'] ?? [])
const тонкие = computed(() => пробелы.data.value?.['тонкие_запросы'] ?? [])
const решается = ref('')

async function решитьПредложение(предложение, решение) {
  решается.value = предложение['ключ']
  try {
    const ответ = await collection.decideSuggestion({ 'ключ': предложение['ключ'], 'решение': решение })
    if (решение === 'accept') {
      keywords.value = [...ответ.search_queries]
      запросыСохранены.value = true
      toast.success(`«${ответ['запрос']}» в списке запросов`, 'Сбор по нему начнётся, когда вы его запустите')
    }
    пробелы.load()
  } catch (e) {
    toast.error('Решение не записано', e.message || 'Повторите позже', { label: 'Повторить', run: () => решитьПредложение(предложение, решение) })
  } finally {
    решается.value = ''
  }
}

// Расписание сбора. Ставит его команда на компьютере, где живёт
// продукт; экран показывает, что обещано и выполняется ли обещание.
const расписание = useApi((options) => collection.schedule(options))

const расписаниеСловами = computed(() => {
  const р = расписание.data.value
  if (!р?.['установлено']) return null
  const какЧасто = р['каждые_дней'] === 1 ? 'Каждый день' : `Раз в ${р['каждые_дней']} ${plural(р['каждые_дней'], 'день', 'дня', 'дней')}`
  return {
    когда: `${какЧасто} в ${р['время']}`,
    следующий: р['следующий'],
    последний: р['последний_сбор'],
    пропущен: р['пропущен'],
    дней: р['дней_без_сбора']
  }
})

// Пропуск называется числом дней, а пока удачных сборов не было — прямо.
const оПропуске = computed(() => {
  const р = расписаниеСловами.value
  if (!р?.пропущен) return ''
  return р.дней === null
    ? 'Расписание установлено, но ни один сбор по нему ещё не прошёл.'
    : `Сбора не было ${р.дней} ${plural(р.дней, 'день', 'дня', 'дней')} — дольше, чем обещает расписание.`
})

// Качество собранного — рядом с числом собранного.
//
// «Собрано 1891» ничего не говорит о том, годятся ли записи для
// аналитики. Карточка вакансии даёт 14,7 навыка против 2,4 без неё, и
// доля записей без карточки объясняет, почему навыков мало.
const качество = computed(() => history.data.value?.качество ?? null)

const долиКачества = computed(() => {
  const к = качество.value
  if (!к || !к.всего) return null
  return {
    всего: к.всего,
    сКарточкой: к.с_карточкой,
    долиКарточек: Math.round((к.с_карточкой / к.всего) * 100),
    безНавыков: к.без_навыков,
    доляБезНавыков: Math.round((к.без_навыков / к.всего) * 100),
  }
})
const settingsApi = useApi((options) => settings.collection(options))

onMounted(async () => {
  status.startPolling()
  history.load()
  расписание.load()
  пробелы.load()

  const saved = await settingsApi.load()
  email.value = saved?.email || ''
  emailSaved.value = Boolean(saved?.email)
  if (saved?.request_delay) requestDelay.value = String(saved.request_delay)

  // Список запросов приходит с сервера: раньше он жил в памяти вкладки
  // и пропадал при обновлении страницы — набранное приходилось
  // восстанавливать по памяти.
  if (Array.isArray(saved?.search_queries)) {
    keywords.value = [...saved.search_queries]
    запросыСохранены.value = keywords.value.length > 0
  }

  // С экрана «Профессии» сюда приходят с подставленным названием.
  const preset = route.query.keyword
  if (preset && !keywords.value.includes(preset)) {
    keywords.value.push(String(preset))
    сохранитьЗапросы()
  }

  списокЗагружен.value = true
})

const state = computed(() => status.state.value ?? {})
const isRunning = computed(() => status.isRunning.value)

// Один запрос повторять незачем: он ничего не добавит, а сбор удлинит.
const isDuplicate = computed(() => keywords.value.includes(newKeyword.value.trim()))

const canStart = computed(() => keywords.value.length > 0 && Boolean(email.value) && !isRunning.value)

// Объяснение отказа по коду причины. Текст исключения показывать нельзя:
// человеку нужно знать, что случилось и что делать, а не как называется
// сломавшаяся функция.
const отказ = computed(() => объяснитьОтказ(state.value?.error_type, state.value?.error_message || ''))

// Отказ, которого этот процесс уже не помнит. Состояние сбора живёт в
// памяти приложения, и после перезапуска экран выглядел так, будто
// ничего не случилось. Исход последнего запуска читается из базы — тем
// же запросом, что и шапка.
const { состояниеБазы } = useHeaderMeta()
const прежнийОтказ = computed(() => {
  const запуск = состояниеБазы.value?.last_run
  return запуск?.failed && !state.value?.error_message ? запуск : null
})

// Проверка доступа к источнику: один лёгкий запрос вместо целого сбора.
const проверка = ref(null)
const проверяем = ref(false)

async function проверитьСвязь() {
  проверяем.value = true
  проверка.value = null
  try {
    проверка.value = await collection.check()
  } catch (e) {
    проверка.value = { доступно: false, причина: 'network', подробности: e.message || '' }
  } finally {
    проверяем.value = false
  }
}

const startBlockedReason = computed(() => {
  if (isRunning.value) return 'Сбор уже идёт — дождитесь окончания или остановите его.'
  if (!email.value) return 'hh.ru требует контактный email в заголовке запроса: без него API отвечает 403.'
  if (!keywords.value.length) return 'Добавьте хотя бы один запрос — иначе собирать нечего.'
  return ''
})

// Цена сбора: сколько обращений к источнику и сколько это займёт.
//
// Считает сервер — она зависит от паузы между запросами и от того,
// включена ли резка на срезы. Здесь раньше стояло «полминуты на
// запрос»: сбор из четырёх запросов обещал две минуты и шёл
// восемнадцать.
const оценкаСбора = ref(null)

const estimate = computed(() => оценкаСбора.value?.фраза || '')

async function пересчитатьОценку() {
  if (!keywords.value.length) {
    оценкаСбора.value = null
    return
  }
  try {
    оценкаСбора.value = await collection.estimate({
      keywords_count: keywords.value.length,
      max_pages: Number(maxPages.value) || 10,
    })
  } catch {
    // Оценка — подсказка, а не условие запуска: её отсутствие не
    // должно мешать собирать.
    оценкаСбора.value = null
  }
}

watch([keywords, maxPages], пересчитатьОценку, { deep: true, immediate: true })

function addKeyword() {
  const value = newKeyword.value.trim()
  if (!value || isDuplicate.value) return
  keywords.value.push(value)
  newKeyword.value = ''
  сохранитьЗапросы()
}

function removeKeyword(word) {
  keywords.value = keywords.value.filter((k) => k !== word)
  сохранитьЗапросы()
}

// Список сохраняется сам, но не мгновенно: человек добавляет запросы
// подряд, и три обращения к серверу вместо одного здесь ни к чему.
//
// Отдельной кнопки «Сохранить» нет намеренно. Список из чипов — не
// форма: у него нет состояния «черновик», и кнопка означала бы, что
// набранное можно потерять, не нажав её. Вместо неё подпись рядом со
// списком: действие не должно молчать.
const запросыСохранены = ref(false)
const списокЗагружен = ref(false)
const ошибкаСохранения = ref('')
let отложенное = null

function сохранитьЗапросы() {
  запросыСохранены.value = false
  clearTimeout(отложенное)
  отложенное = setTimeout(async () => {
    try {
      await settings.saveCollection({ search_queries: keywords.value })
      запросыСохранены.value = true
      ошибкаСохранения.value = ''
    } catch (e) {
      ошибкаСохранения.value = e.message || 'Список не сохранён — правки живут только в этой вкладке.'
    }
  }, 600)
}

onBeforeUnmount(() => clearTimeout(отложенное))

async function saveEmail() {
  if (!email.value) return
  await settings.saveEmail({ email: email.value })
  emailSaved.value = true
}

// Пауза ниже 200 мс — прямой путь к отказам источника по частоте.
// Сервер такое значение не примет, и предупредить об этом лучше до
// отправки, а не после.
const delayTooLow = computed(() => Number(requestDelay.value) < 0.2)

async function saveDelay() {
  const значение = Number(requestDelay.value)
  if (!значение || delayTooLow.value) return
  await settings.saveCollection({ request_delay: значение })
  delaySaved.value = true
}

function добрать() {
  // Добор — тот же сбор, только заведомо глубокий и дописывающий: он
  // достаёт то, что осталось за пределом выдачи, и ничего не стирает.
  глубоко.value = true
  incremental.value = true
  start()
}

function requestStart() {
  startError.value = ''
  // Выключенный инкрементальный режим — необратимое действие: сбор
  // перезапишет таблицу целиком. Подтверждается вводом слова.
  if (!incremental.value) {
    confirmOpen.value = true
    return
  }
  start()
}

async function start() {
  confirmOpen.value = false
  startError.value = ''
  starting.value = true
  try {
    await collection.start({
      keywords: keywords.value,
      max_pages: maxPages.value,
      days_back: daysBack.value,
      incremental: incremental.value,
      use_cache: useCache.value,
      глубоко: глубоко.value
    })
    status.startPolling()
    // Сбор идёт минуты: о его начале сообщаем, чтобы уход на другой
    // экран не выглядел потерей запуска.
    toast.progress('Сбор запущен', `${keywords.value.length} ${keywords.value.length === 1 ? 'запрос' : 'запроса и более'} · страницу можно закрыть`)
  } catch (e) {
    startError.value = e.message || 'Сбор не запустился.'
    toast.error('Сбор не запустился', startError.value, {
      label: 'Повторить',
      run: () => requestStart()
    })
  } finally {
    starting.value = false
  }
}

async function stop() {
  stopping.value = true
  try {
    await collection.stop()
    status.fetchStatus()
    toast.success('Сбор остановлен', 'Собранное записано в базу — ничего не потеряно')
  } finally {
    stopping.value = false
  }
}

watch(isRunning, async (running, was) => {
  if (!was || running) return

  // Сбор закончился — обновляем историю: она и есть результат.
  await history.load()

  const last = history.data.value?.history?.[0]
  if (!last) return

  if (last.status === 'completed') {
    toast.success(
      `Сбор завершён — ${vacanciesCount(last.vacancies_collected || 0)}`,
      `${last.vacancies_new || 0} новых, ${last.vacancies_updated || 0} обновлено`,
      { label: 'Открыть аналитику', run: () => router.push({ name: 'analytics' }) }
    )
  } else if (last.error_message) {
    toast.error('Сбор прервался', last.error_message, {
      label: 'Запустить заново',
      run: () => requestStart()
    })
  }
})

const runs = computed(() => history.data.value?.history ?? [])

// Что последний сбор не увидел.
//
// Источник обрывает выдачу: по популярному запросу мы читаем первую
// тысячу вакансий из нескольких тысяч. Раньше об этом говорила только
// пометка «partial» в разбивке — слово, которого человек не знает, и
// без числа. Показываем размер потери словами и по самому потерянному
// запросу: с него начнётся резка на срезы.
const недобор = computed(() => {
  const п = runs.value.find((r) => r['недобор']?.вакансий > 0)
  return п ? п['недобор'] : null
})

// Одной строкой: сколько не увидели и по какому запросу больнее всего.
// Второе предложение важнее первого — с этого запроса начнётся резка
// на срезы.
const подписьНедобора = computed(() => {
  const н = недобор.value
  if (!н) return ''
  const худший = н.по_запросам[0]
  if (!худший) return н.фраза
  return `${н.фраза} Больше всего по запросу «${худший.запрос}»: `
    + `источник знает ${num(худший.найдено)}, прочитано ${num(худший.взято)}.`
})

// Качество запуска: какая доля собранного годится для аналитики.
//
// Вакансия без карточки несёт 2,4 навыка вместо 14,7, а запрос,
// прочитанный не до конца, даёт недобор. Одна доля в колонке, остальное
// — подсказкой: колонка на пять чисел нечитаема.
function качествоЗапуска(run) {
  const к = run['качество']
  const всего = run.vacancies_collected || 0
  if (!к || к.с_карточкой === null || к.с_карточкой === undefined || !всего) return null
  return {
    доля: Math.round((к.с_карточкой / всего) * 100),
    сКарточкой: к.с_карточкой,
    безНавыков: к.без_навыков,
    неполных: к.неполных_запросов,
    всего,
  }
}

function подписьКачества(run) {
  const к = качествоЗапуска(run)
  if (!к) return 'Этот сбор шёл до того, как качество стало записываться.'
  const части = [
    // Формулировка выбрана так, чтобы не склонять «запись» по числу:
    // «у 231 записей» — ошибка, «у 231 из 234 записей» верно всегда.
    `Карточка вакансии есть у ${к.сКарточкой} из ${к.всего} записей.`,
    `Без единого навыка — ${к.безНавыков}.`,
  ]
  if (к.неполных) {
    части.push(`Запросов, прочитанных не до конца: ${к.неполных}.`)
  }
  return части.join(' ')
}

// Сколько осталось. Оценка по скорости этого же сбора; до первых
// замеров сервер её не даёт, и тогда строки нет вовсе — число, которое
// через минуту сменится втрое, хуже отсутствующего.
const осталось = computed(() => {
  const секунд = state.value.eta_seconds
  if (секунд === null || секунд === undefined) return ''
  if (секунд < 60) return 'осталось меньше минуты'
  const минут = Math.round(секунд / 60)
  return `осталось примерно ${минут} ${plural(минут, 'минута', 'минуты', 'минут')}`
})

// Запросы сбора: что уже принёс каждый, какой идёт, какие ждут.
// Сбор идёт десятки минут, и всё это время у него есть промежуточный
// итог — показывать вместо него одну полосу значило прятать результат.
const ВИД_ЗАПРОСА = {
  done: { kind: 'ok', слово: 'Собран' },
  running: { kind: 'run', слово: 'Идёт' },
  skipped: { kind: 'stop', слово: 'Пропущен' },
  waiting: { kind: 'idle', слово: 'Ждёт' }
}

const ходЗапросов = computed(() => (state.value.queries || []).map((q) => {
  let итог = ''
  if (q.status === 'done') {
    итог = `${vacanciesCount(q.found || 0)} · новых ${num(q.new || 0)}`
  } else if (q.status === 'running' && q.found) {
    итог = `найдено ${num(q.found)}`
  } else if (q.status === 'skipped') {
    итог = 'собран прерванной попыткой'
  }
  return { ...q, ...(ВИД_ЗАПРОСА[q.status] || ВИД_ЗАПРОСА.waiting), итог }
}))

// Только что найденное. Названия сменяются по ходу сбора: по ним видно
// не только что работа идёт, но и что именно она приносит.
const лента = computed(() => state.value.recent || [])

// Подпись под полосой хода.
//
// Про пропущенные запросы сказано отдельно: сбор из семи запросов,
// прошедший за минуту, иначе выглядит поломкой. Пропущены они потому,
// что их вакансии собрала прерванная попытка и они уже в базе.
const подписьХода = computed(() => {
  const s = state.value
  const части = [`${vacanciesCount(s.vacancies_collected || 0)} собрано`]
  // Запрос из скольких — главная мера хода: процент считается по ним.
  if (s.keyword_index && s.keywords_total > 1) {
    части.push(`запрос ${s.keyword_index} из ${s.keywords_total}`)
  }
  // Страниц столько, сколько будет прочитано, а не глубина обхода:
  // «страница 0 из 10» при выдаче на две страницы обещала восемь лишних.
  if (s.pages_expected) {
    части.push(`страница ${Math.min((s.current_page || 0) + 1, s.pages_expected)} из ${s.pages_expected}`)
  }
  const пропущено = s['пропущено_пройденных'] || 0
  if (пропущено) {
    части.push(
      `${пропущено} ${пропущено === 1 ? 'запрос' : 'запроса и более'} пропущено — `
      + 'их собрала прерванная попытка'
    )
  }
  return части.join(' · ')
})

function statusOf(run) {
  if (run.status === 'completed') return { kind: 'ok', label: 'Завершён' }
  if (run.status === 'running') return { kind: 'run', label: 'Идёт' }
  if (run.status === 'stopped') return { kind: 'stop', label: 'Остановлен' }
  // Прерванный — это не ошибка сбора, а обрыв снаружи: приложение
  // перезапустили, пока он работал. Собранное до обрыва осталось в базе,
  // и путать это со сбоем не стоит — действия у них разные.
  if (run.status === 'interrupted') return { kind: 'stop', label: 'Прерван' }
  if (run.status === 'error' || run.status === 'failed' || run.error_message) {
    return { kind: 'err', label: 'Ошибка' }
  }
  return { kind: 'idle', label: 'В очереди' }
}

function durationOf(run) {
  if (!run.started_at || !run.completed_at) return '—'
  const ms = new Date(run.completed_at) - new Date(run.started_at)
  if (Number.isNaN(ms) || ms < 0) return '—'
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.round((ms % 60000) / 1000)
  return minutes ? `${minutes} мин ${seconds} с` : `${seconds} с`
}
</script>

<template>
  <section class="col">
    <header class="col__head">
      <div class="col__titles">
        <h1>Сбор данных</h1>
        <p class="col__meta">
          Соберите вакансии с hh.ru по своим запросам. Сбор идёт минуты — страницу можно
          не держать открытой, но результат появится только после возвращения.
        </p>
      </div>
    </header>

    <!-- Идущий сбор занимает первое место на экране: пока он работает,
         это единственное, что интересует пользователя. -->
    <BvCard v-if="isRunning" title="Сбор идёт">
      <template #actions>
        <BvStatus kind="run" label="Идёт" />
      </template>

      <BvProgress
        :value="state.progress || 0"
        :current="state.current_keyword ? `Сейчас: ${state.current_keyword}` : 'Готовим запросы'"
        :note="подписьХода"
      />
      <p v-if="осталось" class="col__eta">{{ осталось }}</p>

      <div v-if="ходЗапросов.length || лента.length" class="col__live">
        <section v-if="ходЗапросов.length" class="col__live-block" aria-label="Запросы сбора">
          <h3 class="col__live-title">Запросы</h3>
          <ul class="col__queries">
            <li v-for="q in ходЗапросов" :key="q.keyword" class="col__query" :class="{ 'is-waiting': q.status === 'waiting' }">
              <span class="col__query-name">{{ q.keyword }}</span>
              <span class="col__query-note">{{ q.итог }}</span>
              <BvStatus :kind="q.kind" :label="q.слово" />
            </li>
          </ul>
        </section>

        <!-- Лента не объявляется читалкой экрана: новая вакансия раз в
             несколько секунд перебивала бы человека на полуслове. -->
        <section v-if="лента.length" class="col__live-block" aria-label="Только что найдено" aria-live="off">
          <h3 class="col__live-title">Только что найдено</h3>
          <TransitionGroup tag="ul" name="col-feed" class="col__feed">
            <li v-for="в in лента" :key="`${в.name}·${в.employer}·${в.area}`" class="col__feed-item">
              <span class="col__feed-name">{{ в.name }}</span>
              <span class="col__feed-meta">{{ [в.employer, в.area].filter(Boolean).join(' · ') }}</span>
            </li>
          </TransitionGroup>
        </section>
      </div>

      <BvButton :loading="stopping" @click="stop">Остановить сбор</BvButton>
    </BvCard>

    <!-- Ошибка объясняет причину и следующий шаг, а не показывает текст
         исключения: из него не следует ни что случилось, ни что делать. -->
    <BvBanner
      v-else-if="state.error_message"
      kind="error"
      :title="отказ.title"
      :text="`${отказ.text} Собранные до остановки вакансии сохранены в базе.`"
    >
      <template #actions>
        <BvButton size="md" :loading="starting" :disabled="!canStart" @click="requestStart">Повторить сбор</BvButton>
      </template>
    </BvBanner>

    <BvBanner
      v-else-if="прежнийОтказ"
      kind="error"
      :title="прежнийОтказ.title"
      :text="`${прежнийОтказ.text} Это исход последнего запуска, ${timeAgo(прежнийОтказ.finished_at)}.`"
    >
      <template #actions>
        <BvButton size="md" :loading="starting" :disabled="!canStart" @click="requestStart">Повторить сбор</BvButton>
      </template>
    </BvBanner>

    <div class="col__grid">
      <BvCard title="Что собираем">
        <div class="col__keywords">
          <div class="col__add">
            <BvField
              v-model="newKeyword"
              label="Запрос для поиска"
              placeholder="Например: HR-менеджер"
              :state="isDuplicate && newKeyword ? 'error' : 'default'"
              :message="isDuplicate && newKeyword ? 'Такой запрос уже в списке — повторный сбор по нему ничего не добавит.' : ''"
              hint="Каждый запрос удлиняет сбор примерно на полминуты."
              @keydown.enter="addKeyword"
            />
            <BvButton :disabled="!newKeyword.trim() || isDuplicate" @click="addKeyword">Добавить</BvButton>
          </div>

          <div v-if="keywords.length" class="col__chips">
            <BvChip
              v-for="word in keywords"
              :key="word"
              variant="filter"
              removable
              :remove-label="`Убрать запрос ${word}`"
              @remove="removeKeyword(word)"
            >{{ word }}</BvChip>
          </div>
          <p v-else class="col__note">Список пуст. Добавьте запрос — или выберите профессию в разделе «Профессии».</p>

          <p v-if="ошибкаСохранения" class="col__note col__note--warn">{{ ошибкаСохранения }}</p>
          <p v-else-if="запросыСохранены && списокЗагружен" class="col__note col__note--ok">
            Список сохранён — он останется здесь после обновления страницы.
          </p>

          <p v-if="keywords.length" class="col__note">{{ estimate }}</p>
        </div>
      </BvCard>

      <BvCard title="Настройки сбора">
        <div class="col__settings">
          <BvField
            v-model="email"
            label="Email для hh.ru"
            required
            placeholder="you@company.ru"
            :state="emailSaved && email ? 'checked' : 'default'"
            :message="emailSaved && email ? 'Email сохранён — сбор можно запускать.' : ''"
            hint="hh.ru требует контакт в заголовке запроса. Без него API отвечает 403."
            @blur="saveEmail"
          />

          <!-- Проверка доступа до запуска: узнать, что ключ отклонён,
               лучше сейчас, чем на середине десятиминутного сбора.
               Подтверждение приходит от самого источника, а не от нашей
               проверки формата. -->
          <div class="col__check">
            <BvButton size="md" :loading="проверяем" @click="проверитьСвязь">
              Проверить связь
            </BvButton>

            <BvStatus
              v-if="проверка && проверка.доступно"
              kind="ok"
              :label="`Связь есть · ${проверка.задержка_мс} мс`"
            />
            <BvStatus
              v-else-if="проверка"
              kind="err"
              :label="объяснитьОтказ(проверка.причина).title"
            />
          </div>

          <BvField
            v-model="requestDelay"
            label="Пауза между запросами"
            type="number"
            suffix="с"
            :state="delayTooLow ? 'error' : (delaySaved ? 'checked' : 'default')"
            :message="delayTooLow ? 'Меньше 0,2 с — источник начнёт отказывать по частоте.' : (delaySaved ? 'Пауза сохранена — применится к следующему сбору.' : '')"
            hint="Чем меньше пауза, тем быстрее сбор и выше риск отказа источника."
            @blur="saveDelay"
          />

          <div class="col__pair">
            <BvField v-model="maxPages" label="Страниц на запрос" suffix="стр" hint="100 вакансий на странице." />
            <BvField v-model="daysBack" label="Глубина поиска" suffix="дн" hint="hh.ru отдаёт вакансии за ограниченный срок." />
          </div>

          <BvCheckbox v-model="incremental" label="Дописывать к базе, не стирая собранное" />
          <BvCheckbox v-model="useCache" label="Использовать кеш ответов hh.ru" />
          <BvCheckbox
            v-model="глубоко"
            label="Собирать глубоко: резать запросы, упёршиеся в предел выдачи"
          />
          <!-- Цена названа до запуска, а не после. Источник отдаёт не
               больше 2000 вакансий на запрос, и резка — единственный
               способ увидеть остальное; карточки внутри срезов не
               запрашиваются, поэтому охват стоит минут, а не часов. -->
          <BvBanner
            v-if="!глубоко"
            kind="info"
            title="Сбор будет поверхностным"
            text="По популярному запросу источник отдаст не больше 2000 вакансий, и остальное останется непрочитанным. Так быстрее, но по такой базе нельзя судить о рынке."
          />

          <!-- Предупреждение появляется ровно тогда, когда режим опасен,
               и говорит, что именно будет потеряно. Закрыть его нельзя:
               оно исчезает вместе с причиной. -->
          <BvBanner
            v-if="!incremental"
            kind="warning"
            title="Следующий сбор перезапишет базу целиком"
            text="Собранные вакансии будут удалены и заменены результатом нового запроса. Действие подтверждается вводом слова."
          >
            <template #actions>
              <BvButton size="md" @click="incremental = true">Включить дописывание</BvButton>
            </template>
          </BvBanner>
        </div>
      </BvCard>
    </div>

    <div class="col__start">
      <BvButton
        variant="primary"
        :disabled="!canStart"
        :loading="starting"
        @click="requestStart"
      >Запустить сбор</BvButton>
      <!-- Выключенная кнопка всегда сопровождается объяснением: без него
           она читается как поломка. -->
      <span v-if="startBlockedReason" class="col__note">{{ startBlockedReason }}</span>
      <span v-if="startError" class="col__error">{{ startError }}</span>
    </div>

    <BvCard v-if="предложения.length || тонкие.length" title="Чего не хватает в базе">
      <template #actions>
        <span class="col__note">считается по базе, сбор сам не начинается</span>
      </template>

      <BvTable v-if="предложения.length" label="Предложенные запросы" sticky-first>
        <thead>
          <tr>
            <th>Запрос</th>
            <th class="col-num">Уже в базе</th>
            <th class="col-num">Работодателей</th>
            <th>Почему предложен</th>
            <th>Решение</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="предложение in предложения" :key="предложение['ключ']">
            <td><span class="col__suggest">{{ предложение['запрос'] }}</span></td>
            <td class="col-num">{{ num(предложение['вакансий']) }}</td>
            <td class="col-num">{{ num(предложение['работодателей']) }}</td>
            <td><span class="col__reason">{{ предложение['основание'] }}</span></td>
            <td>
              <div class="col__decide">
                <BvButton size="sm" :loading="решается === предложение['ключ']" :disabled="Boolean(решается)" @click="решитьПредложение(предложение, 'accept')">В запросы</BvButton>
                <BvButton size="sm" variant="quiet" :disabled="Boolean(решается)" @click="решитьПредложение(предложение, 'reject')">Не нужно</BvButton>
              </div>
            </td>
          </tr>
        </tbody>
      </BvTable>

      <p v-if="тонкие.length" class="col__note">
        Тонкая выборка — меньше {{ пробелы.data.value['порог_тонкой_выборки'] }} активных вакансий:
        <template v-for="(запрос, i) in тонкие" :key="запрос['запрос']">
          <template v-if="i > 0">, </template>«{{ запрос['запрос'] }}» — {{ num(запрос['вакансий']) }}
        </template>. Числа по таким запросам ненадёжны.
      </p>
    </BvCard>

    <BvCard title="Сбор по расписанию">
      <template #actions>
        <BvStatus
          v-if="расписание.data.value"
          :kind="расписаниеСловами ? 'ok' : 'stop'"
          :label="расписаниеСловами ? 'Включён' : 'Не установлен'"
        />
      </template>

      <!-- Пропуск не шлёт оповещений сам: сбор, который не запустился,
           сообщить о себе не может. Поэтому он назван здесь. -->
      <BvBanner
        v-if="оПропуске"
        kind="warning"
        title="Сбор по расписанию не прошёл"
        :text="`${оПропуске} Обычно это значит, что компьютер был выключен или задание планировщика не запускается.`"
      />

      <dl v-if="расписаниеСловами" class="col__schedule">
        <div>
          <dt class="label">Когда</dt>
          <dd>{{ расписаниеСловами.когда }}</dd>
        </div>
        <div>
          <dt class="label">Следующий запуск</dt>
          <dd>{{ dateTime(расписаниеСловами.следующий) }}</dd>
        </div>
        <div>
          <dt class="label">Последний удачный сбор</dt>
          <dd>{{ расписаниеСловами.последний ? timeAgo(расписаниеСловами.последний) : 'ещё не было' }}</dd>
        </div>
      </dl>

      <p v-if="расписание.error.value" class="col__error">{{ расписание.error.value }}</p>
      <p v-else-if="расписаниеСловами" class="col__note">
        Сбор идёт по запросам из списка выше и только дописывает к базе; перед ним снимается её копия.
        Компьютер должен быть включён: пропущенный запуск пройдёт при следующем включении.
      </p>
      <p v-else-if="расписание.data.value" class="col__note">
        Сейчас сбор идёт только по кнопке. Расписание ставится на компьютере, где работает продукт, командой
        <span class="col__command">python scripts/расписание.py --установить --время 03:30</span>
      </p>
    </BvCard>

    <BvCard title="История сборов">
      <template #actions>
        <span class="col__note">{{ runs.length ? `${runs.length} запусков` : '' }}</span>
      </template>

      <!-- Качество базы стоит здесь, а не в логах: по нему видно, годятся
           ли собранные записи для аналитики. Вакансия без карточки несёт
           2,4 навыка вместо 14,7 — и это главная причина, по которой
           навыков в продукте мало. -->
      <p v-if="долиКачества" class="col__quality">
        Из {{ num(долиКачества.всего) }} записей карточка вакансии есть у
        {{ num(долиКачества.сКарточкой) }} ({{ долиКачества.долиКарточек }} %).
        Без единого навыка — {{ num(долиКачества.безНавыков) }}
        ({{ долиКачества.доляБезНавыков }} %).
        <template v-if="долиКачества.долиКарточек < 90">
          Карточки для остальных добираются отдельным проходом.
        </template>
        <RouterLink to="/dictionary">Чего не знает словарь навыков</RouterLink>
      </p>

      <!-- Недобор стоит рядом с качеством, а не в разбивке запуска:
           это свойство всей базы, а не одного запуска. Молчание здесь
           означало бы, что собранное — весь рынок. -->
      <!-- Вид info, а не warning: сбор отработал верно, предел выдачи
           поставил источник. Это состояние, о котором надо знать, а не
           режим, который что-то испортит. -->
      <BvBanner
        v-if="недобор"
        kind="info"
        title="Часть выдачи осталась непрочитанной"
        :text="подписьНедобора"
      >
        <!-- Действие стоит там, где о проблеме узнают. Отправлять
             человека искать галочку в настройках сбора значит потерять
             его на полпути. -->
        <template #actions>
          <BvButton
            size="md"
            :loading="starting"
            :disabled="!canStart"
            @click="добрать"
          >
            Добрать непрочитанное
          </BvButton>
        </template>
      </BvBanner>

      <p v-if="!runs.length" class="col__note">Сборов ещё не было. Первый запуск появится здесь сразу после запуска.</p>

      <BvTable v-else label="История сборов" sticky-first>
        <thead>
          <tr>
            <th>Запуск</th>
            <th>Состояние</th>
            <th>Запросы</th>
            <th class="col-num">Собрано</th>
            <th class="col-num">С карточкой</th>
            <th class="col-num">Длительность</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in runs" :key="run.id">
            <td class="col__run">
              <span class="col__run-date">{{ dateTime(run.started_at) }}</span>
              <span class="col__run-ago">
                {{ timeAgo(run.started_at) }}<template v-if="run.source === 'schedule'"> · по расписанию</template>
              </span>
            </td>
            <td>
              <BvStatus :kind="statusOf(run).kind" :label="statusOf(run).label" />
            </td>
            <td class="col__run-keywords">{{ (run.keywords || []).join(', ') || '—' }}</td>
            <td class="col-num">{{ num(run.vacancies_collected || 0) }}</td>
            <td class="col-num" :title="подписьКачества(run)">
              <template v-if="качествоЗапуска(run)">{{ качествоЗапуска(run).доля }} %</template>
              <span v-else class="col__unknown">—</span>
            </td>
            <td class="col-num">{{ durationOf(run) }}</td>
          </tr>
        </tbody>
      </BvTable>
    </BvCard>

    <BvConfirmDialog
      :open="confirmOpen"
      title="Перезаписать базу целиком?"
      message="Инкрементальный режим выключен. Сбор удалит все собранные вакансии и заменит их результатом нового запроса. Отменить это будет нельзя."
      word="перезаписать"
      confirm-label="Перезаписать и запустить"
      @confirm="start"
      @cancel="confirmOpen = false"
    />
  </section>
</template>

<style scoped>
/* Расписание тремя парами «подпись — значение» в ряд, как строка итогов. */
.col__schedule {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(200px, 100%), 1fr));
  gap: var(--s-4) var(--s-6);
}

.col__schedule div {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.col__schedule dd {
  margin: 0;
  font-size: var(--t-body-size);
  color: var(--c-text);
}

/* Ячейки предложений: раскладка — во вложенных блоках, ширину колонок
   считает таблица. */
.col__suggest {
  display: block;
  min-width: 150px;
  color: var(--c-text);
  font-weight: var(--w-medium);
}

.col__reason {
  display: block;
  min-width: 260px;
  max-width: 520px;
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
}

.col__decide {
  display: flex;
  gap: var(--s-2);
  white-space: nowrap;
}

/* Команда — то, что набирают дословно: моноширинным и без переноса посреди слова. */
.col__command {
  font-family: var(--font-mono);
  font-size: var(--t-label-alt-size);
  color: var(--c-text-secondary);
  overflow-wrap: anywhere;
}

.col {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.col__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.col__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.col__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr));
  gap: var(--gap-grid);
  align-items: start;
}

.col__keywords,
.col__settings {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.col__add {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--s-3);
  align-items: start;
}

/* Кнопка выравнивается по полю, а не по его подписи. */
.col__add > :deep(.btn) { margin-top: 22px; }

/* Кнопка проверки и её результат стоят в строку и переносятся вместе:
   на узком экране статус уходит под кнопку, а не выдавливает её. */
.col__check {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-3);
}

.col__pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-3);
}

.col__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.col__start {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-3);
}

/* Прочерк — это «не измеряли», а не «ноль». Приглушённый цвет
   отличает его от числа, которое действительно посчитано. */
.col__unknown {
  color: var(--c-text-quiet);
}

.col__quality {
  margin: 0 0 var(--s-3);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

.col__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

/* Подтверждение и отказ подписью, а не тостом: список правится по
   одному запросу, и всплывающее окно на каждое добавление — шум. */
.col__note--ok { color: var(--c-positive); }
.col__note--warn { color: var(--c-negative); }

.col__error {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-status-err-text);
  max-width: none;
}

.col__run {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 190px;
}

.col__run-date {
  color: var(--c-text);
  font-weight: var(--w-medium);
}

.col__run-ago {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.col__run-keywords {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Сколько осталось — под полосой, тише её подписи: это оценка. */
.col__eta {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

/* Живой ход сбора: слева запросы, справа только что найденное. Обе
   колонки сжимаются до нуля — длинное название вакансии обрезается
   многоточием, а не распирает страницу. */
.col__live {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--s-6);
  padding-top: var(--s-4);
  box-shadow: inset 0 1px 0 var(--c-border);
}

.col__live-block { min-width: 0; }

.col__live-title {
  margin-bottom: var(--s-3);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  font-weight: var(--w-medium);
  color: var(--c-text-secondary);
}

.col__queries,
.col__feed {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.col__query {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--s-3);
  min-height: var(--h-control-sm);
}

.col__query-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.col__query-note {
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-secondary);
  white-space: nowrap;
}

/* Запрос, до которого сбор ещё не дошёл, приглушён, но виден: по нему
   понятно, сколько работы впереди. */
.col__query.is-waiting .col__query-name {
  color: var(--c-text-muted);
  font-weight: var(--w-regular);
}

.col__feed { position: relative; }

.col__feed-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.col__feed-name,
.col__feed-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col__feed-name {
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.col__feed-meta {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

/* Новая вакансия въезжает сверху, остальные сдвигаются. Уходящая
   снимается из потока, иначе список на мгновение становится длиннее и
   дёргает кнопку под ним. */
.col-feed-enter-active,
.col-feed-leave-active,
.col-feed-move { transition: opacity 0.25s ease, transform 0.25s ease; }
.col-feed-enter-from { opacity: 0; transform: translateY(-8px); }
.col-feed-leave-to { opacity: 0; }
.col-feed-leave-active { position: absolute; left: 0; right: 0; }

/* Движение — подсказка, а не содержание: тем, кто просил его убрать,
   лента просто меняет строки. */
@media (prefers-reduced-motion: reduce) {
  .col-feed-enter-active,
  .col-feed-leave-active,
  .col-feed-move { transition: none; }
}

/* До 768px две колонки не помещаются: лента уходит под запросы, а итог
   запроса — под его название. */
@media (max-width: 767px) {
  .col__live { grid-template-columns: minmax(0, 1fr); }
  .col__query { grid-template-columns: minmax(0, 1fr) auto; }
  .col__query-note { grid-column: 1; grid-row: 2; white-space: normal; }
  .col__query > :last-child { grid-column: 2; grid-row: 1 / span 2; }
}
</style>
