<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import BvAutocomplete from '@/components/ui/BvAutocomplete.vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvField from '@/components/ui/BvField.vue'
import BvKpiTile from '@/components/ui/BvKpiTile.vue'
import BvMenuItem from '@/components/ui/BvMenuItem.vue'
import BvModal from '@/components/ui/BvModal.vue'
import BvPagination from '@/components/ui/BvPagination.vue'
import BvSegmented from '@/components/ui/BvSegmented.vue'
import BvSelect from '@/components/ui/BvSelect.vue'
import BvTable from '@/components/ui/BvTable.vue'
import { ai } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { num, plural } from '@/utils/format'

// Словарь навыков: что нашла модель и чего словарь ещё не знает.
//
// Модель читает тексты вакансий и находит навыки, которых нет в
// словаре. Такой навык не идёт в аналитику — он копится кандидатом.
// Когда его назвали три разных работодателя, он показывается здесь
// вместе с цитатами, из которых получен: решение принимается не
// вслепую. Подтверждённый навык уходит в словарь и дальше находится
// обычным кодом, без модели.
//
// Решений три, а не два. «В словарь» и «Отклонить» не решают один навык
// в нескольких написаниях: «ИИ», «AI» и «ИИ-инструменты» — сотни
// вакансий, разбитые на три кандидата. Третье решение — «Это другое
// написание»: кандидат становится написанием навыка словаря или другого
// кандидата, и его вакансии считаются вместе с ним. Рядом с кандидатом
// экран сам подсказывает похожие названия.
//
// Кандидатов на всей базе тысячи, поэтому список ищется и листается.
//
// Экран собран из примитивов системы; своих компонентов у него нет.

const состояние = useApi((options) => ai.state(options))
const список = useApi((параметры, options) => ai.candidates(параметры, options))
const toast = useToast()

const СОСТОЯНИЯ = [
  { value: 'new', label: 'Ждут решения' },
  { value: 'confirmed', label: 'В словаре' },
  { value: 'rejected', label: 'Отклонённые' }
]
const статус = ref('new')
const поиск = ref('')
const страница = ref(1)
const наСтранице = ref(25)

const РАЗДЕЛЫ = [
  { value: 'hard', label: 'Профессиональные' },
  { value: 'tools', label: 'Инструменты' },
  { value: 'soft', label: 'Личные' }
]
// Раздел предлагает модель по виду навыка; человек может поправить.
const разделы = ref({})
const занят = ref('')

const кандидаты = computed(() => список.data.value?.['кандидаты'] ?? [])
const всего = computed(() => список.data.value?.['всего'] ?? 0)
const сводка = computed(() => список.data.value?.['сводка'] ?? состояние.data.value?.['кандидаты'] ?? null)
const слой = computed(() => состояние.data.value ?? null)

function загрузитьСписок() {
  список.load({
    status: статус.value,
    q: поиск.value.trim(),
    limit: наСтранице.value,
    offset: (страница.value - 1) * наСтранице.value
  })
}

function загрузить() {
  состояние.load()
  загрузитьСписок()
}

watch(статус, () => { страница.value = 1; загрузитьСписок() })
watch([страница, наСтранице], загрузитьСписок)

// Поиск ждёт, пока человек допишет: запрос на каждую букву спорил бы с ним.
let таймер = null
watch(поиск, () => {
  clearTimeout(таймер)
  таймер = setTimeout(() => { страница.value = 1; загрузитьСписок() }, 300)
})

watch(кандидаты, (строки) => {
  for (const строка of строки) if (!(строка['ключ'] in разделы.value)) разделы.value[строка['ключ']] = строка['раздел']
})

onMounted(загрузить)

async function решить(кандидат, решение, цель = null) {
  занят.value = кандидат['ключ']
  try {
    await ai.decide({ 'ключ': кандидат['ключ'], 'решение': решение, 'раздел': разделы.value[кандидат['ключ']], 'цель': цель?.['значение'] })
    if (решение === 'confirm') {
      toast.success(`«${кандидат['название']}» в словаре`, 'Следующие вакансии с этим навыком разберёт словарь, без модели')
    } else if (решение === 'reject') {
      toast.success(`«${кандидат['название']}» отклонён`, 'Больше предлагаться не будет')
    } else if (решение === 'synonym') {
      toast.success(`«${кандидат['название']}» — написание «${цель['название']}»`, 'Дальше словарь найдёт его как этот навык')
    } else {
      toast.success(`«${кандидат['название']}» слит с «${цель['название']}»`, 'Их вакансии теперь считаются вместе')
    }
    загрузить()
    return true
  } catch (e) {
    toast.error('Решение не записано', e.message || 'Повторите позже', { label: 'Повторить', run: () => решить(кандидат, решение, цель) })
    return false
  } finally {
    занят.value = ''
  }
}

