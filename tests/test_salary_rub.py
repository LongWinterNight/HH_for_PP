"""
Пересчёт зарплат в рубли.

Проверяется то, что легко сломать незаметно: номинал (курс ЦБ даётся за
100 тенге и за 10 000 сумов), поведение при незнакомой валюте и то, что
пересчёт не отменяет ранее принятых решений — сомнительная зарплата не
становится правдоподобной оттого, что её выразили в рублях.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.cbr_rates import Курсы
from src.salary_sanity import только_правдоподобные
from src.storage import VacancyStorage

# Курс из настоящего ответа ЦБ на 09.09.2026, приведённый к единице.
КУРСЫ = Курсы(
    на_дату=date(2026, 9, 9),
    значения={"RUB": 1.0, "USD": 86.473, "EUR": 100.4989,
              "KZT": 0.190339, "UZS": 0.00733485, "BYN": 28.1488},
)


@pytest.fixture
def хранилище():
    """Пустая база со своими курсами: тест не зависит от боевых данных."""
    путь = Path(tempfile.mkdtemp()) / "проба.db"
    склад = VacancyStorage(путь)
    склад.save_currency_rates(КУРСЫ)
    try:
        yield склад
    finally:
        склад.close()


def сохранить(склад, записи):
    склад.save_vacancies_incremental(pd.DataFrame(записи))
    return склад.get_all_vacancies()


def test_номинал_не_потерян(хранилище):
    """
    19 000 000 сум — это 139 тысяч рублей, а не 139 миллионов.

    Курс сумов ЦБ даёт за 10 000 единиц. Ошибка в номинале выглядит
    правдоподобно и потому не замечается глазом.
    """
    df = сохранить(хранилище, [
        {"vacancy_id": "1", "vacancy_name": "Сумовая",
         "salary_from": 19_000_000, "salary_to": None, "salary_currency": "UZS"},
        {"vacancy_id": "2", "vacancy_name": "Тенговая",
         "salary_from": 350_000, "salary_to": None, "salary_currency": "KZT"},
    ])
    по_ид = df.set_index("vacancy_id")["salary_from_rub"]
    assert по_ид["1"] == pytest.approx(139_362, abs=50)
    assert по_ид["2"] == pytest.approx(66_619, abs=50)


def test_обе_границы_вилки(хранилище):
    df = сохранить(хранилище, [
        {"vacancy_id": "1", "vacancy_name": "Вилка",
         "salary_from": 1_000, "salary_to": 2_000, "salary_currency": "USD"},
    ])
    строка = df.iloc[0]
    assert строка["salary_from_rub"] == pytest.approx(86_473, abs=10)
    assert строка["salary_to_rub"] == pytest.approx(172_946, abs=10)


def test_рубль_остаётся_собой(хранилище):
    df = сохранить(хранилище, [
        {"vacancy_id": "1", "vacancy_name": "Рублёвая",
         "salary_from": 120_000, "salary_to": None, "salary_currency": "RUB"},
    ])
    assert df.iloc[0]["salary_from_rub"] == 120_000


def test_дата_курса_рядом_с_числом(хранилище):
    """Без даты «≈ 139 000 ₽» ничем не подтверждено."""
    df = сохранить(хранилище, [
        {"vacancy_id": "1", "vacancy_name": "Любая",
         "salary_from": 1_000, "salary_to": None, "salary_currency": "USD"},
    ])
    assert pd.Timestamp(df.iloc[0]["rate_date"]).date() == date(2026, 9, 9)


def test_валюта_без_курса_остаётся_без_эквивалента(хранилище):
    """
    Пусто важнее нуля.

    Ноль в колонке рублей выглядит как настоящая зарплата и попадёт в
    минимум по выборке — то самое враньё, от которого уходили в E8.
    """
    df = сохранить(хранилище, [
        {"vacancy_id": "1", "vacancy_name": "Неведомая валюта",
         "salary_from": 50_000, "salary_to": None, "salary_currency": "XYZ"},
    ])
    строка = df.iloc[0]
    assert pd.isna(строка["salary_from_rub"])
    assert pd.isna(строка["rate_date"])
    # Сама вакансия при этом остаётся в выборке со своей суммой.
    assert строка["salary_from"] == 50_000


def test_сомнительная_зарплата_не_отмывается_рублями(хранилище):
    """
    «18 EUR» в рублях выглядит правдоподобно — и тем опаснее.

    Пересчёт не отменяет решения E8: помеченная запись не участвует в
    расчётах, в какой бы валюте её ни выразили.
    """
    df = сохранить(хранилище, [
        {"vacancy_id": "1", "vacancy_name": "Часовая ставка",
         "salary_from": 18, "salary_to": 18, "salary_currency": "EUR"},
        {"vacancy_id": "2", "vacancy_name": "Обычная",
         "salary_from": 120_000, "salary_to": None, "salary_currency": "RUB"},
    ])
    сомнительная = df[df["vacancy_id"] == "1"].iloc[0]
    assert сомнительная["salary_doubt"]
    assert сомнительная["salary_from_rub"] == pytest.approx(1_809, abs=5)

    в_расчёте = только_правдоподобные(df)
    assert list(в_расчёте["vacancy_id"]) == ["2"]


def test_курсы_переживают_перезапуск():
    """Курс читается из базы, а не из памяти процесса."""
    путь = Path(tempfile.mkdtemp()) / "проба.db"

    первое = VacancyStorage(путь)
    первое.save_currency_rates(КУРСЫ)
    первое.close()

    второе = VacancyStorage(путь)
    try:
        курсы = второе.get_currency_rates()
        assert курсы.на_дату == date(2026, 9, 9)
        assert курсы.рублей_за("USD") == pytest.approx(86.473)
        # Сопоставка кодов работает и на курсах из базы.
        assert курсы.рублей_за("BYR") == pytest.approx(28.1488)
    finally:
        второе.close()


def test_отказ_источника_оставляет_прежние_курсы(monkeypatch, хранилище):
    """Чужой сайт не должен ронять наш сбор."""
    import src.cbr_rates as цб

    monkeypatch.setattr(цб, "запросить", lambda *а, **к: (_ for _ in ()).throw(ConnectionError()))

    курсы = хранилище.refresh_currency_rates()
    assert курсы is not None
    assert курсы.на_дату == date(2026, 9, 9)
