<script setup>
import { computed } from 'vue'
import BvBanner from '@/components/ui/BvBanner.vue'
import BvCard from '@/components/ui/BvCard.vue'
import BvStatus from '@/components/ui/BvStatus.vue'
import BvTable from '@/components/ui/BvTable.vue'
import { useScene } from '@/composables/useScene'
import { dateTime, timeAgo } from '@/utils/format'

// Что происходит, когда сбор падает.
//
// Сбор однажды пролежал месяц, и об этом никто не узнал: отказ жил в
// памяти процесса и был виден на одном экране. Теперь у отказа четыре
// следа, и здесь они показаны цепочкой — на примере, без настоящего
// отказа: оповещение при этом не уходит, и об этом сказано прямо.
//
// Под цепочкой — что было на самом деле: последние оповещения и дошли
// ли они.
const props = defineProps({
  // state['надзор'] из /api/system/state.
  watchdog: { type: Object, default: null },
  // story['защита'] из /api/system/story: пороги ограничения входа.
  guard: { type: Object, default: null }
})

const ШАГОВ = 4
// Цепочка проигрывается, когда до неё докрутили; повтор — из шапки главы.
const сцена = useScene(ШАГОВ, { пауза: 900, готово: () => Boolean(props.watchdog) })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const телеграм = computed(() => Boolean(props.watchdog?.['телеграм_настроен']))
const оповещения = computed(() => props.watchdog?.['оповещения'] ?? [])
const толькоПробы = computed(() => оповещения.value.length > 0 && оповещения.value.every((запись) => запись['проба']))

const цепочка = computed(() => [
  {
    имя: 'Сбор упал',
    текст: 'Источник не ответил, истёк ключ доступа или не записались данные. Причина приходит кодом, а не текстом ошибки.',
    kind: 'err',
    метка: 'Отказ'
  },
  {
    имя: 'Журнал на диске',
    текст: `Запись с трассировкой ложится в файл дня. Пароли и токены в нём заменены. Журнал хранится ${props.watchdog?.['хранить_дней'] ?? 30} дней.`,
    kind: props.watchdog?.['журнал_пишется'] ? 'ok' : 'stop',
    метка: props.watchdog?.['журнал_пишется'] ? 'Пишется' : 'Выключен'
  },
  {
    имя: 'Метка в шапке',
    текст: '«Сбор не удался» стоит на каждом экране и ведёт туда, где причина объяснена словами. Исход читается из базы и переживает перезапуск.',
    kind: 'ok',
    метка: 'Работает'
  },
  {
    имя: 'Сообщение в Telegram',
    текст: телеграм.value
      ? 'Уходит сообщение: что случилось, почему и что делать. Дошло оно или нет — записывается.'
      : 'Канал не настроен: сообщение никуда не уйдёт, и это будет записано в журнал оповещений.',
    kind: телеграм.value ? 'ok' : 'stop',
    метка: телеграм.value ? 'Настроен' : 'Не настроен'
  }
])
</script>

<template>
  <div ref="корень" class="st-stack">
    <ol class="fail__chain" aria-label="Что происходит при отказе сбора">
      <li v-for="(звено, i) in цепочка" :key="звено.имя" class="fail__link">
        <!-- До первого проигрывания цепочка видна целиком; во время него
             звено, до которого не дошли, приглушено. -->
        <BvCard tight class="fail__card st-dim" :class="{ 'is-on': шаг === 0 || шаг >= i + 1, 'is-run': шаг === i + 1 && идёт }">
          <div class="fail__head">
            <span class="label">Шаг {{ i + 1 }}</span>
            <BvStatus :kind="звено.kind" :label="звено.метка" />
          </div>
          <h3 class="fail__name">{{ звено.имя }}</h3>
          <p class="st-note">{{ звено.текст }}</p>
        </BvCard>
      </li>
    </ol>

    <p class="st-note">Это демонстрация на примере: настоящего отказа нет, сообщение не отправляется.</p>

    <BvBanner
      v-if="!телеграм"
      kind="info"
      title="Оповещения в Telegram не настроены"
      text="Об отказе сбора сейчас можно узнать только открыв продукт. Как включить канал, подскажет команда python scripts/проверить_оповещение.py."
    />

    <div class="st-grid st-grid--wide st-grid--stretch">
      <BvCard title="Что было на самом деле">
        <template #actions>
          <span class="st-scope">последние оповещения</span>
        </template>
        <p v-if="!оповещения.length" class="st-note">
          Оповещений ещё не было: с тех пор как они включены, сбор не падал.
        </p>
        <template v-else>
          <BvTable label="Последние оповещения">
            <thead>
              <tr>
                <th>Событие</th>
                <th>Когда</th>
                <th>Исход</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(запись, i) in оповещения" :key="i">
                <td>
                  <div class="st-vac">
                    <span class="st-vac__name">{{ запись['заголовок'] }}</span>
                    <span v-if="запись['проба']" class="st-vac__company">проверка канала</span>
                  </div>
                </td>
                <td><span :title="dateTime(запись['когда'])">{{ timeAgo(запись['когда']) }}</span></td>
                <td>
                  <BvStatus :kind="запись['доставлено'] ? 'ok' : 'stop'" :label="запись['доставлено'] ? 'Доставлено' : 'Не доставлено'" />
                </td>
              </tr>
            </tbody>
          </BvTable>
          <p v-if="толькоПробы" class="st-note">Настоящих отказов не было — в таблице только проверки канала.</p>
        </template>
      </BvCard>

      <BvCard v-if="guard" title="Кто может сюда попасть">
        <template #actions>
          <BvStatus :kind="guard['вход_по_паролю'] ? 'ok' : 'stop'" :label="guard['вход_по_паролю'] ? 'Вход по паролю' : 'Пароль не задан'" />
        </template>
        <p class="st-note">
          <template v-if="!guard['вход_по_паролю']">Продукт открыт каждому, кто знает адрес. </template>
          После {{ guard['неудач'] }} неудачных попыток за {{ guard['окно_минут'] }} минут адрес закрывается на
          {{ guard['закрыт_минут'] }} минут: перебор пароля упирается в это ограничение, а не в его длину.
        </p>
      </BvCard>
    </div>
  </div>
</template>

<style scoped>
.fail__chain {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
  gap: var(--gap-grid);
}

.fail__link { display: flex; min-width: 0; }

.fail__card {
  flex: 1 1 auto;
  gap: var(--s-2);
  transition: opacity var(--dur-panel) var(--ease-standard), background-color var(--dur-panel) var(--ease-standard);
}

/* Звено, до которого дошли прямо сейчас, — тем же тоном, что статус «Идёт». */
.fail__card.is-run { background: var(--c-status-run-bg); }

.fail__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
  min-height: var(--h-control-sm);
}

.fail__name {
  font-size: var(--t-ui-size);
  line-height: var(--t-ui-lh);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

@media (prefers-reduced-motion: reduce) {
  .fail__card { transition: none; }
}
</style>
