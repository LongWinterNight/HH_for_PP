"""
Проверка правила правдоподобия зарплат.

Случаи взяты из настоящих данных, а не выдуманы: «18 EUR» у Structural
Steel Supervisor, «400 UZS» у HR Assistant, «от 50 до 100 000 ₽» у
менеджера по подбору. Такой тест защищает не абстрактную границу, а
конкретные записи, из-за которых минимум на экране показывал «от 7 ₽».
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.salary_sanity import (
    МАЛО,
    ПОРОГ_МЕСЯЧНОЙ_ОПЛАТЫ,
    РАЗРЫВ,
    зарплата_правдоподобна,
    причина_сомнения,
    только_правдоподобные,
)


@pytest.mark.parametrize("от, до, валюта", [
    (18, 18, "EUR"),        # часовая ставка в поле месячной
    (8, 16, "USD"),         # то же у тестировщика
    (400, None, "UZS"),     # потерянные нули
    (7, None, "RUB"),       # ночной официант
    (5000, None, "KZT"),    # бухгалтер за 5 000 тенге
    (120, None, "BYR"),     # оплата за смену
])
def test_известные_случаи_помечаются(от, до, валюта):
    assert причина_сомнения(от, до, валюта) == МАЛО


def test_разрыв_вилки_ловится_отдельно():
    """«От 32 000 до 840 000» — не широкая вилка, а потерянные нули."""
    assert причина_сомнения(32_000, 840_000, "RUB") == РАЗРЫВ


@pytest.mark.parametrize("от, до, валюта", [
    (120_000, 180_000, "RUB"),
    (30_000, 600_000, "RUB"),   # продавец на проценте: вилка широкая, но настоящая
    (400, 700, "EUR"),
    (1_000_000, 6_000_000, "UZS"),
    (None, 90_000, "RUB"),      # указана только верхняя граница
])
def test_настоящие_зарплаты_не_трогаем(от, до, валюта):
    assert зарплата_правдоподобна(от, до, валюта)


def test_проверяется_та_граница_которая_указана():
    """У половины вакансий задана только одна из двух границ."""
    assert причина_сомнения(None, 18, "EUR") == МАЛО
    assert причина_сомнения(None, 1200, "EUR") is None


def test_незнакомая_валюта_не_считается_сомнительной():
    """Иначе при выходе на новый рынок половина вакансий тихо исчезнет."""
    assert причина_сомнения(5, 10, "TRY") is None
    assert причина_сомнения(5, 10, None) is None


def test_порог_ниже_настоящей_массы():
    """
    Порог обязан оставлять запас до реальных зарплат.

    На замере 08.09.2026 первый перцентиль рубля был 20 000 — вчетверо
    выше порога. Если однажды порог подберётся к массе вплотную, правило
    начнёт отсекать настоящие вакансии, и тест должен упасть раньше, чем
    это увидит пользователь.
    """
    assert ПОРОГ_МЕСЯЧНОЙ_ОПЛАТЫ["RUB"] <= 20_000 / 4


def test_выборка_чистится_по_колонке():
    """Готовая пометка из базы важнее пересчёта: она уже согласована."""
    df = pd.DataFrame([
        {"salary_from": 120_000, "salary_to": None, "salary_currency": "RUB", "salary_doubt": None},
        {"salary_from": 18, "salary_to": 18, "salary_currency": "EUR", "salary_doubt": МАЛО},
        {"salary_from": None, "salary_to": None, "salary_currency": None, "salary_doubt": None},
    ])
    assert list(только_правдоподобные(df)["salary_from"]) == [120_000]


def test_выборка_чистится_без_колонки():
    """Данные приходят и не из базы — например, из разбора файлов сбора."""
    df = pd.DataFrame([
        {"salary_from": 120_000, "salary_to": None, "salary_currency": "RUB"},
        {"salary_from": 18, "salary_to": 18, "salary_currency": "EUR"},
    ])
    assert list(только_правдоподобные(df)["salary_from"]) == [120_000]


def test_минимум_перестаёт_врать():
    """Ради этого всё и делалось: «от 7 ₽» на экране и в отчёте."""
    df = pd.DataFrame([
        {"salary_from": 7, "salary_to": None, "salary_currency": "RUB"},
        {"salary_from": 60_000, "salary_to": None, "salary_currency": "RUB"},
        {"salary_from": 90_000, "salary_to": None, "salary_currency": "RUB"},
    ])
    assert df["salary_from"].min() == 7
    assert только_правдоподобные(df)["salary_from"].min() == 60_000


def test_запись_не_исчезает_из_выборки():
    """
    Пометка — не удаление.

    Вакансия настоящая, а правило основано на догадке: скрывать из-за
    неуверенности в одном поле существующую работу нельзя.
    """
    from src.storage import VacancyStorage
    import tempfile
    from pathlib import Path

    хранилище = VacancyStorage(Path(tempfile.mkdtemp()) / "проба.db")
    try:
        хранилище.save_vacancies_incremental(pd.DataFrame([
            {"vacancy_id": "1", "vacancy_name": "Обычная",
             "salary_from": 120_000, "salary_to": None, "salary_currency": "RUB"},
            {"vacancy_id": "2", "vacancy_name": "Часовая ставка",
             "salary_from": 18, "salary_to": 18, "salary_currency": "EUR"},
        ]))
        все = хранилище.get_all_vacancies()
        assert len(все) == 2, "помеченная вакансия обязана остаться в списке"
        помеченная = все[все["vacancy_id"] == "2"].iloc[0]
        assert помеченная["salary_doubt"] == МАЛО
    finally:
        хранилище.close()
