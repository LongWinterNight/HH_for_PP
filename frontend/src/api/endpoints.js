import { del, fileUrl, get, post, postQuery } from '@/api/client'

// Все обращения к бэкенду одним списком, сгруппированные по разделам.
// Экран не составляет адреса сам: иначе один и тот же вызов появляется
// в трёх местах с разными параметрами по умолчанию, и поведение
// расходится незаметно.

// Состояние базы для шапки: сколько вакансий и когда собирали. Отдельно
// от dashboard.summary — тот считает спарклайны и топ навыков, а шапка
// стоит на всех шести экранах.
export const overview = {
  get: (options) => get('/overview', {}, options)
}

// Экран «Как устроено»: живое состояние систем и поиск по шагам.
export const system = {
  state: (options) => get('/system/state', {}, options),
  // Данные глав: вакансия-пример и то, что система делает с ней на каждом шаге.
  story: (options) => get('/system/story', {}, options),
  // Тот же поиск, что на «Вакансиях», с выдачей промежуточного: разбор
  // запроса, два списка и их слияние.
  explain: (q, options) => get('/search/explain', { q }, options)
}

// Слой понимания текста: что нашла модель и что с этим решил человек.
export const ai = {
  state: (options) => get('/ai/state', {}, options),
  candidates: (status, options) => get('/ai/candidates', { status }, options),
  decide: (body, options) => post('/ai/candidates/decide', body, options)
}

export const dashboard = {
  summary: (options) => get('/dashboard', {}, options)
}

export const analytics = {
  kpi: (params, options) => get('/analytics/kpi', params, options),
  topSkills: (params, options) => get('/analytics/top-skills', params, options),
  advanced: (params, options) => get('/analytics/advanced', params, options),
  distribution: (params, options) => get('/analytics/distribution', params, options),
  // Прирост базы по месяцам: считается по дате первой встречи, а не по
  // дате публикации, — см. комментарий у эндпоинта.
  newByMonth: (params, options) => get('/analytics/new-by-month', params, options),
  export: (body, options) => post('/export/analytics', body, options)
}

export const vacancies = {
  list: (params, options) => get('/vacancies', params, options),
  // Эндпоинт отдаёт CSV по умолчанию и XLSX по параметру. Формат
  // указывается явно: кнопка называет расширение, и оно должно
  // совпадать с тем, что скачается.
  exportUrl: (format = 'xlsx') => fileUrl(`/export/vacancies?format=${format}`)
}

export const professions = {
  list: (params, options) => get('/professions/list', params, options),
  detail: (key, options) => get(`/professions/detail/${encodeURIComponent(key)}`, {}, options),
  vacancies: (params, options) => get('/professions/vacancies', params, options)
}

// Раздел называется «Сбор данных»: слово «парсер» в интерфейсе не
// появляется. Адреса бэкенда остаются прежними — переименование API
// сломало бы старый интерфейс, который пока работает параллельно.
export const collection = {
  status: (options) => get('/parser/status', {}, options),
  // Параметры уходят строкой запроса: эндпоинт объявляет их как Query.
  start: (params, options) => postQuery('/parser/start', params, options),
  stop: (options) => get('/parser/stop', {}, options),
  lastRun: (options) => get('/parser/last-run', {}, options),
  // Проверка доступа к источнику: один лёгкий запрос вместо целого сбора.
  check: (options) => get('/parser/check', {}, options),
  history: (options) => get('/parser/history', {}, options),
  // Расписание сбора и то, держится ли оно.
  schedule: (options) => get('/schedule', {}, options),
  // Чего не хватает в базе и какие запросы это закрыли бы.
  suggestions: (options) => get('/collection/suggestions', {}, options),
  decideSuggestion: (body, options) => post('/collection/suggestions/decide', body, options),
  // Во что обойдётся сбор. Считает сервер: цена зависит от его настроек
  // — паузы между запросами и того, включена ли резка на срезы.
  estimate: (params, options) => get('/parser/estimate', params, options),
  cacheStats: (options) => get('/parser/cache/stats', {}, options),
  clearCache: (options) => post('/parser/cache/clear', {}, options)
}

export const reports = {
  list: (options) => get('/reports/list', {}, options),
  // Что попадёт в файл: считается до сборки, теми же фильтрами.
  preview: (params, options) => get('/reports/preview', params, options),
  // Фильтры уходят строкой запроса: отчёт собирается по той же
  // выборке, что показывает список, и теми же параметрами.
  generate: (params, options) => postQuery('/reports/generate', params, options),
  // Сборка идёт в фоне, и её итог узнаётся отдельным запросом: ответ на
  // запуск говорит только о том, что она началась.
  status: (options) => get('/reports/status', {}, options),
  downloadUrl: (filename) => fileUrl(`/reports/download/${encodeURIComponent(filename)}`),
  // Удаление: папка отчётов копится, и проверочный файл на восемнадцать
  // вакансий лежит в ней рядом с тем, что отправили заказчику.
  remove: (filename, options) => del(`/reports/${encodeURIComponent(filename)}`, options)
}

export const settings = {
  app: (options) => get('/app/settings', {}, options),
  // Настройки сбора: почта для запросов и пауза между ними.
  collection: (options) => get('/settings/collection', {}, options),
  saveCollection: (body, options) => post('/settings/collection', body, options),
  email: (options) => get('/user/email', {}, options),
  saveEmail: (body, options) => post('/user/email', body, options)
}

export const suggest = {
  vacancies: (params, options) => get('/autocomplete/vacancies', params, options),
  areas: (params, options) => get('/autocomplete/areas', params, options),
  skills: (params, options) => get('/autocomplete/skills', params, options)
}
