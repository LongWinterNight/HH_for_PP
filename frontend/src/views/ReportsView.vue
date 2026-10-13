<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvModal from '@/components/ui/BvModal.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import BvTable from '@/components/ui/BvTable.vue'
import { reports } from '@/api/endpoints'
import { useHeaderMeta } from '@/composables/useHeaderMeta'
import { изАдреса, вАдрес } from '@/app/адрес'
import { СХЕМА_СРЕЗА } from '@/views/vacancies-адрес'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { dateTime, num, plural, timeAgo, vacancies as vacanciesCount } from '@/utils/format'

// Отчёты: готовые файлы и сборка новых.
//
// Сборка идёт в фоне, но её итог теперь известен: бэкенд держит
// состояние (idle, running, done, error), и экран спрашивает его, пока
// сборка не кончится. До этого кнопка отвечала «Генерация запущена» и
// замолкала — упавшая сборка выглядела так же, как удачная.

const toast = useToast()
const list = useApi((options) => reports.list(options))
// Пуста ли база — из сводки шапки, без запроса расчёта дашборда.
const { состояниеБазы } = useHeaderMeta()
const building = ref(false)
const buildError = ref('')

// Пауза между опросами. Сборка занимает секунды: чаще — лишние
// запросы, реже — человек ждёт уже готовый файл.
const ПАУЗА = 1000
// Предел ожидания. Дальше экран перестаёт спрашивать и говорит об этом
// прямо: молча крутить кнопку бесконечно — это тот же обман, только
// дольше.
const ПРЕДЕЛ = 120000

// Срез приходит ссылкой с «Вакансий»: там человек настроил выборку, и
// файл должен собраться ровно по ней. Без параметров — вся база, как
// раньше.
const route = useRoute()
const срез = computed(() => изАдреса(route.query, СХЕМА_СРЕЗА))
const параметрыСреза = computed(() => вАдрес(срез.value, СХЕМА_СРЕЗА))
const срезЗадан = computed(() => Object.keys(параметрыСреза.value).length > 0)

// Что попадёт в файл. Считает сервер теми же выражениями, что наполняют
// листы: свой подсчёт на экране разошёлся бы с файлом при первой правке.
const состав = useApi((параметры, options) => reports.preview(параметры, options))

function обновитьСостав() {
  состав.load(срез.value)
}

onMounted(() => {
  list.load()
  обновитьСостав()
})

// Ссылка со срезом может открыться поверх уже открытого экрана.
watch(() => route.fullPath, обновитьСостав)

// Листы файла и их объём. Состав известен до сборки — человек видит,
// что получит, а не узнаёт это, открыв файл.
const листы = computed(() => {
  const с = состав.data.value
  if (!с) return []
  return [
    { имя: 'Срез', объём: 'титульный', пояснение: 'Что за выборка, когда собрана и по какому источнику. Лист обязателен.' },
    { имя: 'Вакансии', объём: строк(с.вакансий), пояснение: 'Плоская таблица: название, компания, регион, зарплата, опыт, навыки, ID.' },
    {
      имя: 'Сводка',
      объём: с.валют ? `${с.валют} ${plural(с.валют, 'валюта', 'валюты', 'валют')}` : 'нет данных',
      пояснение: с.валют
        ? 'Минимум, медиана, средняя и максимум по каждой валюте. Валюты не складываются.'
        : 'В выборке нет вакансий с указанной зарплатой — считать нечего.',
      выключен: !с.валют,
    },
    {
      имя: 'Навыки',
      объём: с.навыков ? строк(с.навыков) : 'нет данных',
      пояснение: с.навыков_всего > с.навыков
        ? `Частота навыков по убыванию. В файл идут первые ${с.навыков} из ${с.навыков_всего}.`
        : 'Частота навыков в выборке, отсортированная по убыванию.',
      выключен: !с.навыков,
    },
  ]
})

function строк(n) {
  return `${num(n)} ${plural(n, 'строка', 'строки', 'строк')}`
}

