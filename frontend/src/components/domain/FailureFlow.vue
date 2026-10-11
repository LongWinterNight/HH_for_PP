<script setup>
import { computed } from 'vue'
import BvStatus from '@/components/ui/BvStatus.vue'
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
const сцена = useScene(ШАГОВ, { пауза: 1100, готово: () => Boolean(props.watchdog) })
const { корень, шаг, идёт } = сцена

defineExpose({ повторить: сцена.повторить, идёт })

const телеграм = computed(() => Boolean(props.watchdog?.['телеграм_настроен']))
const оповещения = computed(() => props.watchdog?.['оповещения'] ?? [])

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
      : 'Канал не настроен: сообщение никуда не уйдёт, и это будет записано в журнал оповещений. Как включить — python scripts/проверить_оповещение.py.',
    kind: телеграм.value ? 'ok' : 'stop',
    метка: телеграм.value ? 'Настроен' : 'Не настроен'
  }
])
</script>

<template>
  <div ref="корень" class="fail">
    <ol class="fail__chain" aria-label="Что происходит при отказе сбора">
      <li
        v-for="(звено, i) in цепочка"
        :key="звено.имя"
        class="fail__link"
        :class="{ 'is-active': шаг === i + 1 && идёт, 'is-reached': шаг >= i + 1, 'is-idle': шаг === 0 }"
      >
        <span class="fail__marker" aria-hidden="true">{{ i + 1 }}</span>
        <div class="fail__body">
          <div class="fail__head">
            <span class="fail__name">{{ звено.имя }}</span>
            <BvStatus :kind="звено.kind" :label="звено.метка" />
          </div>
          <p class="fail__text">{{ звено.текст }}</p>
        </div>
      </li>
    </ol>

    <div class="fail__foot">
      <p class="fail__note">
        Это демонстрация на примере: настоящего отказа нет, сообщение не отправляется.
      </p>
    </div>

    <section class="fail__real" aria-label="Последние оповещения">
      <h3 class="fail__title">Что было на самом деле</h3>
      <p v-if="!оповещения.length" class="fail__note">
        Оповещений ещё не было: с тех пор как они включены, сбор не падал.
      </p>
      <p v-else-if="оповещения.every((запись) => запись['проба'])" class="fail__note">
        Настоящих отказов не было — ниже только проверки канала.
      </p>
      <ul v-else class="fail__alerts">
        <li v-for="(запись, i) in оповещения" :key="i" class="fail__alert">
          <span class="fail__alert-name">{{ запись['заголовок'] }}</span>
          <span class="fail__alert-when" :title="dateTime(запись['когда'])">{{ timeAgo(запись['когда']) }}</span>
          <BvStatus :kind="запись['доставлено'] ? 'ok' : 'stop'" :label="запись['доставлено'] ? 'Доставлено' : 'Не доставлено'" />
        </li>
      </ul>
    </section>

    <section v-if="guard" class="fail__real" aria-label="Защита входа">
      <h3 class="fail__title">Кто может сюда попасть</h3>
      <p class="fail__note">
        <template v-if="guard['вход_по_паролю']">Вход закрыт паролем. </template>
        <template v-else>Пароль на вход не задан — продукт открыт каждому, кто знает адрес. </template>
        После {{ guard['неудач'] }} неудачных попыток за {{ guard['окно_минут'] }} минут адрес закрывается на
        {{ guard['закрыт_минут'] }} минут: перебор пароля упирается в это ограничение, а не в его длину.
      </p>
    </section>
  </div>
</template>

<style scoped>
.fail {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.fail__chain {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--s-4);
}

.fail__link {
  display: flex;
  gap: var(--s-3);
  min-width: 0;
  padding: var(--s-4);
  border-radius: var(--r-lg);
  box-shadow: var(--border);
  transition: opacity var(--dur-panel) var(--ease-standard),
              background-color var(--dur-panel) var(--ease-standard),
              box-shadow var(--dur-panel) var(--ease-standard);
}

/* Во время проигрывания звено, до которого ещё не дошли, приглушено:
   видно, что будет дальше, и видно, что ещё не случилось. До первого
   нажатия цепочка видна целиком. */
.fail__link:not(.is-reached):not(.is-idle) { opacity: 0.4; }

.fail__link.is-active {
  background: var(--c-status-run-bg);
  box-shadow: inset 0 0 0 2px var(--c-status-run-dot);
}

.fail__marker {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--r-pill);
  box-shadow: var(--border-strong);
  font-size: var(--t-caption-size);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-secondary);
}

.fail__body {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.fail__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
}

.fail__name {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.fail__text,
.fail__note {
  font-size: var(--t-caption-size);
  line-height: var(--t-caption-lh);
  color: var(--c-text-secondary);
  max-width: none;
  overflow-wrap: anywhere;
}

.fail__note { color: var(--c-text-muted); }

.fail__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
}

.fail__foot :deep(.btn) { flex: 0 0 auto; }

.fail__real {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding-top: var(--s-5);
  box-shadow: inset 0 1px 0 var(--c-border);
}

.fail__title {
  font-size: var(--t-ui-size);
  font-weight: var(--w-medium);
  color: var(--c-text);
}

.fail__alerts {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
}

.fail__alert {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--s-3);
  min-height: var(--h-control-lg);
  box-shadow: inset 0 -1px 0 var(--c-border);
}

.fail__alert-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--t-ui-size);
  color: var(--c-text);
}

.fail__alert-when {
  font-size: var(--t-caption-size);
  color: var(--c-text-muted);
  white-space: nowrap;
}

@media (max-width: 1199px) {
  .fail__chain { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 767px) {
  .fail__chain { grid-template-columns: minmax(0, 1fr); }
  .fail__foot { flex-direction: column; align-items: flex-start; }
  .fail__alert { grid-template-columns: minmax(0, 1fr) auto; row-gap: 2px; padding: var(--s-2) 0; }
  .fail__alert-when { grid-column: 1; grid-row: 2; }
  .fail__alert > :last-child { grid-column: 2; grid-row: 1 / span 2; }
}

@media (prefers-reduced-motion: reduce) {
  .fail__link { transition: none; }
}
</style>
