"""
Проверка правил вёрстки отчёта XLSX.

Проверяется не то, что файл собрался, а то, что в нём соблюдены решения
дизайн-системы: числа остались числами, «не указана» не подменяет пустую
ячейку, объединённых ячеек нет ни одной, валюты не сложены в одну строку.
Каждое из этих правил однажды нарушалось в прежних анализаторах, и
нарушение было видно только при открытии файла.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest
from openpyxl import load_workbook

from src.report_xlsx import КОЛОНКИ, МАЛАЯ_ВЫБОРКА, СЕРЫЙ, собрать_отчёт


@pytest.fixture
def выборка() -> pd.DataFrame:
    """Выборка на две валюты: одна многочисленная, вторая — из двух записей."""
    return pd.DataFrame([
        {
            "vacancy_id": "1001", "vacancy_name": "Аналитик данных",
            "employer_name": "Контур", "area": "Москва",
            "salary_from": 150000.0, "salary_to": 220000.0, "salary_currency": "RUB",
            "salary_from_rub": 150000.0, "rate_date": "2026-09-09",
            "experience": "От 1 года до 3 лет", "published_at": "2026-09-01T10:15:00+0300",
            "vacancy_url": "https://hh.ru/vacancy/1001",
            "hard_skills": "SQL, Python", "soft_skills": "Внимательность", "tools": "Excel",
        },
        {
            "vacancy_id": "1002", "vacancy_name": "Продуктовый аналитик",
            "employer_name": "Ozon", "area": "Санкт-Петербург",
            "salary_from": 90000.0, "salary_to": None, "salary_currency": "RUB",
            "salary_from_rub": 90000.0, "rate_date": "2026-09-09",
            "experience": "Нет опыта", "published_at": "2026-09-02T09:00:00+0300",
            "vacancy_url": "https://hh.ru/vacancy/1002",
            "hard_skills": "SQL", "soft_skills": None, "tools": None,
        },
        {
            # Без зарплаты: должна попасть в выгрузку, но не в расчёты.
            "vacancy_id": "1003", "vacancy_name": "Стажёр-аналитик",
            "employer_name": "Тинькофф", "area": "Москва",
            "salary_from": None, "salary_to": None, "salary_currency": None,
            "salary_from_rub": None, "rate_date": None,
            "experience": "Нет опыта", "published_at": "2026-09-03T12:00:00+0300",
            "vacancy_url": "https://hh.ru/vacancy/1003",
            "hard_skills": "Python", "soft_skills": None, "tools": None,
        },
        {
            "vacancy_id": "1004", "vacancy_name": "Data Analyst",
            "employer_name": "Kolesa", "area": "Алматы",
            "salary_from": 600000.0, "salary_to": 900000.0, "salary_currency": "KZT",
            "salary_from_rub": 114203.0, "rate_date": "2026-09-09",
            "experience": "От 3 до 6 лет", "published_at": "2026-09-04T08:30:00+0600",
            "vacancy_url": "https://hh.ru/vacancy/1004",
            "hard_skills": "SQL", "soft_skills": None, "tools": None,
        },
    ])


@pytest.fixture
def книга(выборка, tmp_path):
    путь = собрать_отчёт(
        выборка,
        tmp_path / "отчёт.xlsx",
        {"период": "01.09 — 08.09.2026", "курс_на": "09.09.2026"},
    )
    return load_workbook(путь)


def test_четыре_листа_в_порядке_чтения(книга):
    """Срез идёт первым: читатель узнаёт, откуда числа, прежде чем их увидеть."""
    assert книга.sheetnames == ["Срез", "Вакансии", "Сводка", "Навыки"]


def test_ни_одной_объединённой_ячейки(книга):
    """Объединения ломают фильтр, сортировку и сводные таблицы."""
    for имя in книга.sheetnames:
        assert len(книга[имя].merged_cells.ranges) == 0, имя


def test_зарплата_записана_числом(книга):
    """Число в текстовой ячейке лишает выгрузку смысла: по нему не отсортировать."""
    ws = книга["Вакансии"]
    assert ws["E2"].value == 150000
    assert isinstance(ws["E2"].value, (int, float))
    assert ws["E2"].number_format == "# ##0"


def test_пустая_ячейка_вместо_не_указана(книга):
    """Текст «не указана» в числовой колонке — то же самое, что мусор в данных."""
    ws = книга["Вакансии"]
    assert ws["F3"].value is None   # верхняя граница не задана
    assert ws["E4"].value is None   # зарплаты нет вовсе
    assert ws["G4"].value is None   # валюты нет вовсе


def test_дата_записана_датой_без_времени(книга):
    """Дата датой — иначе сортировка идёт по строке, а группировка по дню не работает."""
    ws = книга["Вакансии"]
    # Обратно openpyxl отдаёт datetime: в XLSX дата хранится числом, и
    # нулевое время как раз означает, что часы с минутами отсечены.
    assert ws["I2"].value == dt.datetime(2026, 9, 1, 0, 0)
    assert ws["I2"].number_format == "DD.MM.YYYY"


def test_идентификатор_ведёт_на_источник(книга):
    """Проверить вакансию можно в один клик, а не поиском по названию."""
    ws = книга["Вакансии"]
    assert ws["A2"].value == "1001"
    assert ws["A2"].number_format == "@"
    assert ws["A2"].hyperlink.target == "https://hh.ru/vacancy/1001"


def test_шапка_закреплена_и_с_автофильтром(книга):
    """Файл готов к работе сразу после открытия, настраивать его не нужно."""
    ws = книга["Вакансии"]
    assert ws.freeze_panes == "A2"
    # Диапазон растёт вместе с составом колонок: он считается по КОЛОНКИ,
    # и жёсткое «A1:I5» скрыло бы забытую колонку вместо того, чтобы
    # показать её.
    последняя = ws.cell(row=1, column=len(КОЛОНКИ)).column_letter
    assert ws.auto_filter.ref == f"A1:{последняя}5"


def test_ширины_колонок_заданы_явно(книга):
    """Автоподбор ширины ломается на длинных названиях вакансий."""
    ws = книга["Вакансии"]
    for i, колонка in enumerate(КОЛОНКИ, start=1):
        буква = ws.cell(row=1, column=i).column_letter
        assert ws.column_dimensions[буква].width == колонка["ширина"]


def test_эквивалент_отдельной_колонкой(книга):
    """Внутри файла переключателя нет: сравнить сумы с рублями можно
    только по эквиваленту, и он должен быть числом, а не текстом."""
    ws = книга["Вакансии"]
    заголовки = [c.value for c in ws[1]]

    assert заголовки[-1] == "В рублях", "эквивалент последний — A–I не сдвинуты"
    assert заголовки[:9] == [
        "ID", "Вакансия", "Компания", "Регион", "Зарплата от",
        "Зарплата до", "Валюта", "Опыт", "Опубликована",
    ], "состав и порядок колонок из спеки не изменились"

    колонка = len(КОЛОНКИ)
    assert ws.cell(row=2, column=колонка).value == 150000
    assert ws.cell(row=2, column=колонка).number_format == "# ##0"
    # Тенге пересчитаны, а не скопированы: иначе колонка бесполезна.
    тенге = ws.cell(row=5, column=колонка)
    assert тенге.value == 114203 and ws.cell(row=5, column=5).value == 600000
    # У вакансии без зарплаты эквивалента нет — пустая ячейка, не ноль.
    assert ws.cell(row=4, column=колонка).value is None


def test_срез_называет_курс_и_дату(книга):
    """«59 330 ₽» без курса и дня ничем не подтверждено."""
    ws = книга["Срез"]
    строки = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
              for r in range(2, ws.max_row + 1)}

    assert строки["Курс ЦБ на"] == "09.09.2026", "прочерк вместо даты означает неподтверждённое число"


def test_валюты_не_сложены_и_итога_нет(книга):
    """Сумма разных валют — то самое число, из-за которого интерфейс переделывали."""
    ws = книга["Сводка"]
    валюты = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
    assert валюты == ["RUB", "KZT"]
    assert not any(isinstance(v, str) and "сег" in v.lower() for v in валюты)
    # Строка на валюту и ничего сверх: итоговой строки «всего» быть не должно.
    assert ws.max_row == 3


def test_малая_выборка_подана_серым(книга):
    """Медиана по паре вакансий — не показатель рынка, и это должно быть видно."""
    ws = книга["Сводка"]
    assert ws["F2"].value == 2 and ws["F2"].value < МАЛАЯ_ВЫБОРКА
    assert ws["F2"].font.color.rgb == СЕРЫЙ


def test_срез_называет_долю_без_зарплаты(книга):
    """Без этой оговорки средние числа вводят в заблуждение."""
    ws = книга["Срез"]
    подписи = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
               for r in range(2, ws.max_row + 1)}
    assert подписи["Вакансий в выборке"] == "4"
    assert подписи["Без указанной зарплаты"] == "1 из 4"
    assert "3 вакансиям" in подписи["Зарплатные числа считаны по"]
    assert подписи["Период публикаций"] == "01.09 — 08.09.2026"


def test_навыки_с_категорией_словом(книга):
    """Категория текстом, а не цветом: заливка не переживает копирования в чужую книгу."""
    ws = книга["Навыки"]
    строки = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
              for r in range(2, ws.max_row + 1)}
    assert строки["SQL"] == "Профессиональные"
    assert строки["Внимательность"] == "Личные"
    assert строки["Excel"] == "Инструменты"


def test_пустая_выборка_отклоняется(tmp_path):
    """Пустой отчёт хуже отсутствующего: получатель решит, что рынок пуст."""
    with pytest.raises(ValueError):
        собрать_отчёт(pd.DataFrame(), tmp_path / "пусто.xlsx")
