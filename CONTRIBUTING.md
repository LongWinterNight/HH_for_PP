# Руководство для контрибьюторов

Благодарим за интерес к проекту HH.ru Analytics! Это руководство поможет вам внести свой вклад в развитие проекта.

## 📋 Содержание

- [Как внести вклад](#как-внести-вклад)
- [Стандарты кода](#стандарты-кода)
- [Процесс разработки](#процесс-разработки)
- [Сообщение об ошибках](#сообщение-об-ошибках)
- [Запрос функций](#запрос-функций)

---

## 🤝 Как внести вклад

### 1. Форкните репозиторий

Нажмите кнопку **Fork** в правом верхнем углу страницы репозитория.

### 2. Клонируйте репозиторий

```bash
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP
```

### 3. Создайте ветку

```bash
git checkout -b feature/your-feature-name
```

**Именование веток:**
- `feature/` — для новых функций
- `bugfix/` — для исправления ошибок
- `docs/` — для документации
- `refactor/` — для рефакторинга
- `test/` — для тестов

### 4. Внесите изменения

Следуйте стандартам кода ниже.

### 5. Закоммитьте изменения

```bash
git commit -m "feat: add new feature description"
```

**Формат коммитов:**
- `feat:` — новая функция
- `fix:` — исправление ошибки
- `docs:` — документация
- `style:` — форматирование
- `refactor:` — рефакторинг
- `test:` — тесты
- `chore:` — прочее

### 6. Отправьте в репозиторий

```bash
git push origin feature/your-feature-name
```

### 7. Создайте Pull Request

Перейдите в репозиторий на GitHub и нажмите **New Pull Request**.

---

## 📝 Стандарты кода

### Python Code Style

Следуйте [PEP 8](https://pep8.org/):

```python
# ✅ Правильно
def calculate_salary(experience: int, area: str) -> float:
    """Расчёт зарплаты по опыту и региону."""
    return base_salary * (1 + experience * 0.1)


# ❌ Неправильно
def calcSal(exp,area):return base*exp
```

### Типизация

Используйте type hints:

```python
from typing import Optional, List, Dict, Any

def process_vacancies(
    keywords: List[str],
    max_pages: int = 10,
    days_back: Optional[int] = None
) -> Dict[str, Any]:
    ...
```

### Документирование

Добавляйте docstrings:

```python
def collect_vacancies(keyword: str) -> List[Dict]:
    """
    Сбор вакансий по ключевому слову.

    Args:
        keyword: Поисковый запрос

    Returns:
        Список словарей с данными вакансий

    Raises:
        APIError: При ошибке запроса к API
    """
```

### Логирование

Используйте логгер вместо print:

```python
from src.utils import get_logger

logger = get_logger(__name__)

logger.info("Начало сбора вакансий")
logger.error(f"Ошибка при запросе: {error}")
```

---

## 🔄 Процесс разработки

### Ветка main

- ✅ Стабильная версия
- ✅ Проходит тесты
- ✅ Документация обновлена

### Ветка develop (опционально)

- 🔄 Активная разработка
- 🧪 Тесты могут выполняться

### Pull Request Checklist

Перед созданием PR убедитесь:

- [ ] Код следует PEP 8
- [ ] Добавлены type hints
- [ ] Написаны docstrings
- [ ] Пройдены тесты: `pytest tests/ -v`
- [ ] Обновлена документация (если нужно)
- [ ] Добавлены тесты (для новых функций)

---

## 🐛 Сообщение об ошибках

### Шаблон Issue

```markdown
**Описание проблемы:**
Краткое описание проблемы.

**Шаги воспроизведения:**
1. Запустить `python main.py --collect`
2. Ввести параметр X
3. Увидеть ошибку

**Ожидаемое поведение:**
Что должно было произойти.

**Фактическое поведение:**
Что произошло вместо этого.

**Окружение:**
- OS: Windows 11
- Python: 3.12
- Версия проекта: 1.0.0

**Логи:**
```
Текст ошибки или лог
```

**Скриншоты:**
(если применимо)
```

---

## 💡 Запрос функций

### Шаблон Feature Request

```markdown
**Описание функции:**
Что вы хотите добавить?

**Проблема:**
Какую проблему решает эта функция?

**Пример использования:**
```python
# Пример кода с новой функцией
python optimized_parser.py --new-feature
```

**Альтернативы:**
Какие существуют обходные пути?

**Дополнительно:**
Любая дополнительная информация.
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
pytest tests/ -v

# С покрытием
pytest tests/ --cov=src --cov-report=html

# Конкретный тест
pytest tests/test_api_client.py -v
```

### Написание тестов

```python
def test_vacancy_collection():
    """Тест сбора вакансий."""
    collector = VacancyCollector(max_pages=2)
    result = collector.collect_all(keywords=["Python"])
    
    assert result["total"] > 0
    assert "unique" in result
```

---

## 📚 Ресурсы

- [Документация проекта](README.md)
- [HH.ru API](https://github.com/hhru/api)
- [PEP 8](https://pep8.org/)
- [Semantic Versioning](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

## 📞 Контакты

- **GitHub Issues:** [Сообщить об ошибке](https://github.com/LongWinterNight/HH_for_PP/issues)
- **Discussions:** [Обсуждение проекта](https://github.com/LongWinterNight/HH_for_PP/discussions)

---

**Спасибо за ваш вклад! 🎉**
