// Форматирование чисел, дат и денег. Единственное место в продукте,
// где число превращается в строку: правила разрядов и валют иначе
// расходятся по экранам, и одно и то же значение выглядит по-разному.

const NBSP = ' '

/**
 * Разряды разделяются неразрывным пробелом. Обычный пробел позволяет
 * браузеру перенести строку внутри числа, и «100 900 ₽» разрывается,
 * а знак валюты уезжает отдельно от суммы.
 */
export function num(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toLocaleString('ru-RU').replace(/\s/g, NBSP)
}

/**
 * Сумма со знаком валюты.
 *
 * Валюты по-прежнему не складываются: сумма семи валют в одном числе —
 * та самая ошибка, из-за которой затевалась пересборка. Рублёвый
 * эквивалент по курсу ЦБ этого не отменяет — он идёт отдельным числом
 * рядом с исходной суммой, никогда вместо неё (см. moneyRub).
 */
const CURRENCY_SIGN = {
  RUR: '₽', RUB: '₽', USD: '$', EUR: '€', KZT: '₸',
  UZS: 'сум', BYR: 'Br', BYN: 'Br', KGS: 'сом', AZN: '₼', UAH: '₴', GEL: '₾'
}

/**
 * Порог сокращения: от миллиона сумма пишется как «6 млн».
 *
 * Ниже миллиона сокращать нечего — «120 000 ₽» читается с одного
 * взгляда. Выше начинается счёт разрядов глазами: «6 000 000 сум —
 * 9 000 000 сум» вилкой не помещалось в карточку вакансии и вылезало за
 * её край.
 *
 * Порог общий для всех валют намеренно. Сокращать «по длине строки»
 * означало бы, что одна и та же сумма выглядит по-разному в узкой
 * колонке и в широкой карточке, — а это ровно то расхождение, ради
 * которого форматирование собрано в одном файле.
 */
const MILLION = 1e6
const BILLION = 1e9

function short(value) {
  const abs = Math.abs(value)
  if (abs < MILLION) return num(Math.round(value))

  const [делитель, слово] = abs >= BILLION ? [BILLION, 'млрд'] : [MILLION, 'млн']
  const сокращённое = value / делитель

  // Одна цифра после запятой, и то лишь когда она не ноль: «6,0 млн»
  // выглядит точнее, чем есть, а «6 млн» честно говорит о порядке.
  const цифр = Math.abs(сокращённое) < 100 && Math.round(сокращённое * 10) % 10 !== 0 ? 1 : 0
  const число = сокращённое.toLocaleString('ru-RU', {
    minimumFractionDigits: цифр,
    maximumFractionDigits: цифр
  })
  return `${число}${NBSP}${слово}`
}

export function money(value, currency = 'RUR') {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = CURRENCY_SIGN[currency] || currency
  return `${short(value)}${NBSP}${sign}`
}

/**
 * Полная сумма без сокращения — для подсказки при наведении.
 *
 * Сокращение говорит о порядке величины, и этого достаточно, чтобы
 * сравнить вакансии. Но человек, которому важна точная цифра, должен
 * иметь способ её увидеть, не уходя на hh.ru.
 */
export function moneyExact(value, currency = 'RUR') {
  if (value === null || value === undefined || Number.isNaN(value)) return null
  const sign = CURRENCY_SIGN[currency] || currency
  return `${num(Math.round(value))}${NBSP}${sign}`
}

/**
 * Рублёвый эквивалент: «≈ 139 362 ₽».
 *
 * Знак приблизительности обязателен. Курс взят на дату сбора, к моменту
 * чтения он уже другой, и точное на вид число вводило бы в заблуждение
 * сильнее, чем его отсутствие. Дату курса называет подпись рядом с
 * таблицей — без неё эквивалент ничем не подтверждён.
 */
export function moneyRub(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return null
  return `≈${NBSP}${money(value, 'RUB')}`
}

/**
 * Период выплаты словами: «за час», «за смену».
 *
 * Формулировка совпадает с той, что человек видит на hh.ru: расхождение
 * подписи с источником читается как ошибка продукта, даже когда число
 * верное. Месячная оплата не подписывается — она подразумевается, и
 * «120 000 ₽ за месяц» в каждой строке было бы шумом.
 */
const SALARY_PERIOD = {
  HOUR: 'за час',
  SHIFT: 'за смену',
  FLY_IN_FLY_OUT: 'за вахту',
  SERVICE: 'за услугу'
}

export function salaryPeriod(mode) {
  return SALARY_PERIOD[mode] || null
}

/** Доля в процентах: одна цифра после запятой, как в дизайн-системе. */
export function percent(part, whole) {
  if (!whole) return '—'
  const v = (part / whole) * 100
  return `${v.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}${NBSP}%`
}

/** Дата и время сбора: 01.09.2026 в 19:15. */
export function dateTime(value) {
  if (!value) return '—'
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const date = d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  return `${date} в ${time}`
}

/**
 * «14 часов назад» — человеку важно, насколько данные свежие,
 * а не в какую минуту прошёл сбор.
 */
export function timeAgo(value) {
  if (!value) return '—'
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return '—'

  const minutes = Math.round((Date.now() - d.getTime()) / 60000)
  if (minutes < 1) return 'только что'
  if (minutes < 60) return `${minutes}${NBSP}${plural(minutes, 'минуту', 'минуты', 'минут')} назад`

  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}${NBSP}${plural(hours, 'час', 'часа', 'часов')} назад`

  const days = Math.round(hours / 24)
  return `${days}${NBSP}${plural(days, 'день', 'дня', 'дней')} назад`
}

/**
 * «14 ч» — та же давность, но для шапки, где на подпись есть несколько
 * знаков. Полная форма рядом, в подсказке: точное время нужно, когда
 * человек проверяет, застал ли сбор сегодняшние публикации.
 */
export function timeAgoShort(value) {
  if (!value) return '—'
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return '—'

  const minutes = Math.round((Date.now() - d.getTime()) / 60000)
  if (minutes < 1) return 'только что'
  if (minutes < 60) return `${minutes}${NBSP}мин`

  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}${NBSP}ч`

  return `${Math.round(hours / 24)}${NBSP}дн`
}

/** Русское склонение после числительного. */
export function plural(n, one, few, many) {
  const abs = Math.abs(n) % 100
  const last = abs % 10
  if (abs > 10 && abs < 20) return many
  if (last > 1 && last < 5) return few
  if (last === 1) return one
  return many
}

/** «909 вакансий» — число вместе со склонённым словом, неразрывно. */
export function countOf(n, one, few, many) {
  return `${num(n)}${NBSP}${plural(n, one, few, many)}`
}

export function vacancies(n) {
  return countOf(n, 'вакансия', 'вакансии', 'вакансий')
}

export { NBSP }
