#!/usr/bin/env python3
"""
Финальное распределение профессий из OTHER по доменам.
"""

import json
from pathlib import Path
from collections import defaultdict

# Пути
PROJECT_ROOT = Path(__file__).parent
CATALOG_FILE = PROJECT_ROOT / "data" / "professions_catalog.json"

# Ручное распределение для оставшихся
MANUAL_DISTRIBUTION = {
    # IT
    "IT": [
        'ui\\ux', 'ux/ui', 'designer', 'fullstack', 'analyst', 'it',
        'data scientist', 'ml engineer', 'ai', 'nlp', 'llm', 'нейрон',
        'ios software', 'bitrix', 'интегратор битрикс',
        'delivery manager', 'crm supervisor', 'revenue manager',
        'разметчик фото', 'нейронной сетью', 'стаффер', 'вайб-кодер',
        'sound designer', 'content manager', 'ai content creator'
    ],
    
    # Продажи
    "SALES": [
        'sales', 'head of sales', 'sales manager', 'лидоруб',
        'региональный представитель', 'представитель',
        'customer care', 'after-sales', 'retail'
    ],
    
    # HR
    "HR": [
        't&d', 'learning and development', 'onboarding', 'onboarding specialist',
        'методолог', 'квалификатор'
    ],
    
    # Финансы
    "FINANCE": [
        'finance', 'аудит', 'экономист-финансист', 'accounting', 'assistant'
    ],
    
    # Логистика
    "LOGISTICS": [
        'logistics', 'logistics manager'
    ],
    
    # Юриспруденция
    "LEGAL": [
        'lawyer', 'юрист', 'legal', 'public affairs', 'communications'
    ],
    
    # Образование
    "EDUCATION": [
        'teacher', 'учитель', 'преподаватель', 'english teacher',
        ' russian language', 'документовед'
    ],
    
    # Творчество
    "CREATIVE": [
        'designer', 'sound designer', 'design engineer', 'cad'
    ],
    
    # Административный
    "ADMIN": [
        'intern', 'стажер', 'стажировка', 'assistant', 'ассистент',
        'coo', 'chief operating officer', 'супервайзер',
        'сборщик', 'контролер', 'газификации', 'прескриптор'
    ],
    
    # Медицина
    "MEDICINE": [
        'inibsa'  # фармацевтика
    ]
}

def distribute_remaining():
    """Распределить оставшиеся профессии."""
    print("🔧 Распределение остатка из OTHER...")
    
    # Загружаем каталог
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    
    # Распределяем
    distributed = 0
    for prof_key, prof in catalog["professions"].items():
        if prof.get("domain") != "OTHER":
            continue
            
        name_lower = prof["name"].lower()
        
        # Проверяем по каждому домену
        for domain, keywords in MANUAL_DISTRIBUTION.items():
            if any(kw.lower() in name_lower for kw in keywords):
                prof["domain"] = domain
                prof["sphere"] = get_sphere(domain, prof["name"])
                distributed += 1
                break
    
    # Сохраняем
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Распределено {distributed} профессий")
    
    # Статистика
    domain_counts = defaultdict(int)
    for prof in catalog["professions"].values():
        domain_counts[prof.get("domain", "OTHER")] += 1
    
    print("\n📊 Итоговая статистика по доменам:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {domain}: {count}")


def get_sphere(domain: str, profession_name: str) -> str:
    """Получить сферу для домена."""
    spheres = {
        "IT": "Разработка ПО",
        "SALES": "Активные продажи (B2B)",
        "HR": "Рекрутинг и подбор персонала",
        "FINANCE": "Бухгалтерия и учет",
        "LOGISTICS": "Складская логистика",
        "LEGAL": "Корпоративное право",
        "EDUCATION": "Преподавание",
        "CREATIVE": "Графический дизайн",
        "ADMIN": "Управление проектами",
        "MEDICINE": "Фармация",
        "OTHER": "Другое"
    }
    return spheres.get(domain, "Другое")


if __name__ == "__main__":
    distribute_remaining()