// Окно «Это другое написание»: выбор цели — из подсказок или из словаря.
const написаниеДля = ref(null)
const выбор = ref(null)
const поискНавыка = ref('')

function открытьНаписание(кандидат, предвыбор = null) {
  написаниеДля.value = кандидат
  поискНавыка.value = ''
  выбор.value = предвыбор ? цельИз(предвыбор) : null
}

function закрытьНаписание() {
  написаниеДля.value = null
  выбор.value = null
}

// Подсказка — навык словаря или другой кандидат; от этого зависит решение.
function цельИз(подсказка) {
  return подсказка['откуда'] === 'словарь'
    ? { решение: 'synonym', значение: подсказка['название'], название: подсказка['название'] }
    : { решение: 'merge', значение: подсказка['ключ'], название: подсказка['название'] }
}

function выбранаЛи(подсказка) {
  const ц = цельИз(подсказка)
  return выбор.value?.['решение'] === ц['решение'] && выбор.value?.['значение'] === ц['значение']
}

async function подсказатьНавык(запрос) {
  const ответ = await ai.dictionary(запрос)
  return ответ?.suggestions ?? []
}

function выбратьНавык(пункт) {
  выбор.value = { решение: 'synonym', значение: пункт.value, название: пункт.label }
}

async function записатьНаписание() {
  const кандидат = написаниеДля.value
  const цель = выбор.value
  if (!кандидат || !цель) return
  if (await решить(кандидат, цель['решение'], цель)) закрытьНаписание()
}

const подписьПодсказки = (подсказка) => (
  подсказка['откуда'] === 'словарь'
    ? 'в словаре'
    : `кандидат · ${num(подсказка['работодателей'] ?? 0)} ${plural(подсказка['работодателей'] ?? 0, 'работодатель', 'работодателя', 'работодателей')}`
)

const плитка = (значение) => (значение === null || значение === undefined ? null : num(значение))

// Замеры извлечения: полнота и точность по режимам, от словаря к модели.
const ПОРЯДОК = { 'словарь': 0, 'модель': 1, 'вместе': 2 }
const замеры = computed(() =>
  Object.values(слой.value?.['замеры'] ?? {}).sort((а, б) => (ПОРЯДОК[а['режим']] ?? 9) - (ПОРЯДОК[б['режим']] ?? 9))
)
const подписьЗамера = (замер) => (замер['режим'] === 'словарь' ? 'словарь' : `${замер['режим']} · ${(замер['версия'] || '').split(':')[0]}`)
const полнота = computed(() => замеры.value.map((замер) => ({ label: подписьЗамера(замер), value: замер['полнота'] })))
const точность = computed(() => замеры.value.map((замер) => ({ label: подписьЗамера(замер), value: замер['точность'] })))
const проценты = (значение) => `${String(значение).replace('.', ',')} %`

const пусто = computed(() => {
  if (поиск.value.trim()) return `Кандидатов с «${поиск.value.trim()}» в названии нет.`
  if (статус.value === 'confirmed') return 'Из кандидатов в словарь пока ничего не перешло.'
  if (статус.value === 'rejected') return 'Отклонённых кандидатов нет.'
  if (!слой.value) return ''
  if (!слой.value['разобрано']) return 'Модель ещё не разбирала вакансии — кандидатов нет.'
  const новых = сводка.value?.['новых'] ?? 0
  return новых
    ? `Накоплено ${новых} ${plural(новых, 'кандидат', 'кандидата', 'кандидатов')}, но ни одного ещё не назвали три разных работодателя.`
    : 'Всё найденное моделью словарь уже знает.'
})
</script>

