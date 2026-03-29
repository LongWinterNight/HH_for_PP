#!/usr/bin/env python3
"""
Скрипт для сбора профессий и специальностей из HH.ru API.
Создает структурированный каталог профессий с категориями, сферами и навыками.

API HH.ru: https://api.hh.ru/openapi
"""

import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict

# Конфигурация
API_BASE = "https://api.hh.ru"
USER_AGENT = "HHAnalyticsBot/1.0 (safanch2705@gmail.com)"
DELAY = 0.5  # Задержка между запросами

# Пути
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# =============================================================================
# Справочник сфер деятельности и профессиональных областей из HH.ru
# =============================================================================

# Основные сферы деятельности (домены)
DOMAINS = {
    "IT": "Информационные технологии",
    "SALES": "Продажи и работа с клиентами",
    "MARKETING": "Маркетинг и реклама",
    "FINANCE": "Финансы и бухгалтерия",
    "HR": "Управление персоналом",
    "PRODUCTION": "Производство и технологии",
    "LOGISTICS": "Логистика и ВЭД",
    "MEDICINE": "Медицина и фармацевтика",
    "EDUCATION": "Образование и наука",
    "CONSTRUCTION": "Строительство и недвижимость",
    "RETAIL": "Розничная торговля",
    "HORECA": "Рестораны и общественное питание",
    "BEAUTY": "Красота и фитнес",
    "LEGAL": "Юриспруденция",
    "ADMIN": "Административный персонал",
    "CREATIVE": "Творчество и дизайн",
    "MEDIA": "СМИ и издательское дело",
    "TRANSPORT": "Транспорт и связь",
    "AGRO": "Сельское хозяйство",
    "SECURITY": "Охрана и безопасность",
    "SPORT": "Спорт и туризм",
    "NGO": "Некоммерческие организации",
    "OTHER": "Другое"
}

# Профессиональные области (подкатегории)
PROFESSIONAL_AREAS = {
    # IT
    "IT": [
        "Разработка ПО",
        "Системное администрирование",
        "Информационная безопасность",
        "Тестирование (QA)",
        "Аналитика данных",
        "DevOps",
        "Веб-разработка",
        "Мобильная разработка",
        "1С программирование",
        "Искусственный интеллект и ML"
    ],
    
    # Продажи
    "SALES": [
        "Активные продажи",
        "Розничные продажи",
        "Оптовые продажи",
        "B2B продажи",
        "Работа с клиентами",
        "Торговые представители",
        "Менеджеры по продажам"
    ],
    
    # Маркетинг
    "MARKETING": [
        "Digital маркетинг",
        "SMM",
        "Контент-маркетинг",
        "Бренд-менеджмент",
        "Маркетинговая аналитика",
        "Event маркетинг"
    ],
    
    # Финансы
    "FINANCE": [
        "Бухгалтерия",
        "Финансовый анализ",
        "Аудит",
        "Налоговое планирование",
        "Банковское дело",
        "Страхование"
    ],
    
    # HR
    "HR": [
        "Рекрутинг",
        "Обучение и развитие",
        "HR-брендинг",
        "Оплата труда",
        "Кадровое делопроизводство"
    ],
    
    # Производство
    "PRODUCTION": [
        "Инженерия",
        "Технология производства",
        "Контроль качества",
        "Снабжение",
        "Операционное производство"
    ],
    
    # Логистика
    "LOGISTICS": [
        "Складская логистика",
        "Транспортная логистика",
        "ВЭД",
        "Закупки",
        "Дистрибуция"
    ],
    
    # Медицина
    "MEDICINE": [
        "Лечебное дело",
        "Сестринское дело",
        "Фармация",
        "Стоматология",
        "Диагностика"
    ],
    
    # Образование
    "EDUCATION": [
        "Преподавание",
        "Репетиторство",
        "Методическая работа",
        "Научная деятельность"
    ],
    
    # Строительство
    "CONSTRUCTION": [
        "Проектирование",
        "Строительно-монтажные работы",
        "Сметное дело",
        "Геодезия",
        "Архитектура"
    ],
    
    # Розница
    "RETAIL": [
        "Торговый зал",
        "Кассиры",
        "Мерчандайзинг",
        "Управление магазином"
    ],
    
    # HORECA
    "HORECA": [
        "Кухня",
        "Зал",
        "Бар",
        "Управление рестораном"
    ],
    
    # Красота
    "BEAUTY": [
        "Парикмахерское искусство",
        "Косметология",
        "Маникюр/педикюр",
        "Визаж",
        "Фитнес-тренер"
    ],
    
    # Юриспруденция
    "LEGAL": [
        "Корпоративное право",
        "Судебная практика",
        "Налоговое право",
        "Патентное право"
    ],
    
    # Административный
    "ADMIN": [
        "Офис-менеджмент",
        "Секретариат",
        "Делопроизводство",
        "АХО"
    ],
    
    # Творчество
    "CREATIVE": [
        "Графический дизайн",
        "Веб-дизайн",
        "Иллюстрация",
        "Фотография",
        "Видеопроизводство"
    ],
    
    # СМИ
    "MEDIA": [
        "Журналистика",
        "Редактура",
        "Копирайтинг",
        "PR"
    ],
    
    # Транспорт
    "TRANSPORT": [
        "Водители",
        "Диспетчеры",
        "Связь и телеком"
    ],
    
    # Сельское хозяйство
    "AGRO": [
        "Агрономия",
        "Животноводство",
        "Механизация"
    ],
    
    # Охрана
    "SECURITY": [
        "Охрана",
        "Безопасность",
        "ЧС и ГО"
    ],
    
    # Спорт и туризм
    "SPORT": [
        "Спорт и фитнес",
        "Туризм и гостиницы"
    ]
}


