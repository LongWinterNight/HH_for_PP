<script setup>
import AppShell from '@/app/AppShell.vue'
import AppToasts from '@/app/AppToasts.vue'
</script>

<template>
  <AppShell>
    <RouterView />
  </AppShell>

  <!-- Слой уведомлений живёт над всеми экранами: сбор может закончиться,
       пока пользователь смотрит другой раздел. -->
  <AppToasts />
</template>