// Выборка мала для отчёта как документа: медианы по девяти вакансиям —
// не показатель рынка. Это предупреждение, а не запрет: срез из пяти
// строк бывает нужен для проверки.
const выборкаМала = computed(() => Boolean(состав.data.value?.малая_выборка) && !пустойСрез.value)
const пустойСрез = computed(() => состав.data.value?.вакансий === 0)

// Кнопка сборки при пустой базе выключена: файл из нулевых строк
// выглядит как поломка отчёта, а не как пустая база.
const базаПуста = computed(() => состояниеБазы.value?.active === 0)

const files = computed(() => list.data.value?.reports ?? [])

// Срок хранения приходит с сервера: правило действует там, и число на
// экране не должно расходиться с тем, по которому файлы убираются.
const срокХранения = computed(() => list.data.value?.retention?.days ?? 30)
// Убранное по сроку при этой загрузке списка. Файл, исчезнувший молча,
// выглядит как потеря — поэтому уборка называется.
const убранные = computed(() => list.data.value?.retention?.removed ?? [])

// Состояние одним словом, как на остальных экранах. Срок уходит в
// подпись под ним: там он читается и не ломает колонку.
function состояние(file) {
  if (file.state === 'expiring') {
    const дней = file.expires_in_days
    return {
      kind: 'stop',
      слово: 'Истекает',
      подпись: дней > 0 ? `через ${дней} ${plural(дней, 'день', 'дня', 'дней')}` : 'сегодня',
    }
  }
  return { kind: 'ok', слово: 'Готов', подпись: '' }
}

// Тип файла — часть данных, а не догадка по значку: расширение
// определяет, чем файл откроется.
function kindOf(name) {
  const ext = name.split('.').pop()?.toUpperCase() || '—'
  return ext
}

function sizeOf(bytes) {
  if (!bytes) return '—'
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
  return `${Math.round(bytes / 1024)} КБ`
}

function пауза(мс) {
  return new Promise((resolve) => setTimeout(resolve, мс))
}

function отказ(текст) {
  buildError.value = текст
  toast.error('Отчёт не собрался', текст, { label: 'Повторить', run: () => build() })
}

async function build() {
  if (building.value) return

  building.value = true
  buildError.value = ''
  try {
    // Сборке уходят поля API (search, area, salary_only), а не короткие
    // имена из адреса (q, area, paid). Их легко перепутать: оба объекта
    // описывают один и тот же срез. Промах виден только по числу строк
    // в готовом файле — в первый раз он собрался по 606 вакансиям
    // вместо 18.
    const запуск = await reports.generate(срез.value)

    // Отказ до начала работы: пустая база или уже идущая сборка. Ответ
    // называет причину словами — своё объяснение придумывать не нужно.
    if (запуск?.accepted === false) {
      отказ(запуск.error || 'Сборка не запустилась.')
      return
    }

    toast.progress('Собираем отчёт', 'Кнопка останется занятой, пока файл не будет готов')

    const крайний = Date.now() + ПРЕДЕЛ
    // Кнопка держится в состоянии работы всё время сборки, а не долю
    // секунды, пока идёт запрос на запуск.
    while (Date.now() < крайний) {
      await пауза(ПАУЗА)
      const состояние = await reports.status()

      if (состояние.status === 'done') {
        await list.load()
        toast.success(
          'Отчёт собран',
          `${vacanciesCount(состояние.vacancies)} в файле`,
          { label: 'Скачать', run: () => download(состояние.file) }
        )
        return
      }

      if (состояние.status === 'error') {
        отказ(состояние.error || 'Сборка прервалась.')
        return
      }
    }

    // Сборка не уложилась в предел. Файл может ещё появиться, поэтому
    // это не отказ: список обновляется, а человеку сказано, что ждать
    // у кнопки больше нечего.
    await list.load()
    toast.progress(
      'Сборка идёт дольше обычного',
      'Файл появится в списке сам — обновите его через минуту'
    )
  } catch (e) {
    отказ(e.message || 'Отчёт не собрался.')
  } finally {
    building.value = false
  }
}

