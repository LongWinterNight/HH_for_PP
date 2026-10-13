import {
  Chart,
  BarController,
  BarElement,
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Filler
} from 'chart.js'
import { num, plural } from '@/utils/format'

// Единственное место, где графики получают цвет, шрифт и поведение.
// Библиотека приходит со своей палитрой и своими подписями; настроить
// её один раз в теме дешевле, чем спорить с ней на каждом графике.
//
// Цвета не выписаны литералами, а читаются из tokens.css: слот остаётся
// единственным источником истины, и смена токена меняет все графики.
//
// Кольцевые диаграммы не регистрируются намеренно. Угол сектора люди
// сравнивают хуже длины, а порядок рядов в кольце не читается вовсе:
// доли целого показывает составная полоса, категории — горизонтальные.
// Попытка построить кольцо упрётся в отсутствие контроллера — это
// дешевле, чем обнаружить его на проде.

let registered = false

/** Значение токена из tokens.css. */
export function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Палитра величин: три ступени, светлота растёт монотонно. */
export function dataScale() {
  return [token('--c-data-1'), token('--c-data-2'), token('--c-data-3')]
}

/** Маркер: одно значение на график — медиана, текущий период, выбранный ряд. */
export function markerColor() {
  return token('--c-marker')
}

/**
 * Вид ряда по его номеру — для графика с несколькими линиями и для
 * подписей рядов рядом с ним: цвет в двух местах обязан совпадать.
 *
 * Рядов четыре, ступеней шкалы, различимых линией на белом, три.
 * Четвёртый ряд берёт среднюю ступень и отличается формой — штрихом:
 * светлейшая ступень линией почти не видна, а чужого цвета в графиках
 * величин быть не должно.
 */
export function seriesStyle(index) {
  const ступени = [token('--c-data-1'), token('--c-data-2'), token('--c-data-3')]
  return index < 3
    ? { color: ступени[index], dash: [] }
    : { color: ступени[1], dash: [6, 4] }
}

/** Цвет токена с прозрачностью — для заливки вилки под линией. */
export function withAlpha(color, alpha) {
  const hex = color.trim()
  if (/^#[0-9a-f]{6}$/i.test(hex)) {
    const доля = Math.round(alpha * 255).toString(16).padStart(2, '0')
    return `${hex}${доля}`
  }
  return hex
}

/**
 * Штриховка для незакрытого периода. Цвет один и тот же, различает
 * форма: полоса в клетку читается как «ещё не всё» и в чёрно-белой
 * печати тоже.
 */
export function markerHatch(ctx) {
  if (!ctx) return token('--c-marker')

  const canvas = document.createElement('canvas')
  canvas.width = 6
  canvas.height = 6
  const c = canvas.getContext('2d')
  c.fillStyle = token('--c-marker-subtle') || token('--c-marker')
  c.fillRect(0, 0, 6, 6)
  c.strokeStyle = token('--c-marker')
  c.lineWidth = 3
  c.beginPath()
  c.moveTo(-3, 3)
  c.lineTo(3, -3)
  c.moveTo(0, 6)
  c.lineTo(6, 0)
  c.stroke()

  // Если движок не отдал паттерн, столбец остаётся сплошным маркером:
  // пометка периода важнее способа заливки.
  return ctx.createPattern(canvas, 'repeat') || token('--c-marker')
}

/**
 * Тема применяется один раз за жизнь страницы. Дальше графики просто
 * наследуют её: локальные переопределения цвета — дефект обзора кода.
 */
export function setupCharts() {
  if (registered) return
  registered = true

  Chart.register(
    BarController, BarElement,
    LineController, LineElement, PointElement,
    CategoryScale, LinearScale,
    Tooltip,
    // Заливка между двумя линиями: вилка вокруг медианы.
    Filler
  )

  const sans = token('--font-sans')
  const mono = token('--font-mono')

  // Подписи осей и легенд — интерфейсный текст, поэтому основной шрифт.
  // Моно остаётся числам: ось состоит из чисел одной длины, и там
  // выравнивание по разрядам важнее читаемости слова.
  Chart.defaults.font.family = sans
  Chart.defaults.font.size = 12
  Chart.defaults.font.weight = 500
  Chart.defaults.color = token('--c-text-muted')
  Chart.defaults.backgroundColor = token('--c-data-2')
  Chart.defaults.borderColor = token('--c-border')
  Chart.defaults.maintainAspectRatio = false

  // Появление короткое и отключаемое. Бесконечных анимаций у графиков нет.
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  Chart.defaults.animation = reduced ? false : { duration: 160, easing: 'easeOutQuart' }

  // Цвета не анимируются. Дело не во вкусе: столбец незакрытого периода
  // залит штриховкой, то есть CanvasPattern, а не цветом. Chart.js
  // пытается его интерполировать и падает — в Firefox это ронял весь
  // график с «this._fn is not a function». Анимация размеров остаётся.
  Chart.defaults.animations.colors = false

  // Плагин легенды не регистрируется вовсе, поэтому и отключать её
  // нечего: ряды подписаны рядом с данными, а не сноской сбоку.
  // Обращение к Chart.defaults.plugins.legend здесь упало бы — этой
  // ветки defaults не существует, пока плагин не зарегистрирован.
  Chart.defaults.plugins.tooltip.backgroundColor = token('--c-text')
  Chart.defaults.plugins.tooltip.titleFont = { family: sans, size: 13, weight: 500 }
  Chart.defaults.plugins.tooltip.bodyFont = { family: mono, size: 11 }
  Chart.defaults.plugins.tooltip.padding = 10
  Chart.defaults.plugins.tooltip.cornerRadius = 8
  Chart.defaults.plugins.tooltip.displayColors = false

  return Chart
}

/**
 * Оси и сетка. Горизонтальных линий четыре: вертикальные спорят со
 * столбцами. Нулевая линия темнее остальных — она граница, а не деление.
 */
export function baseScales({ unit = '', mono = true } = {}) {
  return {
    x: {
      grid: { display: false },
      border: { color: token('--c-border-strong') },
      ticks: {
        font: { family: mono ? token('--font-mono') : token('--font-sans'), size: 10 },
        color: token('--c-text-muted'),
        maxRotation: 0,
        autoSkipPadding: 12
      }
    },
    y: {
      beginAtZero: true,
      border: { display: false },
      grid: {
        color: token('--c-border'),
        drawTicks: false
      },
      ticks: {
        count: 5,
        padding: 8,
        font: { family: token('--font-mono'), size: 10 },
        color: token('--c-text-muted'),
        callback: (value) => (unit ? `${num(value)} ${unit}` : num(value))
      }
    }
  }
}

/**
 * Тултип показывает период, значение и объём выборки. Медиана по трём
 * вакансиям и по восьмидесяти — разные по надёжности числа, и это
 * видно только вместе с n.
 *
 * Объём выборки берётся из dataset.samples по индексу точки: держать
 * его рядом со значением надёжнее, чем собирать из внешнего состояния.
 */
export function tooltipWithSample({ formatValue = (v) => num(v) } = {}) {
  return {
    callbacks: {
      title: (items) => items[0]?.label ?? '',
      label: (item) => {
        const value = formatValue(item.parsed.y ?? item.parsed)
        const n = item.dataset?.samples?.[item.dataIndex]
        if (n === undefined || n === null) return value
        return [value, `${n} ${plural(n, 'вакансия', 'вакансии', 'вакансий')} в выборке`]
      }
    }
  }
}

export { Chart }
