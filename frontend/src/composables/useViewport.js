import { onBeforeUnmount, ref } from 'vue'

/**
 * Режим ширины окна: узкий, средний, широкий.
 *
 * Пороги те же, что в спеке адаптивности, — 768 и 1024. Значение
 * считается по matchMedia, а не по обработчику resize: браузер сам
 * сообщает о пересечении порога, и на каждый пиксель перетаскивания
 * окна перерисовки не происходит.
 *
 * Это не замена медиазапросам. Всё, что решается на CSS, решается на
 * CSS; сюда попадает только то, что меняет состав разметки: три пункта
 * в шапке против шести — это разные списки, а не другой отступ.
 */

const ПОРОГИ = {
  средний: '(min-width: 768px) and (max-width: 1023.98px)',
  широкий: '(min-width: 1024px)',
}

export function useViewport() {
  const режим = ref(определить())

  const слушатели = Object.entries(ПОРОГИ).map(([, запрос]) => {
    const наблюдение = window.matchMedia(запрос)
    const обновить = () => { режим.value = определить() }
    наблюдение.addEventListener('change', обновить)
    return () => наблюдение.removeEventListener('change', обновить)
  })

  onBeforeUnmount(() => слушатели.forEach((отписаться) => отписаться()))

  return { режим }
}

function определить() {
  if (window.matchMedia(ПОРОГИ.широкий).matches) return 'широкий'
  if (window.matchMedia(ПОРОГИ.средний).matches) return 'средний'
  return 'узкий'
}
