"""
Тесты для модуля analyzer.py.

Проверяют:
- Подсчёт статистики по навыкам
- Формирование отчётов

Запуск: pytest tests/test_analyzer.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analyzer import VacancyAnalyzer


@pytest.fixture
def sample_df():
    """Фикстура с тестовыми данными."""
    data = {
        "vacancy_id": ["1", "2", "3"],
        "vacancy_name": [
            "Python Developer",
            "Data Scientist",
            "ML Engineer"
        ],
        "hard_skills": [
            "python, pytorch, sql",
            "python, pandas, numpy",
            "python, tensorflow, keras"
        ],
        "soft_skills": [
            "коммуникабельность, teamwork",
            "analytical thinking",
            "problem solving, teamwork"
        ],
        "tools": [
            "git, docker",
            "jupyter, git",
            "docker, kubernetes"
        ],
        "skill_count": [3, 3, 3],
        "hard_skill_count": [3, 3, 3],
        "soft_skill_count": [2, 1, 2],
        "tools_count": [2, 2, 2],
        "salary_from": [100000, 150000, 200000],
        "salary_to": [200000, 250000, 300000],
        "experience": [
            "От 1 года до 3 лет",
            "От 3 до 6 лет",
            "От 1 года до 3 лет"
        ],
        "area": ["Москва", "Москва", "Санкт-Петербург"]
    }
    return pd.DataFrame(data)


@pytest.fixture
def analyzer(sample_df):
    """Фикстура для создания анализатора."""
    return VacancyAnalyzer(sample_df)


class TestSkillsStatistics:
    """Тесты статистики по навыкам."""

    def test_compute_skills_statistics(self, analyzer):
        """Проверка вычисления статистики по навыкам."""
        stats = analyzer.compute_skills_statistics()

        assert "hard_skills" in stats
        assert "soft_skills" in stats
        assert "tools" in stats
        assert "total_vacancies" in stats

        assert stats["total_vacancies"] == 3

    def test_top_hard_skills(self, analyzer):
        """Проверка топ Hard Skills."""
        stats = analyzer.compute_skills_statistics()

        top_hard = stats.get("top_hard_skills", {})

        # Python должен быть на первом месте (упоминается 3 раза)
        assert "python" in top_hard
        assert top_hard["python"] == 3

    def test_cache_statistics(self, analyzer):
        """Проверка кэширования статистики."""
        # Первый вызов
        stats1 = analyzer.compute_skills_statistics()

        # Второй вызов (должен вернуть кэш)
        stats2 = analyzer.compute_skills_statistics()

        # Это тот же объект
        assert stats1 is stats2


class TestCountSkills:
    """Тесты подсчёта навыков."""

    def test_count_skills_basic(self, analyzer):
        """Проверка базового подсчёта."""
        column = pd.Series(["python, sql", "python, pandas", "sql"])

        result = analyzer._count_skills(column)

        assert result["python"] == 2
        assert result["sql"] == 2
        assert result["pandas"] == 1

    def test_count_skills_empty(self, analyzer):
        """Проверка пустой колонки."""
        column = pd.Series([None, "", None])

        result = analyzer._count_skills(column)

        assert result == {}

    def test_count_skills_whitespace(self, analyzer):
        """Проверка обработки пробелов."""
        column = pd.Series(["python ,  sql ", " pandas"])

        result = analyzer._count_skills(column)

        assert "python" in result
        assert "sql" in result
        assert "pandas" in result


class TestSalaryStatistics:
    """Тесты статистики по зарплатам."""

    def test_compute_salary_statistics(self, analyzer):
        """Проверка вычисления статистики зарплат."""
        stats = analyzer.compute_salary_statistics()

        assert "total_with_salary" in stats
        assert "avg_salary_from" in stats
        assert "median_salary_from" in stats

        assert stats["total_with_salary"] == 3

    def test_salary_by_experience(self, analyzer):
        """Проверка группировки по опыту."""
        stats = analyzer.compute_salary_statistics()

        assert "by_experience" in stats

        # Должно быть 2 группы опыта
        assert len(stats["by_experience"]) == 2


class TestDistribution:
    """Тесты распределений."""

    def test_experience_distribution(self, analyzer):
        """Проверка распределения по опыту."""
        dist = analyzer.compute_experience_distribution()

        assert "От 1 года до 3 лет" in dist
        assert dist["От 1 года до 3 лет"] == 2
        assert dist["От 3 до 6 лет"] == 1

    def test_area_distribution(self, analyzer):
        """Проверка распределения по регионам."""
        dist = analyzer.compute_area_distribution()

        assert "Москва" in dist
        assert "Санкт-Петербург" in dist
        assert dist["Москва"] == 2


class TestCSVExport:
    """Тесты экспорта в CSV."""

    def test_export_to_csv(self, analyzer, tmp_path):
        """Проверка экспорта в CSV."""
        # Меняем директорию для отчётов
        analyzer.reports_dir = tmp_path

        filepath = analyzer.export_to_csv()

        assert filepath.exists()
        assert filepath.suffix == ".csv"

        # Проверяем содержимое
        df = pd.read_csv(filepath)

        assert "category" in df.columns
        assert "skill" in df.columns
        assert "count" in df.columns


class TestEmptyDataFrame:
    """Тесты с пустым DataFrame."""

    def test_empty_dataframe_statistics(self):
        """Проверка обработки пустого DataFrame."""
        empty_df = pd.DataFrame()
        analyzer = VacancyAnalyzer(empty_df)

        stats = analyzer.compute_skills_statistics()

        assert stats == {}

    def test_empty_dataframe_print(self, capsys):
        """Проверка вывода для пустого DataFrame."""
        empty_df = pd.DataFrame()
        analyzer = VacancyAnalyzer(empty_df)

        analyzer.print_summary()

        captured = capsys.readouterr()
        assert "Нет данных для анализа" in captured.out