// Что показать вместо среза у файла, который продукт не собирал.
const ЧУЖОЙ_ФАЙЛ = 'Файл собран не этим экраном: выборка в нём не описана'

// Файл, про который спрашиваем подтверждение. Удаление необратимо, но
// дёшево: отчёт пересобирается той же кнопкой. Поэтому обычная модалка
// с двумя выходами, а не диалог с вводом слова — тот в системе занят
// перезаписью базы, где терять нечего было бы уже навсегда.
const кУдалению = ref(null)
const удаляется = ref('')

function спроситьОбУдалении(file) {
  кУдалению.value = file
}

async function удалить() {
  const file = кУдалению.value
  if (!file) return

  кУдалению.value = null
  удаляется.value = file.name
  try {
    await reports.remove(file.name)
    await list.load()
    toast.success('Отчёт удалён', file.name)
  } catch (e) {
    // Файла уже нет — это не отказ: список просто отстал от папки.
    if (e.status === 404) {
      await list.load()
      toast.progress('Файла уже нет', 'Список обновлён')
      return
    }
    // Остальное объясняет сервер словами: «занят другой программой»
    // подсказывает следующий шаг, код ошибки — нет.
    toast.error('Файл не удалён', e.detail || e.message || 'Причина неизвестна')
  } finally {
    удаляется.value = ''
  }
}

function download(name) {
  const link = document.createElement('a')
  link.href = reports.downloadUrl(name)
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}
</script>

