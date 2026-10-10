// Правила достоверности данных. Двенадцать правил дизайн-системы
// касаются не вида, а того, можно ли верить числу на экране; нарушение
// не заметно глазом и потому опасно. Здесь собраны те из них, которые
// выражаются кодом, — чтобы каждый экран не решал их заново.

/**
 * Ниже этого объёма выборки агрегат не показывается вовсе: медиана по
 * трём вакансиям выглядит как факт и читается как факт, не значив ничего.
 */
export const MIN_SAMPLE = 5

/**
 * От MIN_SAMPLE до этого значения число показывается, но с оговоркой.
 * Порог рабочий: дизайн-система приводит пример с шестью вакансиями и
 * пометкой «выводы ненадёжны», но границу не называет. Если появится
 * основание — менять здесь, а не в компонентах.
 */
export const WEAK_SAMPLE = 10

/**
 * Порог окраски тренда. Отклонение меньше порога отмечается стрелкой и
 * весом, но не цветом: восемь цветных бейджей подряд превращают дашборд
 * в светофор, где не выделено ничего.
 */
export const TREND_THRESHOLD = 10

/**
 * Состояние выборки: показывать значение, показывать с оговоркой или
 * не показывать вовсе.
 */
export function sampleState(n) {
  if (!n || n < MIN_SAMPLE) return 'insufficient'
  if (n < WEAK_SAMPLE) return 'weak'
  return 'ok'
}

export function hasEnoughData(n) {
  return sampleState(n) !== 'insufficient'
}

/**
 * Как подписать объём выборки рядом с агрегатом. Без n читатель не может
 * оценить надёжность и вынужден доверять на слово.
 */
export function sampleNote(n) {
  const state = sampleState(n)
  if (state === 'insufficient') return `мало данных: ${n || 0} из ${MIN_SAMPLE} нужных`
  if (state === 'weak') return `${n} вакансий — выводы ненадёжны`
  return null
}

/**
 * Тренд: направление, величина и признак «окрашивать ли». Цвет включается
 * только при отклонении выше порога, направление несёт стрелка — цвет
 * никогда не единственный носитель смысла.
 */
export function trend(deltaPercent) {
  if (deltaPercent === null || deltaPercent === undefined || Number.isNaN(deltaPercent)) {
    return { direction: 'flat', arrow: '→', value: null, colored: false }
  }
  const abs = Math.abs(deltaPercent)
  const direction = deltaPercent > 0 ? 'up' : deltaPercent < 0 ? 'down' : 'flat'
  return {
    direction,
    arrow: direction === 'up' ? '↑' : direction === 'down' ? '↓' : '→',
    value: deltaPercent,
    colored: abs >= TREND_THRESHOLD && direction !== 'flat'
  }
}

/**
 * Незакрытый период. Семнадцать вакансий за неполный сентябрь без пометки
 * читаются как обвал рынка, поэтому последний период всегда помечается
 * маркером и штриховкой, а не показывается наравне с прочими.
 */
export function isOpenPeriod(periodEnd, now = new Date()) {
  if (!periodEnd) return false
  const end = periodEnd instanceof Date ? periodEnd : new Date(periodEnd)
  if (Number.isNaN(end.getTime())) return false
  return end.getTime() > now.getTime()
}

/**
 * Группировка сумм по валютам. Возвращает записи по каждой валюте
 * отдельно: складывать и пересчитывать их запрещено, поэтому функция
 * не умеет возвращать одно общее число — это не упущение, а защита.
 */
export function byCurrency(items, getAmount, getCurrency) {
  const groups = new Map()
  for (const item of items) {
    const currency = getCurrency(item)
    const amount = getAmount(item)
    if (!currency || amount === null || amount === undefined) continue
    if (!groups.has(currency)) groups.set(currency, [])
    groups.get(currency).push(amount)
  }
  return [...groups.entries()]
    .map(([currency, values]) => ({ currency, values, n: values.length }))
    .sort((a, b) => b.n - a.n)
}

/**
 * Медиана. Средняя в системе не показывается: её тянут выбросы, одна
 * вакансия на 600 000 сдвигает число так, что оно перестаёт описывать
 * рынок. Возвращает null, если выборки не хватает.
 */
export function median(values) {
  const list = values.filter((v) => v !== null && v !== undefined && !Number.isNaN(v)).sort((a, b) => a - b)
  if (list.length < MIN_SAMPLE) return null
  const mid = Math.floor(list.length / 2)
  return list.length % 2 ? list[mid] : (list[mid - 1] + list[mid]) / 2
}
