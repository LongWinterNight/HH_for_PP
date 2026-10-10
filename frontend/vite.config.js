import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Логин и пароль бэкенда подставляются в прокси разработки.
 *
 * Без них первый же вызов /api возвращает 401, и Chrome показывает
 * системное окно входа. Оно не часть продукта: страница под ним стоит,
 * данные не грузятся, а проверка вёрстки упирается в модальное окно
 * браузера, которое со стороны страницы не закрыть.
 *
 * На собранную версию это не влияет — там FastAPI раздаёт файлы сам и
 * проверяет доступ как обычно.
 */
function заголовокВхода() {
  try {
    const env = readFileSync(fileURLToPath(new URL('../.env', import.meta.url)), 'utf-8')
    const значение = (ключ) => {
      const строка = env.split('\n').find((s) => s.trim().startsWith(ключ + '='))
      return строка ? строка.slice(строка.indexOf('=') + 1).trim() : ''
    }
    const user = значение('BASIC_AUTH_USER')
    const password = значение('BASIC_AUTH_PASSWORD')
    if (!user || !password) return undefined
    return { Authorization: `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}` }
  } catch {
    return undefined
  }
}

// Сборка кладётся в frontend/dist, откуда её раздаёт FastAPI.
// В разработке Vite держит свой сервер, а вызовы /api проксирует
// на бэкенд: адрес API в коде всегда относительный, и один и тот же
// код работает и на localhost, и в контейнере.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // Порт бэкенда переопределяется переменной: 8000 бывает занят
        // другим запуском того же продукта, а иногда и осиротевшим
        // сокетом, который Windows держит после убитого процесса.
        target: process.env.BV_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        headers: заголовокВхода()
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Шрифты и графики весят прилично, но это не повод дробить сборку
    // до состояния, когда экран собирается из десятка запросов.
    chunkSizeWarningLimit: 900
  }
})
