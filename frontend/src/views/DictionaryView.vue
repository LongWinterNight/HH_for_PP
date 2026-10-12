<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import BvBarList from '@/components/charts/BvBarList.vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvKpiTile from '@/components/ui/BvKpiTile.vue'
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
// Экран собран из примитивов системы; своих компонентов у него нет.

const состояние = useApi((options) => ai.state(options))
const список = useApi((статус, options) => ai.candidates(статус, options))
const toast = useToast()

const СОСТОЯНИЯ = [
  { value: 'new', label: 'Ждут решения' },
  { value: 'confirmed', label: 'В словаре' },
  { value: 'rejected', label: 'Отклонённые' }
]
const статус = ref('new')

const РАЗДЕЛЫ = [
  { value: 'hard', label: 'Профессиональные' },
  { value: 'tools', label: 'Инструменты' },
  { value: 'soft', label: 'Личные' }
]
// Раздел предлагает модель по виду навыка; человек может поправить.
const разделы = ref({})
const занят = ref('')

const кандидаты = computed(() => список.data.value?.['кандидаты'] ?? [])
const сводка = computed(() => список.data.value?.['сводка'] ?? состояние.data.value?.['кандидаты'] ?? null)
const слой = computed(() => состояние.data.value ?? null)

function загрузить() {
  состояние.load()
  список.load(статус.value)
}

watch(статус, (значение) => список.load(значение))
watch(кандидаты, (строки) => {
  for (const строка of строки) if (!(строка['ключ'] in разделы.value)) разделы.value[строка['ключ']] = строка['раздел']
})

onMounted(загрузить)

async function решить(кандидат, решение) {
  занят.value = кандидат['ключ']
  try {
    await ai.decide({ 'ключ': кандидат['ключ'], 'решение': решение, 'раздел': разделы.value[кандидат['ключ']] })
    if (решение === 'confirm') {
      toast.success(`«${кандидат['название']}» в словаре`, 'Следующие вакансии с этим навыком разберёт словарь, без модели')
    } else {
      toast.success(`«${кандидат['название']}» отклонён`, 'Больше предлагаться не будет')
    }
    загрузить()
  } catch (e) {
    toast.error('Решение не записано', e.message || 'Повторите позже', { label: 'Повторить', run: () => решить(кандидат, решение) })
  } finally {
    занят.value = ''
  }
}

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
      <BvKpiTile no-trend label="Перешло в словарь" :value="плитка(сводка?.['подтверждено'])" note="находятся без модели" :loading="список.loading.value && !список.data.value" />
      <BvKpiTile no-trend label="Вакансий разобрано" :value="плитка(слой?.['разобрано'])" :note="слой ? `ещё в очереди ${num(слой['в_очереди'] ?? 0)}` : ''" :loading="состояние.loading.value && !слой" />
      <BvKpiTile no-trend label="Всего кандидатов" :value="плитка(сводка?.['новых'])" note="большинство встретилось один раз" :loading="список.loading.value && !список.data.value" />
    </div>

    <BvCard title="Кандидаты">
      <template #actions>
        <BvSegmented v-model="статус" :options="СОСТОЯНИЯ" label="Состояние кандидатов" />
      </template>

      <p v-if="список.error.value" class="dict__error" role="alert">{{ список.error.value }}</p>
      <p v-else-if="!кандидаты.length" class="dict__note">{{ пусто }}</p>

      <BvTable v-else label="Кандидаты в словарь навыков" sticky-first>
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
              </div>
            </td>
            <td class="col-num">{{ num(кандидат['работодателей']) }}</td>
            <td class="col-num">{{ num(кандидат['встреч']) }}</td>
            <td>
              <!-- Цитаты — основание решения: без них подтверждать пришлось бы вслепую. -->
              <ul class="dict__quotes">
                <li v-for="(цитата, i) in кандидат['цитаты']" :key="i">
                  «{{ цитата['цитата'] }}»
                  <span class="dict__kind">{{ цитата['работодатель'] }}</span>
                </li>
              </ul>
            </td>
            <td v-if="статус === 'new'">
              <div class="dict__section">
                <BvSelect v-model="разделы[кандидат['ключ']]" :options="РАЗДЕЛЫ" label="Раздел словаря" hide-label />
              </div>
            </td>
            <td v-if="статус === 'new'">
              <div class="dict__actions">
                <BvButton size="sm" :loading="занят === кандидат['ключ']" :disabled="Boolean(занят)" @click="решить(кандидат, 'confirm')">В словарь</BvButton>
                <BvButton size="sm" variant="quiet" :disabled="Boolean(занят)" @click="решить(кандидат, 'reject')">Отклонить</BvButton>
              </div>
            </td>
          </tr>
        </tbody>
      </BvTable>

      <p v-if="кандидаты.length && статус === 'new'" class="dict__note">
        Навык из словаря появится у уже собранных вакансий после пересчёта навыков; новые вакансии словарь разберёт сразу.
      </p>
    </BvCard>

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
}

.dict__name-text {
  color: var(--c-text);
  font-weight: var(--w-medium);
  overflow-wrap: break-word;
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

.dict__actions {
  display: flex;
  gap: var(--s-2);
  white-space: nowrap;
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
