import { createApp } from 'vue'
import router from '@/app/router'
import App from '@/App.vue'

// Порядок подключения существенный: шрифты объявляются до токенов,
// токены — до всего остального. Токены содержат и базовые правила
// (типографика, статусы, карточка, печать), поэтому отдельного
// base.css в системе нет: он был бы вторым источником истины.
//
// touch.css идёт последним: он поднимает цели нажатия до 44px там,
// где указатель грубый, и должен переопределять высоты из токенов.
import '@/styles/fonts.css'
import '@/styles/tokens.css'
import '@/styles/touch.css'

createApp(App).use(router).mount('#app')
