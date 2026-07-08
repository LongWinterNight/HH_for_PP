#!/usr/bin/env python3
"""
Скрипт для очистки словаря навыков от дублей и синонимов.
"""

import yaml
from pathlib import Path

# Путь к config.yaml
CONFIG_PATH = Path(__file__).parent / "config.yaml"

# Словари синонимов для объединения (ключ - каноническое название)
SYNONYM_GROUPS = {
    # Переговоры
    "переговоры": [
        "ведение переговоров",
        "переговоры",
        "деловые переговоры",
    ],
    
    # Организация
    "организация": [
        "организация встреч",
        "организация мероприятий",
        "организация работы",
    ],
    
    # Контроль
    "контроль": [
        "контроль расходов",
        "контроль уборки",
        "контроль питания",
        "контроль качества",
    ],
    
    # Взаимодействие
    "взаимодействие": [
        "взаимодействие с арендодателем",
        "взаимодействие с клиентами",
        "взаимодействие с поставщиками",
    ],
    
    # Работа с документами
    "документооборот": [
        "делопроизводство",
        "документооборот",
        "работа с документами",
    ],
    
    # Продажи
    "продажи": [
        "активные продажи",
        "розничные продажи",
        "оптовые продажи",
    ],
    
    # Клиенты
    "работа с клиентами": [
        "ведение клиентов",
        "сопровождение клиентов",
        "работа с клиентами",
        "клиентоориентированность",
    ],
    
    # Отчётность
    "отчётность": [
        "отчётность",
        "ведение отчётности",
        "подготовка отчётов",
    ],
    
    # Поиск
    "поиск": [
        "поиск поставщиков",
        "поиск клиентов",
        "поиск информации",
    ],
    
    # Образование
    "высшее образование": [
        "высшее образование",
        "высшее профессиональное образование",
    ],
}


def load_config():
    """Загрузка конфигурации."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config):
    """Сохранение конфигурации."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def normalize_skill(skill: str) -> str:
    """Нормализация названия навыка."""
    return skill.lower().strip()


def replace_synonyms(skills: list[str]) -> list[str]:
    """Замена синонимов на канонические названия."""
    result = []
    
    # Создаём обратный маппинг: синоним -> каноническое название
    synonym_map = {}
    for canonical, synonyms in SYNONYM_GROUPS.items():
        for synonym in synonyms:
            synonym_map[normalize_skill(synonym)] = canonical
    
    # Заменяем синонимы
    for skill in skills:
        normalized = normalize_skill(skill)
        canonical = synonym_map.get(normalized, normalized)
        if canonical not in result:
            result.append(canonical)
    
    return result


def remove_duplicates(skills: list[str]) -> list[str]:
    """Удаление точных дублей."""
    seen = set()
    result = []
    for skill in skills:
        normalized = normalize_skill(skill)
        if normalized not in seen:
            seen.add(normalized)
            result.append(skill)
    return result


def clean_config():
    """Очистка конфигурации от дублей."""
    config = load_config()
    
    print("🔍 Очистка словарей навыков...")
    print("=" * 60)
    
    # Очищаем hard_skills
    if "hard_skills" in config:
        original_count = len(config["hard_skills"])
        config["hard_skills"] = remove_duplicates(config["hard_skills"])
        # config["hard_skills"] = replace_synonyms(config["hard_skills"])
        print(f"Hard Skills: {original_count} → {len(config['hard_skills'])} (-{original_count - len(config['hard_skills'])})")
    
    # Очищаем soft_skills
    if "soft_skills" in config:
        original_count = len(config["soft_skills"])
        config["soft_skills"] = remove_duplicates(config["soft_skills"])
        print(f"Soft Skills: {original_count} → {len(config['soft_skills'])} (-{original_count - len(config['soft_skills'])})")
    
    # Очищаем tools
    if "tools" in config:
        original_count = len(config["tools"])
        config["tools"] = remove_duplicates(config["tools"])
        print(f"Tools: {original_count} → {len(config['tools'])} (-{original_count - len(config['tools'])})")
    
    # Сохраняем
    save_config(config)
    
    print("=" * 60)
    print("✅ Конфигурация очищена!")
    print(f"📁 Файл: {CONFIG_PATH}")


if __name__ == "__main__":
    clean_config()