<template>
  <section class="dict">
    <header class="dict__head">
      <div class="dict__titles">
        <h1>Словарь навыков</h1>
        <p class="dict__meta">
          Навыки, которые модель нашла в текстах вакансий и которых словарь ещё не знает.
          Подтверждённый навык дальше находится без модели.
        </p>
      </div>
      <BvButton :loading="состояние.loading.value || список.loading.value" @click="загрузить()">Обновить</BvButton>
    </header>

    <BvBanner
      v-if="слой && !слой['включён']"
      kind="info"
      title="Слой понимания текста выключен"
      text="Модель не разбирает новые вакансии, а её находки не показываются в карточках. Накопленные кандидаты остаются здесь. Включается слой настройкой AI_LAYER=1."
    />

    <div class="dict__kpi">
      <BvKpiTile no-trend label="Ждут решения" :value="плитка(сводка?.['ждут_решения'])" :note="слой ? `назвали ${слой['порог_работодателей']} работодателя и больше` : ''" :loading="список.loading.value && !список.data.value" />
      <BvKpiTile no-trend label="Перешло в словарь" :value="плитка(сводка?.['подтверждено'])" :note="сводка?.['слито'] ? `ещё ${num(сводка['слито'])} слито как написания` : 'находятся без модели'" :loading="список.loading.value && !список.data.value" />
      <BvKpiTile no-trend label="Вакансий разобрано" :value="плитка(слой?.['разобрано'])" :note="слой ? `ещё в очереди ${num(слой['в_очереди'] ?? 0)}` : ''" :loading="состояние.loading.value && !слой" />
      <BvKpiTile no-trend label="Всего кандидатов" :value="плитка(сводка?.['новых'])" note="большинство встретилось один раз" :loading="список.loading.value && !список.data.value" />
    </div>

    <BvCard title="Кандидаты">
      <!-- Переключатель — в теле карточки, рядом с поиском: в шапке он не
           сжимался и на телефоне выдвигал страницу вбок. -->
      <div class="dict__tools">
        <BvSegmented v-model="статус" :options="СОСТОЯНИЯ" label="Состояние кандидатов" />
        <BvField v-model="поиск" label="Найти кандидата" placeholder="Название или написание" />
        <p v-if="список.data.value" class="dict__note">{{ num(всего) }} {{ plural(всего, 'кандидат', 'кандидата', 'кандидатов') }}</p>
      </div>

      <p v-if="список.error.value" class="dict__error" role="alert">{{ список.error.value }}</p>
      <p v-else-if="!кандидаты.length" class="dict__note">{{ пусто }}</p>

      <div v-else class="dict__list">
      <BvTable label="Кандидаты в словарь навыков" sticky-first>
        <thead>
          <tr>
            <th>Навык</th>
            <th class="col-num">Работодателей</th>
            <th class="col-num">Вакансий</th>
            <th>Как написано в вакансиях</th>
            <th v-if="статус === 'new'">Раздел словаря</th>
            <th v-if="статус === 'new'">Решение</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="кандидат in кандидаты" :key="кандидат['ключ']">
            <td>
              <div class="dict__name">
                <span class="dict__name-text">{{ кандидат['название'] }}</span>
                <span class="dict__kind">{{ кандидат['вид'] }}</span>
                <span v-if="кандидат['написания']?.length" class="dict__kind">
                  ещё пишут: {{ кандидат['написания'].join(', ') }}
                </span>
                <span v-if="кандидат['цель']" class="dict__kind">написание навыка «{{ кандидат['цель'] }}»</span>
                <!-- Подсказка рядом с кандидатом: похожее название в словаре или
                     среди кандидатов. Нажатие открывает решение с этой целью. -->
                <div v-if="статус === 'new' && кандидат['похожие']?.length" class="dict__similar">
                  <span class="dict__kind">похоже на:</span>
                  <div class="dict__similar-list">
                    <BvButton
                      v-for="подсказка in кандидат['похожие'].slice(0, 3)"
                      :key="подсказка['ключ']"
                      size="sm"
                      variant="quiet"
                      :disabled="Boolean(занят)"
                      @click="открытьНаписание(кандидат, подсказка)"
                    >{{ подсказка['название'] }}</BvButton>
                  </div>
                </div>
              </div>
            </td>
            <td class="col-num" data-label="Работодателей">{{ num(кандидат['работодателей']) }}</td>
            <td class="col-num" data-label="Вакансий">{{ num(кандидат['встреч']) }}</td>
            <td data-label="Как написано в вакансиях">
              <!-- Цитаты — основание решения: без них подтверждать пришлось бы вслепую. -->
              <ul class="dict__quotes">
                <li v-for="(цитата, i) in кандидат['цитаты']" :key="i">
                  «{{ цитата['цитата'] }}»
                  <span class="dict__kind">{{ цитата['работодатель'] }}</span>
                </li>
              </ul>
            </td>
            <td v-if="статус === 'new'" data-label="Раздел словаря">
              <div class="dict__section">
                <BvSelect v-model="разделы[кандидат['ключ']]" :options="РАЗДЕЛЫ" label="Раздел словаря" hide-label />
              </div>
            </td>
            <td v-if="статус === 'new'" class="dict__decide">
              <div class="dict__actions">
                <BvButton size="sm" :loading="занят === кандидат['ключ']" :disabled="Boolean(занят)" @click="решить(кандидат, 'confirm')">В словарь</BvButton>
                <BvButton size="sm" variant="secondary" :disabled="Boolean(занят)" aria-haspopup="dialog" @click="открытьНаписание(кандидат)">Другое написание…</BvButton>
                <BvButton size="sm" variant="quiet" :disabled="Boolean(занят)" @click="решить(кандидат, 'reject')">Отклонить</BvButton>
              </div>
            </td>
          </tr>
        </tbody>
      </BvTable>
      </div>

      <BvPagination
        v-if="всего > наСтранице"
        :page="страница"
        :per-page="наСтранице"
        :total="всего"
        @update:page="страница = $event"
        @update:per-page="наСтранице = $event; страница = 1"
      />

      <p v-if="кандидаты.length && статус === 'new'" class="dict__note">
        Навык из словаря появится у уже собранных вакансий после пересчёта навыков; новые вакансии словарь разберёт сразу.
      </p>
    </BvCard>

    <BvModal
      :open="Boolean(написаниеДля)"
      :title="написаниеДля ? `Чьё написание «${написаниеДля['название']}»?` : ''"
      subtitle="Вакансии кандидата будут считаться вместе с выбранным навыком"
      @close="закрытьНаписание"
    >
      <section v-if="написаниеДля?.['похожие']?.length" class="dict__choice">
        <h3 class="label">Похожие названия</h3>
        <div class="dict__choice-list" role="listbox" aria-label="Похожие названия">
          <BvMenuItem
            v-for="подсказка in написаниеДля['похожие']"
            :key="подсказка['ключ']"
            :selected="выбранаЛи(подсказка)"
            :hint="подписьПодсказки(подсказка)"
            @click="выбор = цельИз(подсказка)"
          >{{ подсказка['название'] }}</BvMenuItem>
        </div>
      </section>

      <BvAutocomplete
        v-model="поискНавыка"
        label="Или найдите навык словаря"
        placeholder="Название навыка"
        :suggest="подсказатьНавык"
        @select="выбратьНавык"
      />

      <p class="dict__note">
        <template v-if="выбор?.['решение'] === 'synonym'">
          «{{ написаниеДля?.['название'] }}» станет написанием навыка словаря «{{ выбор['название'] }}» и дальше будет находиться как он.
        </template>
        <template v-else-if="выбор?.['решение'] === 'merge'">
          «{{ написаниеДля?.['название'] }}» сольётся с кандидатом «{{ выбор['название'] }}»: вакансии сложатся, а в словарь они уйдут вместе, когда вы решите судьбу «{{ выбор['название'] }}».
        </template>
        <template v-else>Выберите навык из похожих или найдите его в словаре.</template>
      </p>

      <template #actions>
        <BvButton variant="quiet" @click="закрытьНаписание">Отмена</BvButton>
        <BvButton :disabled="!выбор" :loading="Boolean(занят)" @click="записатьНаписание">Записать</BvButton>
      </template>
    </BvModal>

    <BvCard v-if="замеры.length" title="Насколько точно извлекаются навыки">
      <template #actions>
        <span class="dict__scope">эталон: {{ замеры[0]['вакансий'] }} вакансий, размеченных руками</span>
      </template>
      <div class="dict__measure">
        <section>
          <h3 class="label">Полнота — какую долю настоящих навыков нашли</h3>
          <BvBarList :items="полнота" :format="проценты" />
        </section>
        <section>
          <h3 class="label">Точность — какая доля найденного оказалась навыком</h3>
          <BvBarList :items="точность" :format="проценты" />
        </section>
      </div>
      <p class="dict__note">
        Одна метрика без другой ничего не значит: лишние находки тоже прибавляют полноту. Навык засчитывается при
        точном совпадении названия с разметкой, поэтому обе цифры — нижняя граница.
      </p>
    </BvCard>
  </section>