<template>
  <section class="rep">
    <header class="rep__head">
      <div class="rep__titles">
        <h1>Отчёты</h1>
        <p class="rep__meta">
          Отчёт — снимок выборки на дату сбора. Он не обновляется вслед за базой:
          файл, отправленный коллеге, останется таким, каким вы его собрали.
        </p>
      </div>
      <BvButton
        variant="primary"
        :loading="building"
        :disabled="базаПуста || пустойСрез"
        @click="build"
      >
        Собрать отчёт
      </BvButton>
    </header>

    <BvCard title="Что попадёт в файл">
      <template #actions>
        <RouterLink class="rep__link" :to="{ path: '/vacancies', query: параметрыСреза }">
          Изменить срез
        </RouterLink>
      </template>

      <p class="rep__slice">
        {{ состав.data.value?.срез ?? 'Считаем выборку…' }}
      </p>
      <p class="rep__note">
        {{ срезЗадан
          ? 'Срез пришёл из фильтров раздела «Вакансии». Он же напечатается на титульном листе.'
          : 'Фильтры не заданы — в файл пойдёт вся база. Настроить срез можно в разделе «Вакансии».' }}
      </p>

      <ul v-if="листы.length" class="rep__sheets">
        <li v-for="лист in листы" :key="лист.имя" class="rep__sheet" :class="{ 'is-off': лист.выключен }">
          <span class="rep__sheet-name">{{ лист.имя }}</span>
          <span class="rep__sheet-rows">{{ лист.объём }}</span>
          <span class="rep__sheet-note">{{ лист.пояснение }}</span>
        </li>
      </ul>

      <!-- Выключенный лист не просто «недоступен»: рядом сказано, чего
           не хватает. -->
      <p v-if="пустойСрез" class="rep__error">
        По этому срезу нет ни одной вакансии — собирать нечего.
        Ослабьте фильтры в разделе «Вакансии».
      </p>
      <p v-else-if="выборкаМала" class="rep__hint rep__hint--warn">
        В срезе {{ состав.data.value?.вакансий }} — медианы по такой выборке не
        показатель рынка. Собрать можно, но для отчёта как документа лучше
        расширить срез.
      </p>
    </BvCard>

    <!-- Пока сборка идёт, это видно и на кнопке, и строкой: кнопка
         говорит «занято», строка — чем именно. -->
    <p v-if="building" class="rep__hint">
      <BvStatus kind="run" label="Собирается" />
      Файл появится в списке, как только будет готов. Обычно это занимает
      несколько секунд.
    </p>
    <!-- Выключенная кнопка без объяснения читается как поломка. -->
    <p v-else-if="базаПуста" class="rep__hint">
      Собирать нечего: в базе нет вакансий. Отчёт строится по собранным
      данным — начните со сбора.
    </p>
    <p v-if="buildError" class="rep__error">{{ buildError }}</p>

    <BvCard title="Готовые файлы">
      <template #actions>
        <BvButton size="md" :loading="list.loading.value" @click="list.load()">Обновить список</BvButton>
      </template>

      <div v-if="list.error.value" class="rep__state">
        <p class="rep__state-title">Список не загружен</p>
        <p class="rep__state-text">{{ list.error.value }}</p>
        <BvButton size="md" :loading="list.loading.value" @click="list.load()">Повторить</BvButton>
      </div>

      <div v-else-if="!list.loading.value && !files.length" class="rep__state">
        <p class="rep__state-title">Отчётов пока нет</p>
        <p class="rep__state-text">
          Соберите первый отчёт — он попадёт в этот список и останется доступным для скачивания.
        </p>
      </div>

      <BvTable v-else label="Готовые отчёты" sticky-first>
        <thead>
          <tr>
            <th>Файл</th>
            <th>Состояние</th>
            <th>Срез</th>
            <th class="col-num">Строк</th>
            <th>Собран</th>
            <th class="col-num">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="file in files" :key="file.name">
            <td class="rep__name">
              <div class="rep__stack">
                <span>{{ file.name }}</span>
                <span class="rep__file-meta">{{ kindOf(file.name) }} · {{ sizeOf(file.size) }}</span>
              </div>
            </td>
            <td class="rep__status">
              <div class="rep__stack">
                <BvStatus :kind="состояние(file).kind" :label="состояние(file).слово" />
                <span v-if="состояние(file).подпись" class="rep__ago">{{ состояние(file).подпись }}</span>
              </div>
            </td>
            <!-- Срез читается из самого файла. Файл, которого продукт не
                 собирал, о себе ничего не говорит — и тут честнее прочерк
                 с пояснением, чем правдоподобная выдумка. -->
            <td class="rep__slice-cell">
              <span v-if="file.slice">{{ file.slice }}</span>
              <span v-else class="rep__unknown" :title="ЧУЖОЙ_ФАЙЛ">—</span>
            </td>
            <td class="col-num">{{ file.vacancies === null || file.vacancies === undefined ? '—' : num(file.vacancies) }}</td>
            <td class="rep__date">
              <div class="rep__stack">
                <span>{{ dateTime(file.created_at) }}</span>
                <span class="rep__ago">{{ timeAgo(file.created_at) }}</span>
              </div>
            </td>
            <td class="col-num">
              <div class="rep__actions">
                <BvButton size="sm" @click="download(file.name)">Скачать</BvButton>
                <BvButton size="sm" variant="quiet" :loading="удаляется === file.name" @click="спроситьОбУдалении(file)">
                  Удалить
                </BvButton>
              </div>
            </td>
          </tr>
        </tbody>
      </BvTable>

      <!-- Правило названо там, где оно действует, и названо целиком:
           кого срок касается и кого нет. -->
      <p class="rep__note">
        Отчёты, собранные здесь, хранятся {{ срокХранения }}
        {{ plural(срокХранения, 'день', 'дня', 'дней') }} и после этого удаляются сами —
        собрать такой же можно заново. Выгрузки и файлы прежних версий срок не
        трогает: их убираете вы. Всего {{ num(files.length) }}
        {{ plural(files.length, 'файл', 'файла', 'файлов') }}.
      </p>
      <p v-if="убранные.length" class="rep__note">
        Убрано по сроку хранения: {{ убранные.join(', ') }}.
      </p>
    </BvCard>

    <!-- Что именно потеряется, названо до удаления: имя файла человеку
         ничего не говорит, а «18 вакансий, поиск «аналитик»» говорит. -->
    <BvModal
      :open="Boolean(кУдалению)"
      title="Удалить отчёт?"
      :subtitle="кУдалению?.name"
      @close="кУдалению = null"
    >
      <p class="rep__confirm">
        Файл удалится с сервера безвозвратно. Собрать такой же можно заново —
        по тем же фильтрам, но по сегодняшней базе, а не по той, что была на
        день сборки.
      </p>
      <p v-if="кУдалению?.slice" class="rep__confirm-slice">
        {{ кУдалению.slice }} · {{ vacanciesCount(кУдалению.vacancies) }}
      </p>

      <template #actions>
        <BvButton variant="quiet" @click="кУдалению = null">Отмена</BvButton>
        <BvButton variant="danger" @click="удалить()">Удалить файл</BvButton>
      </template>
    </BvModal>
  </section>
