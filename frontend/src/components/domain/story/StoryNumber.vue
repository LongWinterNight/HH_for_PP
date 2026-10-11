<script setup>
import { useCount } from '@/composables/useCount'
import { num } from '@/utils/format'

// Число внутри текста или ячейки, которое досчитывается до значения.
// Пока сцена до него не дошла — прочерк: так же система показывает
// величину, которой ещё нет.
const props = defineProps({
  value: { type: Number, default: 0 },
  active: { type: Boolean, default: true },
  format: { type: Function, default: null }
})

const показано = useCount(() => props.value, () => props.active)
</script>

<template>
  <span class="num">{{ показано === null ? '—' : (format ? format(показано) : num(показано)) }}</span>
</template>
