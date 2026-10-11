import { createRouter, createWebHistory } from 'vue-router'

// Шесть рабочих экранов и один объясняющий. Порядок здесь же задаёт порядок пунктов
// в навигации — второго списка с теми же названиями быть не должно.
// Слово «парсер» в интерфейсе не появляется: раздел называется
// «Сбор данных», маршрут — /collection.
export const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: 'Дашборд' }
  },
  {
    path: '/vacancies',
    name: 'vacancies',
    component: () => import('@/views/VacanciesView.vue'),
    meta: { title: 'Вакансии' }
  },
  {
    path: '/professions',
    name: 'professions',
    component: () => import('@/views/ProfessionsView.vue'),
    meta: { title: 'Профессии' }
  },
  {
    path: '/analytics',
    name: 'analytics',
    component: () => import('@/views/AnalyticsView.vue'),
    meta: { title: 'Аналитика' }
  },
  {
    path: '/collection',
    name: 'collection',
    component: () => import('@/views/CollectionView.vue'),
    meta: { title: 'Сбор данных' }
  },
  {
    path: '/reports',
    name: 'reports',
    component: () => import('@/views/ReportsView.vue'),
    meta: { title: 'Отчёты' }
  },
  {
    // Не рабочий экран, а объясняющий: что происходит в продукте и как
    // устроены сбор, поиск и оповещения. Стоит последним.
    path: '/system',
    name: 'system',
    component: () => import('@/views/SystemView.vue'),
    meta: { title: 'Как устроено' }
  },
  {
    // Служебный экран приёмки: примитивы во всех состояниях.
    // В навигацию не входит — meta.nav: false.
    path: '/styleguide',
    name: 'styleguide',
    component: () => import('@/views/StyleguideView.vue'),
    meta: { title: 'Компоненты', nav: false }
  },
  // Неизвестный адрес возвращает на дашборд: терять пользователя
  // на пустой странице в продукте из шести экранов незачем.
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

/**
 * Куда прокрутить страницу после смены адреса.
 *
 * Прежде ответ был один — в начало, на любую смену адреса. Пока в
 * адресе жил только путь, это было верно. Когда туда переехало
 * состояние экрана (фильтры, страница, открытая вакансия), правило
 * стало ломать работу: клик по строке в середине списка писал в адрес
 * `id` и уносил человека наверх, прочь от строки, по которой он нажал.
 *
 * Четыре случая, и только в двух страница двигается:
 *   «назад» и «вперёд»   — туда, где человек был;
 *   другой экран          — в начало;
 *   другая страница списка — в начало: продолжать чтение с конца нечего;
 *   всё остальное         — на месте. Это панель, фильтр, сортировка.
 */
export function прокрутка(to, from, savedPosition) {
  if (savedPosition) return savedPosition
  if (to.path !== from.path) return { top: 0 }
  if ((to.query.page ?? '') !== (from.query.page ?? '')) return { top: 0 }
  return false
}

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: прокрутка
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · BaseVacancy` : 'BaseVacancy'
})

export default router