</template>

<style scoped>
.dict {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.dict__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.dict__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.dict__meta { color: var(--c-text-secondary); }

.dict__kpi {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
  gap: var(--gap-grid);
}

.dict__tools {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-3);
  margin-bottom: var(--s-4);
}

.dict__tools > * { min-width: 0; max-width: 100%; }
.dict__tools > .field { flex: 0 1 360px; }

.dict__note,
.dict__scope,
.dict__kind {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
}

.dict__note { max-width: 78ch; }

.dict__error {
  font-size: var(--t-caption-size);
  color: var(--c-status-err-text);
}

/* Раскладка внутри ячейки — отдельным блоком: саму ячейку таблицы
   раскладывать нельзя, она выпадает из колонки. */
.dict__name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 160px;
  max-width: 280px;
}

.dict__name-text {
  color: var(--c-text);
  font-weight: var(--w-medium);
  overflow-wrap: break-word;
}

/* Подсказки переносятся: в одну строку три названия распирали бы колонку.
   Подпись — своей строкой, а кнопки сдвинуты на свой внутренний отступ,
   чтобы их текст стоял ровно под текстом навыка. */
.dict__similar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  margin-top: var(--s-1);
}

.dict__similar-list {
  display: flex;
  flex-wrap: wrap;
  max-width: calc(100% + 10px);
  margin-left: -10px;
}

