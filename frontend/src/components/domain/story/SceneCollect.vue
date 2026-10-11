<script setup>
import { computed } from 'vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvKpiTile from '@/components/ui/BvKpiTile.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import BvTable from '@/components/ui/BvTable.vue'
import StoryNumber from '@/components/domain/story/StoryNumber.vue'
import { useCount } from '@/composables/useCount'
import { useScene } from '@/composables/useScene'
import { num } from '@/utils/format'

// Сбор: что принёс каждый запрос последнего запуска.
//
// Таблица запросов устроена как история сборов: строка, статус, числа.
// Запросы проходят по очереди — «Ждёт», «Идёт», «Собран», — и числа
// строки появляются, когда запрос пройден. Самое поучительное видно по
// колонке «Уже в базе»: два написания одного слова приносят почти одно
// и то же.
const props = defineProps({
  // story['сбор'] из /api/system/story.
  data: { type: Object, default: null },
  // Запрос, которым найдена вакансия-пример: её строка помечена.
  heroQuery: { type: String, default: '' }
})

const запросы = computed(() => props.data?.['запросы'] ?? [])
// Шаг на запрос и ещё один — на итог.
const шагов = () => запросы.value.length + 1
const сцена = useScene(шагов, { пауза: 900, готово: () => запросы.value.length > 0 })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const итог = computed(() => шаг.value > запросы.value.length)
const наибольшее = computed(() => Math.max(...запросы.value.map((з) => з['взято']), 1))

function строка(запрос, i) {
  const взято = запрос['взято'] || 0
  const прежних = Math.max(0, взято - запрос['новых'] - запрос['обновлено'])
  const доля = (часть) => `${(часть / наибольшее.value) * 100}%`
  const пройден = шаг.value > i + 1
  return {
    прежних,
    пройден,
    статус: пройден
      ? { kind: 'ok', label: 'Собран' }
      : шаг.value === i + 1
        ? { kind: 'run', label: 'Идёт' }
        : { kind: 'idle', label: 'Ждёт' },
    // Пока запрос не пройден, полоса пуста: её длина — итог запроса.
    части: пройден
      ? [доля(запрос['новых']), доля(запрос['обновлено']), доля(прежних)]
      : ['0%', '0%', '0%']
  }
}

function время(мс) {
  const секунд = Math.round(мс / 1000)
  if (секунд < 60) return `${секунд} с`
  return `${Math.floor(секунд / 60)} мин ${String(секунд % 60).padStart(2, '0')} с`
}

const ПОЛЯ = { name: 'названии', description: 'описании', company_name: 'названии компании' }
const гдеИщется = computed(() =>
  (props.data?.['поля_поиска'] ?? []).map((поле) => ПОЛЯ[поле] ?? поле).join(' и ')
)

const взято = useCount(() => props.data?.['взято'], () => итог.value)
const новых = useCount(() => props.data?.['новых'], () => итог.value)
const обновлено = useCount(() => props.data?.['обновлено'], () => итог.value)
const плитка = (значение) => (значение === null ? null : num(значение))
</script>

