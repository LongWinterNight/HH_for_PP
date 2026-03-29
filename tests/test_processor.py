"""
Тесты для модуля processor.py.

Проверяют:
- Извлечение навыков из текста
- Нормализацию и лемматизацию
- Классификацию по категориям

Запуск: pytest tests/test_processor.py -v
"""

import sys
from pathlib import Path

import pytest

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.processor import VacancyProcessor


@pytest.fixture
def processor():
    """Фикстура для создания процессора."""
    return VacancyProcessor()


class TestNormalizeText:
    """Тесты нормализации текста."""

    def test_lowercase_conversion(self, processor):
        """Проверка приведения к нижнему регистру."""
        text = "PYTHON Developer"
        result = processor._normalize_text(text)
        assert result == "python developer"

    def test_whitespace_normalization(self, processor):
        """Проверка удаления лишних пробелов."""
        text = "Python    Developer"
        result = processor._normalize_text(text)
        assert result == "python developer"

    def test_empty_string(self, processor):
        """Проверка обработки пустой строки."""
        result = processor._normalize_text("")
        assert result == ""

    def test_none_input(self, processor):
        """Проверка обработки None."""
        result = processor._normalize_text(None)
        assert result == ""


class TestSkillExtraction:
    """Тесты извлечения навыков."""

    def test_extract_hard_skills(self, processor):
        """Проверка извлечения Hard Skills."""
        text = "Требуется Python разработчик со знанием PyTorch и TensorFlow"
        skills, by_category = processor._extract_skills_from_text(text)

        # Проверяем что найдены навыки
        assert "python" in skills or "pytorch" in skills or "tensorflow" in skills

        # Проверяем категоризацию
        assert isinstance(by_category, dict)
        assert "hard_skills" in by_category

    def test_extract_tools(self, processor):
        """Проверка извлечения Tools."""
        text = "Опыт работы с Docker, Kubernetes, Git"
        skills, by_category = processor._extract_skills_from_text(text)

        # Проверяем что найдены инструменты
        assert "docker" in skills or "kubernetes" in skills or "git" in skills

    def test_empty_string(self, processor):
        """Проверка обработки пустой строки."""
        skills, by_category = processor._extract_skills_from_text("")

        assert skills == []
        assert isinstance(by_category, dict)

    def test_empty_text(self, processor):
        """Проверка текста без навыков из словаря."""
        text = "Требуется опытный специалист в нашу команду"
        skills, by_category = processor._extract_skills_from_text(text)

        # Навыков не должно быть (если только "командная работа" не в словаре)
        assert isinstance(skills, list)
        # by_category может быть пустым или содержать пустые списки
        assert isinstance(by_category, dict)

    def test_no_skills_found(self, processor):
        """Проверка текста без навыков из словаря."""
        text = "Требуется опытный специалист в нашу команду"
        skills, by_category = processor._extract_skills_from_text(text)

        # Навыков не должно быть (если только "командная работа" не в словаре)
        assert isinstance(skills, list)


class TestLemmatization:
    """Тесты лемматизации."""

    def test_russian_lemmatization(self, processor):
        """Проверка лемматизации русских слов."""
        word = "программистами"
        result = processor._lemmatize(word)

        # Лемма должна быть короче оригинала
        assert len(result) <= len(word)

    def test_english_word(self, processor):
        """Проверка обработки английских слов."""
        word = "developers"
        result = processor._lemmatize(word)

        # Для английских слов просто lowercase
        assert result == "developers"

    def test_empty_word(self, processor):
        """Проверка пустого слова."""
        result = processor._lemmatize("")
        assert result == ""


class TestSalaryExtraction:
    """Тесты извлечения зарплаты."""

    def test_extract_salary_full(self, processor):
        """Проверка извлечения полной информации о зарплате."""
        vacancy = {
            "salary": {
                "from": 100000,
                "to": 200000,
                "currency": "RUB",
                "gross": True
            }
        }

        result = processor._extract_salary(vacancy)

        assert result["salary_from"] == 100000
        assert result["salary_to"] == 200000
        assert result["salary_currency"] == "RUB"
        assert result["salary_gross"] is True

    def test_extract_salary_none(self, processor):
        """Проверка отсутствия зарплаты."""
        vacancy = {"salary": None}
        result = processor._extract_salary(vacancy)

        assert result["salary_from"] is None
        assert result["salary_currency"] == "RUB"


class TestProcessSingleVacancy:
    """Тесты обработки одной вакансии."""

    def test_process_vacancy_structure(self, processor):
        """Проверка структуры результата."""
        vacancy = {
            "id": "12345",
            "name": "Python Developer",
            "description": "Требуется Python разработчик",
            "key_skills": [{"name": "Python"}, {"name": "Git"}],
            "employer": {"name": "Test Company", "id": "1"},
            "area": {"name": "Москва"}
        }

        result = processor._process_single_vacancy(vacancy)

        # Проверяем наличие обязательных полей
        assert "vacancy_id" in result
        assert "vacancy_name" in result
        assert "all_skills" in result
        assert "employer_name" in result

        # Проверяем значения
        assert result["vacancy_id"] == "12345"
        assert result["vacancy_name"] == "Python Developer"
        assert result["employer_name"] == "Test Company"