/* Длинная подсказка («Ответственность, организованность и
   стрессоустойчивость») обрезается: кнопка не переносит текст и иначе
   распирала бы колонку. Полное название — в окне выбора. */
.dict__similar-list :deep(.btn) {
  max-width: 100%;
  overflow: hidden;
}

.dict__similar-list :deep(.btn__label) {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dict__quotes {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 240px;
  max-width: 460px;
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
}

.dict__section { min-width: 170px; }

/* Решения столбиком: в ряд три кнопки не помещались, «Отклонить»
   уходила за край, и у таблицы появлялась своя прокрутка вбок. Строка
   и так высокая из-за цитат — высота её не растёт. */
.dict__actions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--s-1);
  white-space: nowrap;
}

.dict__choice {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.dict__choice-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Узкий список: строка кандидата становится карточкой. Шесть колонок с
   цитатами и тремя решениями не помещаются уже на планшете, и у таблицы
   появлялась своя прокрутка вбок. Подписи колонок переезжают к значениям,
   решения — в ряд под цитатами. Меряется ширина списка, а не экрана. */
.dict__list { container: dictlist / inline-size; min-width: 0; }

@container dictlist (max-width: 900px) {
  .dict__list :deep(.table-wrap) { overflow: visible; }
  .dict__list :deep(table),
  .dict__list :deep(tbody),
  .dict__list :deep(tr),
  .dict__list :deep(td) { display: block; width: auto; }
  .dict__list :deep(thead) { display: none; }

  .dict__list :deep(tr) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--s-3) var(--s-4);
    padding: var(--s-5) 0;
    box-shadow: inset 0 -1px 0 var(--c-border);
  }

  .dict__list :deep(td.col-num) { font-variant-numeric: tabular-nums; }

  /* Липкая первая колонка на карточке не нужна: прокрутки вбок нет.
     Линии и выравнивание цифр — свойства таблицы; в карточке блоки
     разделяет только отступ, а число стоит под своей подписью. */
  .dict__list :deep(.table td),
  .dict__list :deep(.table tr td) {
    position: static;
    padding: 0;
    border: 0;
    box-shadow: none;
    background: transparent;
    text-align: left;
  }

  .dict__list :deep(td:first-child),
  .dict__list :deep(td[data-label="Как написано в вакансиях"]),
  .dict__list :deep(td[data-label="Раздел словаря"]),
  .dict__list :deep(td.dict__decide) { grid-column: 1 / -1; }

  .dict__list :deep(td[data-label])::before {
    content: attr(data-label);
    display: block;
    font-size: var(--t-caption-size);
    color: var(--c-text-muted);
  }

  .dict__name,
  .dict__quotes,
  .dict__section { min-width: 0; max-width: none; }

  .dict__actions { flex-direction: row; flex-wrap: wrap; }
}

.dict__measure {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr));
  gap: var(--s-6);
}

.dict__measure section {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
}
</style>
