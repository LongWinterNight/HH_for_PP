<script setup>
import { ref } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvIconButton from '@/components/ui/BvIconButton.vue'
import BvField from '@/components/ui/BvField.vue'
import BvChip from '@/components/ui/BvChip.vue'
import BvMenu from '@/components/ui/BvMenu.vue'
import BvMenuItem from '@/components/ui/BvMenuItem.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import BvTable from '@/components/ui/BvTable.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvChartFrame from '@/components/charts/BvChartFrame.vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvStackedBar from '@/components/charts/BvStackedBar.vue'
import BvColumnChart from '@/components/charts/BvColumnChart.vue'
import BvLineChart from '@/components/charts/BvLineChart.vue'

// Служебный экран: все примитивы системы во всех состояниях на одной
// странице. Он не входит в навигацию продукта и существует ради приёмки —
// по чек-листу каждое состояние должно быть собрано и проверено, а не
// найдено случайно на одном из шести экранов.

const empty = ref('')
const email = ref('analyst@company.ru')
const wrongEmail = ref('analyst.company.ru')
const delay = ref('250')

const statuses = [
  { kind: 'idle', label: 'Не запущен' },
  { kind: 'run', label: 'Сбор идёт' },
  { kind: 'ok', label: 'Завершено' },
  { kind: 'err', label: 'Ошибка 403' },
  { kind: 'stop', label: 'Остановлен' }
]

const nb = (s) => s.replace(/ /g, ' ')

const currencies = [
  { code: 'RUB', min: '40 000', median: '170 000', max: '600 000', n: 462 },
  { code: 'USD', min: '1 200', median: '2 800', max: '9 000', n: 38 },
  { code: 'KZT', min: '180 000', median: '404 500', max: '1 200 000', n: 61 },
  { code: 'KGS', min: '35 000', median: '65 350', max: '150 000', n: 5 }
].map((c) => ({ ...c, min: nb(c.min), median: nb(c.median), max: nb(c.max) }))

const regions = [
  { label: 'Москва', value: 412 },
  { label: 'Санкт-Петербург', value: 271 },
  { label: 'Ташкент', value: 140 },
  { label: 'Алматы', value: 86 },
  { label: 'Астана', value: 61 },
  { label: 'Прочие', value: 39 }
]

const experience = [
  { label: 'От 3 до 6 лет', value: 412 },
  { label: 'От 1 года до 3 лет', value: 271 },
  { label: 'Более 6 лет', value: 140 },
  { label: 'Нет опыта', value: 86 }
]

const months = ['окт', 'ноя', 'дек', 'янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен']
const monthValues = [62, 74, 48, 91, 83, 104, 97, 112, 88, 76, 57, 17]

