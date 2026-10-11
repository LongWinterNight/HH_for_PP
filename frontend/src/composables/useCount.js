import { onBeforeUnmount, ref, watch } from 'vue'

/**
 * Число, которое досчитывается до своего значения.
 *
 * Счёт идёт, когда сцена дошла до числа: видно, что оно — итог шага, а
 * не стояло с самого начала. Пока не дошла — null, и на месте числа
 * стоит прочерк того же кегля, как у плитки без данных.
 *
 * Длится 600 мс: дольше появления блока, чтобы последние цифры успели
 * прочесть, и не настолько долго, чтобы числа ждали.
 */
export function useCount(значение, активно, { длительность = 600 } = {}) {
  const показано = ref(null)
  let кадр = null

  const безДвижения = () =>
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  function считать() {
    cancelAnimationFrame(кадр)
    const цель = значение()
    if (!активно() || цель === null || цель === undefined) {
      показано.value = null
      return
    }
    if (безДвижения() || !цель) {
      показано.value = цель
      return
    }
    const от = показано.value ?? 0
    const начало = performance.now()
    const шаг = (сейчас) => {
      const доля = Math.min(1, (сейчас - начало) / длительность)
      // Быстро в начале, медленно к концу.
      показано.value = Math.round(от + (цель - от) * (1 - Math.pow(1 - доля, 3)))
      if (доля < 1) кадр = requestAnimationFrame(шаг)
    }
    кадр = requestAnimationFrame(шаг)
  }

  watch([значение, активно], считать, { immediate: true })
  onBeforeUnmount(() => cancelAnimationFrame(кадр))

  return показано
}