<template>
  <div ref="корень" class="st-stack">
    <p v-if="!запросы.length" class="st-note">Сбор ещё не запускался — показать нечего.</p>

    <template v-else>
      <BvCard :title="`Запросы сбора №${data['номер']}`">
        <template #actions>
          <span class="st-scope">ищем в {{ гдеИщется }} вакансии</span>
        </template>

        <BvTable label="Запросы последнего сбора" sticky-first>
          <thead>
            <tr>
              <th>Запрос</th>
              <th>Состояние</th>
              <th class="col-num">Страниц</th>
              <th class="col-num">Взято</th>
              <th class="col-num">Новых</th>
              <th class="col-num">Обновлено</th>
              <th class="col-num">Уже в базе</th>
              <th>Состав взятого</th>
              <th class="col-num">Время</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(запрос, i) in запросы" :key="запрос['запрос']" :class="{ 'is-run': шаг === i + 1 && идёт }">
              <td>
                <div class="st-vac st-vac--short">
                  <span class="st-vac__name">{{ запрос['запрос'] }}</span>
                  <span v-if="запрос['запрос'] === heroQuery" class="st-vac__company">отсюда вакансия-пример</span>
                </div>
              </td>
              <td><BvStatus :kind="строка(запрос, i).статус.kind" :label="строка(запрос, i).статус.label" /></td>
              <td class="col-num">{{ запрос['страниц'] }}</td>
              <td class="col-num"><StoryNumber :value="запрос['взято']" :active="строка(запрос, i).пройден" /></td>
              <td class="col-num"><StoryNumber :value="запрос['новых']" :active="строка(запрос, i).пройден" /></td>
              <td class="col-num"><StoryNumber :value="запрос['обновлено']" :active="строка(запрос, i).пройден" /></td>
              <td class="col-num"><StoryNumber :value="строка(запрос, i).прежних" :active="строка(запрос, i).пройден" /></td>
              <td>
                <!-- Длина полосы — доля от самого большого запроса. -->
                <div class="collect__mix" aria-hidden="true">
                  <span class="collect__part collect__part--new" :style="{ width: строка(запрос, i).части[0] }"></span>
                  <span class="collect__part collect__part--upd" :style="{ width: строка(запрос, i).части[1] }"></span>
                  <span class="collect__part collect__part--old" :style="{ width: строка(запрос, i).части[2] }"></span>
                </div>
              </td>
              <td class="col-num">
                {{ запрос['из_памяти'] ? 'из памяти' : время(запрос['мс']) }}
              </td>
            </tr>
          </tbody>
        </BvTable>

        <ul class="collect__legend" aria-hidden="true">
          <li><span class="collect__key collect__part--new"></span>новые</li>
          <li><span class="collect__key collect__part--upd"></span>обновлённые</li>
          <li><span class="collect__key collect__part--old"></span>уже были в базе</li>
        </ul>

        <p class="st-note">
          Вакансия, найденная двумя запросами, записывается один раз — поэтому у второго написания того же слова
          новых почти нет.
        </p>
      </BvCard>

      <div class="st-grid st-grid--kpi" aria-live="polite">
        <BvKpiTile no-trend label="Взято вакансий" :value="плитка(взято)" :note="`со ${data['страниц']} страниц выдачи`" />
        <BvKpiTile no-trend label="Новых" :value="плитка(новых)" note="раньше в базе не было" />
        <BvKpiTile no-trend label="Обновлено" :value="плитка(обновлено)" note="изменились с прошлого сбора" />
        <BvKpiTile no-trend label="Длительность" :value="итог ? время(data['мс']) : null" note="на все запросы" />
      </div>
    </template>
  </div>
</template>

<style scoped>
/* Запрос, который идёт сейчас, — тем же тоном, что статус «Идёт». */
:deep(tbody tr.is-run),
:deep(tbody tr.is-run:hover) { background: var(--c-status-run-bg); }
:deep(tbody tr) { transition: background-color var(--dur-panel) var(--ease-standard); }

/* Составная полоса строки: ступени шкалы величин, как у «Долей целого». */
.collect__mix {
  display: flex;
  width: 100%;
  min-width: 120px;
  height: var(--s-2);
  border-radius: var(--r-pill);
  overflow: hidden;
  background: var(--track-bar);
}

.collect__part {
  flex: 0 0 auto;
  height: 100%;
  transition: width var(--dur-enter) var(--ease-enter);
}

.collect__part--new { background: var(--c-data-1); }
.collect__part--upd { background: var(--c-data-2); }
.collect__part--old { background: var(--c-data-4); box-shadow: var(--bar-hairline); }

.collect__legend {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2) var(--s-5);
  font-size: var(--t-caption-size);
  color: var(--c-text-secondary);
}

.collect__legend li {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
}

.collect__key {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

@media (prefers-reduced-motion: reduce) {
  :deep(tbody tr),
  .collect__part { transition: none; }
}
</style>
