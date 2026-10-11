<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import FailureFlow from '@/components/domain/FailureFlow.vue'
import SearchExplainer from '@/components/domain/SearchExplainer.vue'
import SystemPipeline from '@/components/domain/SystemPipeline.vue'
import { system } from '@/api/endpoints'
import { useApi } from '@/composables/useApi'
import { timeAgo } from '@/utils/format'

// «Как устроено»: что происходит в продукте и как работают его системы.
//
// Не рабочий экран, а объясняющий. Три вопроса, на которые раньше
// отвечал только код: какой путь проходит вакансия, почему поиск нашёл
// именно это и что будет, если сбор упадёт. На каждый — схема с
// живыми числами: они приходят с сервера, а не нарисованы.
//
// Правило экрана — движение означает событие. Поток по схеме идёт,
// пока идёт сбор; объясняющие анимации проигрываются один раз по
// действию. Бесконечных анимаций в системе нет, и здесь тоже.

const состояние = useApi((options) => system.state(options))

// Пока идёт сбор, числа меняются каждую минуту — экран спрашивает их
// снова. В покое опроса нет: спрашивать раз в три секунды то, что
// меняется раз в сутки, незачем.
const ПАУЗА_ПРИ_СБОРЕ = 4000
let таймер = null

const идётСбор = computed(() => Boolean(состояние.data.value?.['сбор']?.['идёт']))

function опросить() {
  остановитьОпрос()
  if (!идётСбор.value) return
  таймер = setTimeout(async () => {
    await состояние.load()
    опросить()
  }, ПАУЗА_ПРИ_СБОРЕ)
}

function остановитьОпрос() {
  if (таймер) clearTimeout(таймер)
  таймер = null
}

watch(идётСбор, опросить)

// Человек вернулся на вкладку — числа могли уйти вперёд.
function приВозврате() {
  if (document.visibilityState === 'visible') состояние.load()
}

onMounted(() => {
  состояние.load()
  document.addEventListener('visibilitychange', приВозврате)
})

onBeforeUnmount(() => {
  остановитьОпрос()
  document.removeEventListener('visibilitychange', приВозврате)
})

const сбор = computed(() => состояние.data.value?.['сбор'] ?? null)
const поиск = computed(() => состояние.data.value?.['поиск'] ?? null)

// Одна строка под заголовком: что система делает прямо сейчас.
const сейчас = computed(() => {
  if (состояние.loading.value && !состояние.data.value) return 'Спрашиваем состояние систем…'
  if (!состояние.data.value) return ''
  // Слова «идёт сбор» говорит метка рядом; повторять их текстом незачем.
  if (идётСбор.value) return 'Числа на схеме обновляются сами.'
  const последний = сбор.value?.['последний']
  if (!последний) return 'Сбор ещё не запускался — схема показывает пустую систему.'
  const когда = последний['завершён'] || последний['начат']
  const исход = { completed: 'прошёл', error: 'не удался', interrupted: 'был оборван', stopped: 'остановлен' }[последний['исход']] ?? последний['исход']
  return `Система в покое. Последний сбор ${исход} ${timeAgo(когда)}.`
})

// Состояние поиска по смыслу — меткой: поднята ли модель.
const смысл = computed(() => {
  const п = поиск.value
  if (!п) return null
  if (!п['смысл_включён']) return { kind: 'stop', label: 'Смысл выключен' }
  if (п['модель_поднята']) return { kind: 'ok', label: `Модель ${п['модель']} поднята` }
  if (п['отказ_модели']) return { kind: 'stop', label: 'Модель недоступна — только слова' }
  return { kind: 'idle', label: 'Модель поднимется при первом поиске' }
})
</script>

<template>
  <section class="sys">
    <header class="sys__head">
      <div class="sys__titles">
        <h1>Как устроено</h1>
        <p class="sys__meta">
          Что происходит с вакансией от источника до списка, почему поиск находит именно это
          и что будет, если сбор упадёт. Числа на схемах — живые.
        </p>
        <p v-if="сейчас" class="sys__now" aria-live="polite">
          <BvStatus v-if="идётСбор" kind="run" label="Идёт сбор" />
          {{ сейчас }}
        </p>
      </div>
      <BvButton :loading="состояние.loading.value" @click="состояние.load()">Обновить числа</BvButton>
    </header>

    <div v-if="состояние.error.value && !состояние.data.value" class="sys__state">
      <p class="sys__state-title">Состояние систем не получено</p>
      <p class="sys__state-text">{{ состояние.error.value }}</p>
      <BvButton :loading="состояние.loading.value" @click="состояние.load()">Повторить</BvButton>
    </div>

    <template v-else>
      <BvCard title="Путь вакансии">
        <SystemPipeline :state="состояние.data.value" :loading="состояние.loading.value" />
      </BvCard>

      <BvCard title="Как работает поиск">
        <template v-if="смысл" #actions>
          <BvStatus :kind="смысл.kind" :label="смысл.label" />
        </template>
        <p class="sys__lead">
          Поиск идёт двумя способами сразу. Слова ловят точные названия — «Corona», «1С», — которые модель
          смысла размывает. Смысл ловит синонимы и перефразы, которых в тексте буквально нет. Списки
          сливаются по местам.
        </p>
        <SearchExplainer :measure="состояние.data.value?.['замер'] ?? null" />
      </BvCard>

      <BvCard title="Если сбор упадёт">
        <FailureFlow :watchdog="состояние.data.value?.['надзор'] ?? null" />
      </BvCard>
    </template>
  </section>
</template>

<style scoped>
.sys {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

.sys__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
}

.sys__titles {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

.sys__meta {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
}

.sys__now {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-muted);
  max-width: none;
}

.sys__lead {
  margin-bottom: var(--s-5);
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-secondary);
  max-width: 78ch;
}

.sys__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-3);
  text-align: center;
  padding: var(--s-12) var(--s-6);
}

.sys__state-title {
  font-size: var(--t-h3-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.sys__state-text {
  font-size: var(--t-body-size);
  line-height: var(--t-body-lh);
  color: var(--c-text-muted);
}
</style>