def make_request(url: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Выполнить запрос к HH.ru API."""
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        time.sleep(DELAY)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️  Ошибка {response.status_code}: {url}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None


def fetch_professional_areas() -> List[Dict[str, Any]]:
    """Получить список профессиональных областей из HH.ru API."""
    url = f"{API_BASE}/professions"
    data = make_request(url)
    
    if data and "clusters" in data:
        return data["clusters"]
    return []


def fetch_vacancies_by_profession(profession_key: str, limit: int = 100) -> List[Dict]:
    """Получить вакансии по профессии."""
    url = f"{API_BASE}/vacancies"
    params = {
        "professional_role": profession_key,
        "per_page": limit
    }
    
    data = make_request(url, params)
    if data and "items" in data:
        return data["items"]
    return []


def extract_skills_from_vacancies(vacancies: List[Dict]) -> Dict[str, Set[str]]:
    """Извлечь навыки из вакансий."""
    skills = {
        "hard_skills": set(),
        "soft_skills": set(),
        "tools": set()
    }
    
    for vacancy in vacancies:
        # Ключевые навыки
        if "key_skills" in vacancy and vacancy["key_skills"]:
            for skill in vacancy["key_skills"]:
                if "name" in skill:
                    skills["hard_skills"].add(skill["name"])
        
        # Описание (можно парсить)
        if "description" in vacancy and vacancy["description"]:
            desc = vacancy["description"].lower()
            # Здесь можно добавить парсинг описания
            
    return skills


def categorize_profession(profession_name: str, profession_key: str) -> tuple[str, str]:
    """Определить домен и сферу для профессии."""
    name_lower = profession_name.lower()
    
    # IT
    if any(kw in name_lower for kw in ['программист', 'разработчик', 'developer', 'python', 'java', '1c', 'веб', 'frontend', 'backend', 'devops', 'qa', 'тестировщик', 'аналитик данных', 'ml', 'ai']):
        return "IT", "Разработка ПО"
    if any(kw in name_lower for kw in ['администратор', 'сисадмин', 'безопасность', 'сеть']):
        return "IT", "Системное администрирование"
    
    # Продажи
    if any(kw in name_lower for kw in ['продаж', 'менеджер по продажам', 'торговый представитель', 'активные продажи']):
        return "Продажи", "Активные продажи"
    if any(kw in name_lower for kw in ['рознич', 'продавец', 'кассир']):
        return "Розничная торговля", "Торговый зал"
    if any(kw in name_lower for kw in ['клиент', 'сопровождение', 'поддержка']):
        return "Продажи", "Работа с клиентами"
    
    # Маркетинг
    if any(kw in name_lower for kw in ['маркет', 'smm', 'контент', 'таргет', 'seo', 'контекст']):
        return "Маркетинг", "Digital маркетинг"
    if any(kw in name_lower for kw in ['pr', 'связи с общественностью']):
        return "СМИ", "PR"
    
    # Финансы
    if any(kw in name_lower for kw in ['бухгалтер', 'финансов', 'аудитор', 'налог']):
        return "Финансы", "Бухгалтерия"
    if any(kw in name_lower for kw in ['банк', 'кредит', 'финансовый советник']):
        return "Финансы", "Банковское дело"
    
    # HR
    if any(kw in name_lower for kw in ['рекрутер', 'hr', 'кадр', 'персонал', 'обучение']):
        return "Управление персоналом", "Рекрутинг"
    
    # Производство
    if any(kw in name_lower for kw in ['инженер', 'технолог', 'производств', 'конструктор']):
        return "Производство", "Инженерия"
    
    # Логистика
    if any(kw in name_lower for kw in ['логист', 'склад', 'закуп', 'вэд', 'снабжен']):
        return "Логистика", "Складская логистика"
    
    # Медицина
    if any(kw in name_lower for kw in ['врач', 'медсестр', 'фармацевт', 'стоматолог']):
        return "Медицина", "Лечебное дело"
    
    # Образование
    if any(kw in name_lower for kw in ['учитель', 'преподаватель', 'репетитор', 'воспитатель']):
        return "Образование", "Преподавание"
    
    # Строительство
    if any(kw in name_lower for kw in ['строитель', 'прораб', 'сметчик', 'архитектор', 'геодезист']):
        return "Строительство", "Строительно-монтажные работы"
    
    # HORECA
    if any(kw in name_lower for kw in ['повар', 'официант', 'бармен', 'шеф', 'кондитер']):
        return "Рестораны", "Кухня"
    
    # Красота
    if any(kw in name_lower for kw in ['парикмахер', 'косметолог', 'маникюр', 'визаж', 'стилист']):
        return "Красота", "Парикмахерское искусство"
    
    # Юриспруденция
    if any(kw in name_lower for kw in ['юрист', 'адвокат', 'нотариус', 'правовед']):
        return "Юриспруденция", "Корпоративное право"
    
    # Административный
    if any(kw in name_lower for kw in ['офис', 'секретар', 'администратор', 'делопроизвод']):
        return "Административный", "Офис-менеджмент"
    
    # Творчество
    if any(kw in name_lower for kw in ['дизайнер', 'графический', 'иллюстратор', 'фотограф']):
        return "Творчество", "Графический дизайн"
    
    # СМИ
    if any(kw in name_lower for kw in ['журналист', 'редактор', 'копирайтер']):
        return "СМИ", "Журналистика"
    
    # Транспорт
    if any(kw in name_lower for kw in ['водитель', 'диспетчер', 'логист транспорт']):
        return "Транспорт", "Водители"
    
    return "Другое", "Другое"


def build_professions_catalog() -> Dict[str, Any]:
    """Построить каталог профессий."""
    print("🔍 Сбор профессий из HH.ru API...")
    
    # Получаем профессиональные области
    areas = fetch_professional_areas()
    
    professions = {}
    
    if areas:
        for area in areas:
            if "clusters" in area:
                for cluster in area["clusters"]:
                    if "items" in cluster:
                        for item in cluster["items"]:
                            prof_key = item.get("key", "")
                            prof_name = item.get("name", "")
                            
                            if prof_key and prof_name:
                                # Определяем категорию
                                domain, sphere = categorize_profession(prof_name, prof_key)
                                
                                # Получаем вакансии для анализа навыков
                                print(f"  📊 Анализ: {prof_name}")
                                vacancies = fetch_vacancies_by_profession(prof_key, limit=50)
                                skills = extract_skills_from_vacancies(vacancies)
                                
                                # Считаем статистику
                                avg_salary_from = []
                                avg_salary_to = []
                                areas_count = defaultdict(int)
                                
                                for vac in vacancies:
                                    if "salary" in vac and vac["salary"]:
                                        if vac["salary"].get("from"):
                                            avg_salary_from.append(vac["salary"]["from"])
                                        if vac["salary"].get("to"):
                                            avg_salary_to.append(vac["salary"]["to"])
                                    
                                    if "area" in vac and vac["area"]:
                                        areas_count[vac["area"].get("name", "")] += 1
                                
                                # Сохраняем профессию
                                professions[prof_key] = {
                                    "key": prof_key,
                                    "name": prof_name,
                                    "domain": domain,
                                    "sphere": sphere,
                                    "vacancies_count": len(vacancies),
                                    "avg_salary_from": int(sum(avg_salary_from) / len(avg_salary_from)) if avg_salary_from else None,
                                    "avg_salary_to": int(sum(avg_salary_to) / len(avg_salary_to)) if avg_salary_to else None,
                                    "hard_skills": sorted(list(skills["hard_skills"]))[:50],
                                    "tools": sorted(list(skills["tools"]))[:30],
                                    "soft_skills": sorted(list(skills["soft_skills"]))[:20],
                                    "top_areas": dict(sorted(areas_count.items(), key=lambda x: x[1], reverse=True)[:5])
                                }
                                
                                time.sleep(0.3)
    
    return {
        "domains": DOMAINS,
        "areas": PROFESSIONAL_AREAS,
        "professions": professions,
        "total": len(professions)
    }


def save_catalog(catalog: Dict[str, Any], filepath: Path) -> None:
    """Сохранить каталог в JSON."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"✅ Каталог сохранен: {filepath}")


def main():
    """Главная функция."""
    print("=" * 60)
    print("📚 HH.ru — Каталог профессий")
    print("=" * 60)
    
    # Строим каталог
    catalog = build_professions_catalog()
    
    # Сохраняем
    output_file = DATA_DIR / "professions_catalog.json"
    save_catalog(catalog, output_file)
    
    # Статистика
    print("\n" + "=" * 60)
    print("📊 Статистика:")
    print(f"  Всего профессий: {catalog['total']}")
    print(f"  Доменов: {len(catalog['domains'])}")
    
    # По доменам
    domain_counts = defaultdict(int)
    for prof in catalog["professions"].values():
        domain_counts[prof["domain"]] += 1
    
    print("\n  По доменам:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"    {domain}: {count}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