</template>

<style scoped>
.rep {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.rep__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.rep__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.rep__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.rep__hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
  max-width: none;
}

.rep__error {
  font-size: var(--t-caption-size);
  color: var(--c-status-err-text);
  max-width: none;
}

/* Малая выборка — не ошибка сборки, а состояние данных: собрать можно,
   но числа в файле придётся читать с оговоркой. */
.rep__hint--warn { color: var(--c-negative); }

/* Срез словами — то же предложение, что напечатается на титульном
   листе. Крупнее подписи: с него человек начинает читать экран. */
.rep__slice {
  font-size: var(--t-body-size);
  color: var(--c-text);
}

.rep__note {
  margin-top: var(--s-2);
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.rep__link {
  font-size: var(--t-ui-size);
  color: var(--c-accent);
}

/* Листы файла: имя, объём, пояснение. Сетка, а не таблица — строк
   четыре, и заголовки столбцов заняли бы больше места, чем данные. */
.rep__sheets {
  margin: var(--s-5) 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.rep__sheet {
  display: grid;
  grid-template-columns: 110px 130px 1fr;
  gap: var(--s-3);
  align-items: baseline;
  padding-top: var(--s-3);
  box-shadow: inset 0 1px 0 var(--c-border);
}

.rep__sheet:first-child {
  padding-top: 0;
  box-shadow: none;
}

.rep__sheet-name {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.rep__sheet-rows {
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-secondary);
}

.rep__sheet-note {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

/* Лист, которого в файле не будет: приглушён, но виден вместе с
   причиной. Исчезнувшая строка не объясняет ничего. */
.rep__sheet.is-off .rep__sheet-name,
.rep__sheet.is-off .rep__sheet-rows { color: var(--c-text-muted); }

/* До 768px три колонки не помещаются: имя и объём встают в строку,
   пояснение уходит под них. */
@media (max-width: 767px) {
  .rep__sheet {
    grid-template-columns: 1fr auto;
  }

  .rep__sheet-note { grid-column: 1 / -1; }
}

.rep__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-3);
  text-align: center;
  padding: var(--s-12) var(--s-6);
}

.rep__state-title {
  font-size: var(--t-h3-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.rep__state-text {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-muted);
}

/* Две строки в ячейке. Раскладка — на вложенном блоке, а не на самой
   ячейке: `display: flex` у td вырывает её из строки таблицы, и колонки
   перестают совпадать с шапкой. */
.rep__stack {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.rep__name {
  color: var(--c-text);
  font-weight: var(--w-medium);
  min-width: 240px;
}

/* Тип и размер — вторая строка у имени, а не свои колонки: ширину
   таблицы они забирали наравне со срезом, хотя читаются реже. */
.rep__file-meta {
  font-size: var(--t-caption-size);
  font-weight: var(--w-regular);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-muted);
}

.rep__status { white-space: nowrap; }

.rep__slice-cell {
  min-width: 200px;
  color: var(--c-text-secondary);
}

.rep__unknown {
  color: var(--c-text-muted);
  cursor: help;
}

.rep__actions {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
}

.rep__confirm {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.rep__confirm-slice {
  margin-top: var(--s-3);
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.rep__date { white-space: nowrap; }

.rep__ago {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
}

.rep__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}
</style>