const medianMonths = ['окт', 'ноя', 'дек', 'янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг']
const medianValues = [142000, 148000, 151000, 156000, 149000, 162000, 168000, 168000, 171000, 165000, 170000]
const medianSamples = [31, 38, 27, 44, 41, 52, 47, 47, 39, 34, 28]
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h1>Компоненты</h1>
      <p>Примитивы системы во всех состояниях. Экран служебный: в навигацию продукта не входит и нужен для приёмки.</p>
    </header>

    <BvCard title="Кнопки">
      <div class="row">
        <BvButton variant="primary">Запустить сбор</BvButton>
        <BvButton variant="secondary">Экспорт XLSX</BvButton>
        <BvButton variant="quiet">Все вакансии →</BvButton>
        <BvButton variant="danger">Перезаписать базу</BvButton>
        <BvButton variant="primary" disabled>Запустить сбор</BvButton>
        <!-- Кнопка в работе. У главной знак занятости стоит рядом с текстом:
             место под него держит min-width. У второстепенной запаса нет, её
             ширина равна тексту, поэтому знак встаёт поверх — иначе кнопка
             прыгала бы под курсором ровно в момент нажатия. -->
        <BvButton variant="primary" loading>Собираем…</BvButton>
        <BvButton variant="secondary" loading>Экспорт XLSX</BvButton>
        <BvIconButton label="Обновить данные">↻</BvIconButton>
      </div>
      <div class="row">
        <BvButton variant="primary" size="md">Применить</BvButton>
        <BvButton variant="secondary" size="md">Сбросить</BvButton>
        <BvButton variant="secondary" size="sm">Собрать по этой профессии</BvButton>
        <BvIconButton label="Открыть вакансию" size="sm">↗</BvIconButton>
      </div>
      <p class="note">Высоты 40 / 32 / 28, радиус 8. Синяя кнопка на экране одна — та, ради которой пришли.</p>
    </BvCard>

    <BvCard title="Поле ввода · семь состояний">
      <div class="grid">
        <BvField v-model="empty" label="Email" required placeholder="you@company.ru"
                 hint="Плейсхолдер показывает форму ответа, а не повторяет подпись." />
        <BvField v-model="email" label="Email" required placeholder="you@company.ru"
                 hint="Значение читается тёмной ступенью — это данные, а не подсказка." />
        <BvField v-model="wrongEmail" label="Email" required state="error"
                 message="Не хватает символа @ — hh.ru отклонит такой заголовок." />
        <BvField v-model="email" label="Email" required state="checked"
                 message="Связь с hh.ru подтверждена: ответ 200 за 340 мс." />
        <BvField v-model="delay" label="Пауза между запросами" suffix="мс"
                 hint="Меньше 200 мс — риск ошибки 429." />
        <BvField v-model="delay" label="Пауза между запросами" suffix="мс" disabled
                 hint="Недоступно, пока идёт сбор — параметр читается при запуске." />
        <BvField model-value="2 000 в сутки" label="Лимит запросов hh.ru" readonly
                 hint="Значение приходит от API и не редактируется — это факт, а не настройка." />
      </div>
      <p class="note">Место под сообщение зарезервировано всегда: появление ошибки не сдвигает форму под курсором. Седьмое состояние — фокус с клавиатуры: обводка 3px по focus-visible, щелчок мышью её не вызывает.</p>
    </BvCard>

    <BvCard title="Статусы">
      <div class="row">
        <BvStatus v-for="s in statuses" :key="s.kind" :kind="s.kind" :label="s.label" />
      </div>
      <p class="note">От 1024px — пилюля, ниже — точка и слово. Слово присутствует в обеих подачах. У «завершено» подложки нет ни на одной ширине.</p>
    </BvCard>

    <BvCard title="Чипы">
      <div class="row">
        <BvChip>FastAPI</BvChip>
        <BvChip>PostgreSQL</BvChip>
        <BvChip variant="count">+12</BvChip>
        <BvChip variant="filter" removable remove-label="Убрать фильтр по региону">Москва</BvChip>
      </div>
      <p class="note">Пастель означает категорию и всегда идёт с текстовой меткой: в ч/б оттенки сливаются.</p>
    </BvCard>

    <BvCard title="Меню · действия над объектом">
      <div class="row">
        <BvMenu label="Действия" title="Вакансия 4471120">
          <BvMenuItem href="https://hh.ru" hint="↗">Открыть на hh.ru</BvMenuItem>
          <BvMenuItem hint="16">Все вакансии компании</BvMenuItem>
          <BvMenuItem hotkey="⌘C">Копировать ID</BvMenuItem>
          <hr />
          <BvMenuItem danger>Скрыть из выборки</BvMenuItem>
        </BvMenu>

        <BvMenu label="Формат отчёта" title="Формат отчёта">
          <BvMenuItem selected>XLSX</BvMenuItem>
          <BvMenuItem>CSV</BvMenuItem>
          <BvMenuItem>PDF</BvMenuItem>
          <BvMenuItem disabled>JSON — недоступен для этой выборки</BvMenuItem>
        </BvMenu>

        <BvMenu label="Ещё" :count="3" placement="top" align="end" title="Разделы">
          <BvMenuItem>Аналитика</BvMenuItem>
          <BvMenuItem>Сбор данных</BvMenuItem>
          <BvMenuItem>Отчёты</BvMenuItem>
        </BvMenu>
      </div>
      <p class="note">Слева меню действий, в середине выбор значения: выбранный пункт помечен подложкой и полосой, как в автокомплите. Разрушительное действие всегда внизу и отделено линией. Справа от подписи стоит что-то одно — число, горячая клавиша или отметка выбора: пункт с двумя значками перестаёт читаться за один взгляд. Недоступный пункт остаётся видимым — «JSON недоступен для этой выборки» объясняет больше, чем исчезнувшая строка.</p>
      <p class="note">Закрытие — Esc, нажатие вне, выбор пункта; фокус возвращается на кнопку, стрелки ходят по списку, стрелка вниз открывает закрытое меню. До 768px список становится нижним листом с ручкой и затемнением: дропдаун у верхнего края на телефоне недосягаем большим пальцем.</p>
    </BvCard>

    <BvCard title="Таблица · зарплаты по валютам">
      <BvTable label="Зарплаты по валютам">
        <thead>
          <tr>
            <th>Валюта</th>
            <th class="col-num">Мин</th>
            <th class="col-num">Медиана</th>
            <th class="col-num">Макс</th>
            <th class="col-num">N</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in currencies" :key="c.code">
            <td><span class="mono-num">{{ c.code }}</span></td>
            <td class="col-num">{{ c.min }}</td>
            <td class="col-num">{{ c.median }}</td>
            <td class="col-num">{{ c.max }}</td>
            <td class="col-num">{{ c.n }}</td>
          </tr>
        </tbody>
      </BvTable>
      <p class="note">Валюты не складываются и не пересчитываются: курс на дату сбора неизвестен. Рядом с каждым агрегатом стоит объём выборки.</p>
    </BvCard>

    <div class="charts">
      <BvChartFrame title="Вакансии по регионам" :sample="909" :height="220">
        <BvBarList :items="regions" :total="909" />
      </BvChartFrame>

      <BvChartFrame title="Требуемый опыт" :sample="909" :height="220">
        <BvStackedBar :items="experience" />
      </BvChartFrame>

      <BvChartFrame title="Новых вакансий в месяц" subtitle="окт 2025 — сен 2026" :sample="909">
        <BvColumnChart :labels="months" :values="monthValues" label="Новых вакансий по месяцам" open-last />
      </BvChartFrame>

      <BvChartFrame title="Медиана зарплаты · RUB" subtitle="только с указанной зарплатой" :sample="462">
        <BvLineChart :labels="medianMonths" :values="medianValues" :samples="medianSamples"
                     label="Медиана зарплаты по месяцам" />
      </BvChartFrame>

      <BvChartFrame title="Загрузка" subtitle="каркас держит высоту" loading :height="180" />

      <BvChartFrame title="Нет данных" subtitle="выборка меньше пяти" :sample="3" :height="180" />

      <BvChartFrame title="Мало данных" subtitle="значение с оговоркой" :sample="6" :height="180">
        <BvBarList :items="[{ label: 'Москва', value: 3 }, { label: 'Алматы', value: 2 }, { label: 'Прочие', value: 1 }]" :total="6" />
      </BvChartFrame>

      <BvChartFrame title="Ошибка построения" error="Запрос к базе прервался. Данные не потеряны." :height="180" />
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: var(--s-8);
}

.page__head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-3);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr));
  gap: var(--s-4) var(--s-6);
}

.charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr));
  gap: var(--gap-grid);
}

.note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}
</style>
