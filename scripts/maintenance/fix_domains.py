#!/usr/bin/env python3
"""
Скрипт для исправления доменов в существующем каталоге профессий.
Заменяет полные названия доменов на ключи (IT, SALES, etc.)
"""

import json
from pathlib import Path

# Пути
PROJECT_ROOT = Path(__file__).parent
CATALOG_FILE = PROJECT_ROOT / "data" / "professions_catalog.json"

# Маппинг: полное название -> ключ
DOMAIN_MAPPING = {
    "Информационные технологии": "IT",
    "Продажи и работа с клиентами": "SALES",
    "Розничная торговля": "RETAIL",
    "Маркетинг и реклама": "MARKETING",
    "Финансы и бухгалтерия": "FINANCE",
    "Управление персоналом": "HR",
    "Производство и технологии": "PRODUCTION",
    "Логистика и ВЭД": "LOGISTICS",
    "Медицина и фармацевтика": "MEDICINE",
    "Образование и наука": "EDUCATION",
    "Строительство и недвижимость": "CONSTRUCTION",
    "Рестораны и общественное питание": "HORECA",
    "Красота и фитнес": "BEAUTY",
    "Юриспруденция": "LEGAL",
    "Административный персонал": "ADMIN",
    "Творчество и дизайн": "CREATIVE",
    "СМИ и издательское дело": "MEDIA",
    "Транспорт и связь": "TRANSPORT",
    "Сельское хозяйство": "AGRO",
    "Охрана и безопасность": "SECURITY",
    "Спорт и туризм": "SPORT",
    "Другое": "OTHER"
}

def fix_catalog():
    """Исправить каталог."""
    print("🔧 Исправление каталога профессий...")
    
    # Загружаем каталог
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    
    # Исправляем домены
    fixed_count = 0
    for prof_key, prof in catalog["professions"].items():
        old_domain = prof.get("domain", "")
        
        # Ищем соответствие
        new_domain = DOMAIN_MAPPING.get(old_domain, old_domain)
        
        if old_domain != new_domain:
            prof["domain"] = new_domain
            fixed_count += 1
    
    # Сохраняем
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Исправлено {fixed_count} профессий")
    
    # Статистика
    domain_counts = {}
    for prof in catalog["professions"].values():
        domain = prof.get("domain", "OTHER")
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    
    print("\n📊 Статистика по доменам:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {domain}: {count}")


if __name__ == "__main__":
    fix_catalog()
