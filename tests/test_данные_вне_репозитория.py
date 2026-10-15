"""
Тест-страж: данные вакансий в репозиторий не попадают (Y1‑1d).

Требование владельца 15.10.2026: репозиторий публичный, данным вакансий
в нём не место. В тот день в коммит попал
журнал рабочей базы, а проверка показала, что с марта git отслеживал 40
сырых выгрузок hh.ru, обработанные выгрузки и эталон из настоящих
вакансий. Проверка перед пушем смотрела строки и двоичные файлы не
видела; этот тест смотрит список отслеживаемых файлов.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

КОРЕНЬ = Path(__file__).resolve().parents[1]

# Что из data/ в репозитории допустимо: словарь навыков, замеры качества
# (числа) и решения по кандидатам (названия навыков). Всё остальное в
# data/ — данные или их производные.
РАЗРЕШЕНО_В_DATA = {
    "data/skills.yaml", "data/замер_навыков.json", "data/замер_поиска.json", "data/кандидаты_навыков.json",
    "data/areas.json", "data/.gitkeep",
}

ЗАПРЕЩЕНО = re.compile(
    r"\.(db|sqlite|db-journal|db-wal|db-shm|parquet)$"   # базы и их журналы
    r"|^data/(raw|processed|reports|backups)/"            # выгрузки и копии
    r"|^tests/fixtures/private/"                          # эталон из настоящих вакансий
    r"|^data/professions_catalog\.json$"
)


def отслеживаемые() -> list:
    if shutil.which("git") is None or not (КОРЕНЬ / ".git").exists():
        pytest.skip("нет git или это не рабочая копия репозитория")
    вывод = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files"], cwd=КОРЕНЬ,
                           capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [строка for строка in вывод.splitlines() if строка]


def test_данные_вакансий_не_отслеживаются():
    нарушения = [ф for ф in отслеживаемые() if ЗАПРЕЩЕНО.search(ф)]
    assert нарушения == [], f"git отслеживает данные вакансий: {нарушения[:10]}"


def test_в_data_только_разрешённое():
    лишнее = [ф for ф in отслеживаемые() if ф.startswith("data/") and ф not in РАЗРЕШЕНО_В_DATA]
    assert лишнее == [], f"в data/ отслеживается не разрешённое: {лишнее[:10]}"


def test_правило_ловит_выгрузку_и_журнал():
    for путь in ("data/raw/vacancies_LLM.json", "data/hh_vacancies.db-journal", "data/backups/до_023.db",
                 "tests/fixtures/private/эталон_навыков.json", "data/processed/x.parquet"):
        assert ЗАПРЕЩЕНО.search(путь), путь
    assert not ЗАПРЕЩЕНО.search("tests/fixtures/ответ_поиска.json"), "обезличенные образцы разрешены"
