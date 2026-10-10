// Клиент API. Адрес всегда относительный: в разработке Vite проксирует
// /api на localhost:8000, в продукте FastAPI раздаёт и статику, и API с
// одного домена. Захардкоженный localhost в старом интерфейсе ломал
// работу везде, кроме машины разработчика.

const BASE = '/api'

/**
 * Ошибка запроса, знающая, что показать человеку. Текст сообщения —
 * не отладочный: он говорит, что делать, а не что произошло внутри.
 */
export class ApiError extends Error {
  constructor(message, { status = 0, detail = '', url = '' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.url = url
  }
}

function humanMessage(status, detail) {
  if (status === 0) return 'Сервер не отвечает. Проверьте, запущено ли приложение, и повторите.'
  if (status === 403) return 'hh.ru отклонил запрос. Проверьте токен и email в настройках сбора.'
  if (status === 404) return 'Данные не найдены. Возможно, сбор ещё не запускался.'
  if (status === 429) return 'Слишком много запросов подряд. Подождите минуту и повторите.'
  if (status >= 500) return 'Приложение не смогло обработать запрос. Данные не потеряны.'
  return detail || 'Запрос не выполнен.'
}

/**
 * GET с параметрами. Пустые значения не отправляются: `area=` в строке
 * запроса бэкенд читает как фильтр по пустому региону.
 */
export async function get(path, params = {}, { signal } = {}) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '' || value === false) continue
    query.set(key, String(value))
  }
  const url = `${BASE}${path}${query.toString() ? `?${query}` : ''}`
  return request(url, { method: 'GET', signal })
}

export async function post(path, body = {}, { signal } = {}) {
  return request(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal
  })
}

/**
 * POST, у которого параметры идут строкой запроса, а не телом.
 * Так устроен запуск сбора: FastAPI объявляет его параметры как Query,
 * и тело он просто не читает. Повторяющиеся значения (несколько
 * запросов сбора) передаются одним ключом несколько раз.
 */
export async function postQuery(path, params = {}, { signal } = {}) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    if (Array.isArray(value)) {
      value.filter(Boolean).forEach((v) => query.append(key, String(v)))
    } else {
      query.set(key, String(value))
    }
  }
  return request(`${BASE}${path}${query.toString() ? `?${query}` : ''}`, { method: 'POST', signal })
}

/**
 * DELETE. Имя файла уходит в путь, а не в тело: адрес ресурса и есть
 * то, что удаляется. Кодирование обязательно — в именах отчётов есть
 * точки и подчёркивания, а у экспортов бывают пробелы.
 */
export async function del(path, { signal } = {}) {
  return request(`${BASE}${path}`, { method: 'DELETE', signal })
}

async function request(url, options) {
  let response
  try {
    response = await fetch(url, options)
  } catch (error) {
    // Прерванный запрос — не ошибка: так экран отменяет устаревшую
    // загрузку при быстром переключении фильтров.
    if (error.name === 'AbortError') throw error
    throw new ApiError(humanMessage(0), { status: 0, url })
  }

  if (!response.ok) {
    let detail = ''
    try {
      const data = await response.json()
      detail = data?.detail || ''
    } catch {
      detail = ''
    }
    throw new ApiError(humanMessage(response.status, detail), {
      status: response.status,
      detail,
      url
    })
  }

  return response.json()
}

/** Адрес файла для скачивания: браузер открывает его сам. */
export function fileUrl(path) {
  return `${BASE}${path}`
}
