<script setup>
// Колонтитул печати: строка, которая повторяется на каждом листе.
//
// Файл уходит из продукта и живёт без него: его открывают люди, которые
// экрана не видели. Без периода, фильтров и даты сбора числа на бумаге
// нечем подтвердить — это требование блока E дизайн-системы, и до сих
// пор оно было выполнено только наполовину: стиль `.print-meta` в
// токенах существовал, а разметки с ним не было ни на одном экране.
//
// На экране компонент невидим: правило `.print-meta { display: none }`
// стоит в токенах до блока @media print, поэтому на бумаге его
// перекрывает печатное правило, а на экране действует скрытие.
import { computed } from 'vue'
import { dateTime } from '@/utils/format'

const props = defineProps({
  // Что показано на экране: «1 411 вакансий», «462 с указанной зарплатой».
  slice: { type: String, default: '' },
  // Условия выборки: период, фильтры.
  filters: { type: String, default: '' },
  // Когда собраны данные.
  collectedAt: { type: String, default: '' }
})

// Дата печати ставится в момент открытия страницы, а не при печати:
// точность до минуты здесь не нужна, а получатель должен видеть, когда
// лист сделан.
const printedAt = dateTime(new Date())

const строка = computed(() => {
  const части = ['BASEVACANCY']
  if (props.slice) части.push(props.slice)
  if (props.filters) части.push(props.filters)
  if (props.collectedAt) части.push(`собрано ${dateTime(props.collectedAt)}`)
  части.push(`напечатано ${printedAt}`)
  return части.join(' · ')
})
</script>

<template>
  <div class="print-meta">{{ строка }}</div>
</template>
