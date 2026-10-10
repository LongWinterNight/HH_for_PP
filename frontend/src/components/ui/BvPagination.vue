<script setup>
import { computed } from 'vue'
import BvButton from '@/components/ui/BvButton.vue'
import BvSelect from '@/components/ui/BvSelect.vue'
import { num } from '@/utils/format'

// Пагинация: сколько показано, из скольких, и как перейти дальше.
//
// Номер страницы идёт моно-шрифтом — это служебное число, а не текст.
// Показанный диапазон важнее номера страницы: «21-40 из 684» отвечает
// на вопрос «где я», а «страница 2» — нет.
const props = defineProps({
  page: { type: Number, required: true },
  perPage: { type: Number, required: true },
  total: { type: Number, required: true },
  perPageOptions: {
    type: Array,
    default: () => [
      { value: 20, label: '20 на странице' },
      { value: 50, label: '50 на странице' },
      { value: 100, label: '100 на странице' }
    ]
  }
})

defineEmits(['update:page', 'update:perPage'])

const pages = computed(() => Math.max(1, Math.ceil(props.total / props.perPage)))
const from = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.perPage + 1))
const to = computed(() => Math.min(props.page * props.perPage, props.total))
</script>

<template>
  <div class="pager">
    <span class="pager__range">
      Показано <b>{{ num(from) }} — {{ num(to) }}</b> из {{ num(total) }}
    </span>

    <div class="pager__controls">
      <BvButton size="md" :disabled="page <= 1" @click="$emit('update:page', page - 1)">Назад</BvButton>
      <span class="pager__page mono-num">СТР. {{ page }} / {{ pages }}</span>
      <BvButton size="md" :disabled="page >= pages" @click="$emit('update:page', page + 1)">Вперёд</BvButton>
      <BvSelect
        :model-value="perPage"
        label="Строк на странице"
        hide-label
        :options="perPageOptions"
        @update:model-value="$emit('update:perPage', Number($event))"
      />
    </div>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  font-size: var(--t-ui-size);
  color: var(--c-text-secondary);
}

.pager__range b {
  color: var(--c-text);
  font-weight: var(--w-medium);
  font-variant-numeric: tabular-nums;
}

.pager__controls {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex-wrap: wrap;
}

.pager__page { white-space: nowrap; }
</style>
