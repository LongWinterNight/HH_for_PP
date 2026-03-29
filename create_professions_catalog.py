#!/usr/bin/env python3
"""
Скрипт для создания каталога профессий на основе данных из БД.
Группирует вакансии по профессиям, извлекает навыки и создает детальные карточки.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import defaultdict
import re

# Пути
PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "data" / "hh_vacancies.db"
OUTPUT_FILE = PROJECT_ROOT / "data" / "professions_catalog.json"

# =============================================================================
# Справочник профессий с категориями
# =============================================================================

# Домены (сферы деятельности)
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
    "OTHER": "Другое"
}

# Профессиональные области (подкатегории) по доменам
PROFESSIONAL_AREAS = {
    "IT": [
        "Разработка ПО",
        "Системное администрирование",
        "Информационная безопасность",
        "Тестирование (QA)",
        "Аналитика данных",
        "DevOps и SRE",
        "Веб-разработка",
        "Мобильная разработка",
        "1С программирование",
        "Искусственный интеллект и ML",
        "Проектирование и архитектура"
    ],
    "SALES": [
        "Активные продажи (B2B)",
        "Активные продажи (B2C)",
        "Розничные продажи",
        "Оптовые продажи",
        "Работа с клиентами (Account Management)",
        "Торговые представители",
        "Менеджеры по продажам",
        "Руководители отдела продаж"
    ],
    "MARKETING": [
        "Digital маркетинг",
        "SMM и социальные сети",
        "Контент-маркетинг",
        "Бренд-менеджмент",
        "Маркетинговая аналитика",
        "Event маркетинг",
        "Performance маркетинг",
        "SEO и SEM"
    ],
    "FINANCE": [
        "Бухгалтерия и учет",
        "Финансовый анализ",
        "Аудит",
        "Налоговое планирование",
        "Банковское дело",
        "Страхование",
        "Инвестиции"
    ],
    "HR": [
        "Рекрутинг и подбор персонала",
        "Обучение и развитие",
        "HR-брендинг",
        "Оплата труда и льготы",
        "Кадровое делопроизводство",
        "HR-директора"
    ],
    "PRODUCTION": [
        "Инженерия и конструирование",
        "Технология производства",
        "Контроль качества",
        "Снабжение",
        "Операционное производство",
        "Автоматизация производства"
    ],
    "LOGISTICS": [
        "Складская логистика",
        "Транспортная логистика",
        "ВЭД и таможенное оформление",
        "Закупки и снабжение",
        "Дистрибуция",
        "Управление цепями поставок"
    ],
    "MEDICINE": [
        "Лечебное дело (терапевты)",
        "Лечебное дело (хирурги)",
        "Лечебное дело (узкие специалисты)",
        "Сестринское дело",
        "Фармация",
        "Стоматология",
        "Диагностика и лаборатория"
    ],
    "EDUCATION": [
        "Преподавание в школе",
        "Преподавание в ВУЗе",
        "Репетиторство",
        "Методическая работа",
        "Научная деятельность",
        "Дошкольное образование"
    ],
    "CONSTRUCTION": [
        "Проектирование зданий",
        "Строительно-монтажные работы",
        "Сметное дело",
        "Геодезия",
        "Архитектура и дизайн",
        "Управление строительством"
    ],
    "RETAIL": [
        "Торговый зал",
        "Кассиры",
        "Мерчандайзинг",
        "Управление магазином",
        "Закупки ритейл"
    ],
    "HORECA": [
        "Кухня (повара)",
        "Зал (официанты)",
        "Бар",
        "Управление рестораном",
        "Кондитерское дело"
    ],
    "BEAUTY": [
        "Парикмахерское искусство",
        "Косметология",
        "Маникюр и педикюр",
        "Визаж и стилистика",
        "Фитнес-тренер"
    ],
    "LEGAL": [
        "Корпоративное право",
        "Судебная практика",
        "Налоговое право",
        "Патентное право",
        "Юрисконсульты"
    ],
    "ADMIN": [
        "Офис-менеджмент",
        "Секретариат",
        "Делопроизводство",
        "АХО",
        "Помощники руководителя"
    ],
    "CREATIVE": [
        "Графический дизайн",
        "Веб-дизайн и UX/UI",
        "Иллюстрация",
        "Фотография",
        "Видеопроизводство",
        "3D моделирование"
    ],
    "MEDIA": [
        "Журналистика",
        "Редактура",
        "Копирайтинг",
        "PR и коммуникации",
        "Радиовещание"
    ],
    "TRANSPORT": [
        "Водители легкового транспорта",
        "Водители грузового транспорта",
        "Диспетчеры",
        "Связь и телеком",
        "Логисты транспортные"
    ],
    "AGRO": [
        "Агрономия",
        "Животноводство",
        "Механизация",
        "Агроинженерия"
    ],
    "SECURITY": [
        "Охрана",
        "Корпоративная безопасность",
        "ЧС и ГО"
    ],
    "SPORT": [
        "Спорт и фитнес (тренеры)",
        "Туризм и гостиницы",
        "Спорт высших достижений"
    ]
}


def normalize_profession_name(name: str) -> str:
    """Нормализовать название профессии."""
    # Убираем лишние слова
    patterns_to_remove = [
        r'\(.*?\)',  # скобки
        r'\[.*?\]',  # квадратные скобки
        r'м/ж',  # м/ж
        r'junior', r'middle', r'senior', r'lead', r'head',  # уровни
        r'ведущий', r'старший', r'младший',  # уровни рус
    ]
    
    result = name
    for pattern in patterns_to_remove:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Убираем двойные пробелы
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result


def categorize_profession(profession_name: str) -> tuple[str, str]:
    """
    Определить домен и сферу для профессии.
    Возвращает (domain_key, sphere_name)
    """
    name_lower = profession_name.lower()
    
    # IT - расширенные ключевые слова
    it_dev_keywords = ['программист', 'разработчик', 'developer', 'python', 'java', 'javascript', 'php', 'c++', 'golang', 'rust', 'scala', '1c', 'веб', 'frontend', 'backend', 'fullstack', 'full-stack', 'html', 'верстальщик']
    it_test_keywords = ['тестировщик', 'qa', 'test engineer', 'инженер по тестированию', 'тестирование', 'ручное тестирование', 'автотест']
    it_devops_keywords = ['devops', 'sre', 'kubernetes', 'docker', 'ci/cd']
    it_admin_keywords = ['администратор', 'сисадмин', 'системный администратор', 'network', 'сеть', 'help desk', 'техническая поддержка']
    it_data_keywords = ['аналитик данных', 'data scientist', 'ml engineer', 'machine learning', 'ai', 'нейросет', 'deep learning']
    it_security_keywords = ['информационная безопасность', 'security', 'пентест', 'кибербезопасность']
    it_analyst_keywords = ['системный аналитик', 'бизнес аналитик', 'бизнес-аналитик', 'it-аналитик', 'аналитик 1с', 'technical writer', 'технический писатель']
    it_pm_keywords = ['project manager', 'продакт', 'product manager', 'it director', 'cto', 'технический директор', 'it-директор', 'руководитель it']
    it_design_keywords = ['ui/ux', 'ux/ui', 'дизайнер интерфейсов', 'web дизайнер', 'graphic designer']
    
    # Сначала проверяем IT (самый большой домен)
    if any(kw in name_lower for kw in it_dev_keywords):
        return "IT", "Разработка ПО"
    if any(kw in name_lower for kw in it_test_keywords):
        return "IT", "Тестирование (QA)"
    if any(kw in name_lower for kw in it_devops_keywords):
        return "IT", "DevOps и SRE"
    if any(kw in name_lower for kw in it_admin_keywords):
        return "IT", "Системное администрирование"
    if any(kw in name_lower for kw in it_data_keywords):
        return "IT", "Аналитика данных"
    if any(kw in name_lower for kw in it_security_keywords):
        return "IT", "Информационная безопасность"
    if any(kw in name_lower for kw in it_analyst_keywords):
        return "IT", "Системная и бизнес аналитика"
    if any(kw in name_lower for kw in it_pm_keywords):
        return "IT", "Управление IT-проектами"
    if any(kw in name_lower for kw in it_design_keywords):
        return "IT", "IT-дизайн"
    if 'it' in name_lower or 'айти' in name_lower:
        return "IT", "Другое"
    
    # Продажи
    sales_active_keywords = ['активные продажи', 'холодные звонки', 'менеджер по продажам', 'торговый представитель', 'b2b продажи', 'продаж']
    sales_retail_keywords = ['продавец', 'кассир', 'рознич', 'торговый зал']
    sales_client_keywords = ['клиент', 'сопровождение клиентов', 'account manager', 'работа с клиентами']
    sales_head_keywords = ['руководитель отдела продаж', 'родп', 'директор по продажам']
    
    if any(kw in name_lower for kw in sales_active_keywords):
        return "SALES", "Активные продажи (B2B)"
    if any(kw in name_lower for kw in sales_retail_keywords):
        return "RETAIL", "Торговый зал"
    if any(kw in name_lower for kw in sales_client_keywords):
        return "SALES", "Работа с клиентами (Account Management)"
    if any(kw in name_lower for kw in sales_head_keywords):
        return "SALES", "Руководители отдела продаж"

    # Маркетинг
    marketing_digital_keywords = ['маркетолог', 'digital', 'интернет-маркетолог', 'таргет', 'контекст', 'seo', 'sem', 'директолог', 'яндекс директ', 'google ads', 'performance']
    marketing_smm_keywords = ['smm', 'социальные сети', 'instagram', 'telegram', 'vkontakte', 'тикток', 'tiktok', 'community manager']
    marketing_brand_keywords = ['бренд', 'product manager', 'продуктовый маркетолог', 'продюсер', 'brand']
    marketing_content_keywords = ['контент', 'копирайт', 'редактор', 'журналист', 'райтер', 'copywriter']
    marketing_pr_keywords = ['pr', 'пиар', 'пресс', 'связи с общественностью', 'public relations']
    marketing_email_keywords = ['email', 'рассылки', 'crm-маркетинг', 'email-маркетолог']
    marketing_analytics_keywords = ['маркетинговая аналитика', 'маркетолог аналитик']
    
    # Исключаем телемаркетинг (это продажи) и маркетплейсы (это продажи/логистика)
    is_telemarketing = 'телемаркет' in name_lower or 'телемаркетолог' in name_lower
    is_marketplace = 'маркетплейс' in name_lower or 'wildberries' in name_lower or 'ozon' in name_lower
    
    if is_telemarketing:
        return "SALES", "Активные продажи (B2B)"
    if is_marketplace:
        return "SALES", "Работа с клиентами (Account Management)"
    if any(kw in name_lower for kw in marketing_digital_keywords):
        return "MARKETING", "Digital маркетинг"
    if any(kw in name_lower for kw in marketing_smm_keywords):
        return "MARKETING", "SMM и социальные сети"
    if any(kw in name_lower for kw in marketing_brand_keywords):
        return "MARKETING", "Бренд-менеджмент"
    if any(kw in name_lower for kw in marketing_content_keywords):
        return "MARKETING", "Контент-маркетинг"
    if any(kw in name_lower for kw in marketing_pr_keywords):
        return "MARKETING", "PR и коммуникации"
    if any(kw in name_lower for kw in marketing_email_keywords):
        return "MARKETING", "Email маркетинг"
    if any(kw in name_lower for kw in marketing_analytics_keywords):
        return "MARKETING", "Маркетинговая аналитика"
    
    # Финансы
    finance_accounting_keywords = ['бухгалтер', 'главный бухгалтер', 'зам главного бухгалтера', 'первичная документация']
    finance_analyst_keywords = ['финансовый аналитик', 'финансовый директор', 'cfo']
    finance_audit_keywords = ['аудитор', 'внутренний аудит', 'внешний аудит']
    finance_bank_keywords = ['банк', 'банковский', 'кредит', 'ипотека']
    
    if any(kw in name_lower for kw in finance_accounting_keywords):
        return "Финансы и бухгалтерия", "Бухгалтерия и учет"
    if any(kw in name_lower for kw in finance_analyst_keywords):
        return "Финансы и бухгалтерия", "Финансовый анализ"
    if any(kw in name_lower for kw in finance_audit_keywords):
        return "Финансы и бухгалтерия", "Аудит"
    if any(kw in name_lower for kw in finance_bank_keywords):
        return "Финансы и бухгалтерия", "Банковское дело"
    
    # HR
    hr_recruit_keywords = ['рекрутер', 'it рекрутер', 'подбор персонала', 'hr менеджер', 'hr generalist', 'talent acquisition']
    hr_train_keywords = ['обучение', 'тренинг', 'корпоративное обучение', 'тренер', 'l&d', 'learning and development']
    hr_cadre_keywords = ['кадр', 'делопроизводство', 'отдел кадров']
    hr_hr_keywords = ['hr director', 'hrd', 'директор по персоналу', 'hr business partner', 'hrbp']
    
    if any(kw in name_lower for kw in hr_recruit_keywords):
        return "HR", "Рекрутинг и подбор персонала"
    if any(kw in name_lower for kw in hr_train_keywords):
        return "HR", "Обучение и развитие"
    if any(kw in name_lower for kw in hr_cadre_keywords):
        return "HR", "Кадровое делопроизводство"
    if any(kw in name_lower for kw in hr_hr_keywords):
        return "HR", "HR-менеджмент"
    
    # Управление и руководство (C-level, директора)
    management_keywords = ['директор', 'director', 'руководитель', 'head of', 'chief', 'ceo', 'cfo', 'coo', 'cto', 'cmo']
    if any(kw in name_lower for kw in management_keywords):
        # Если это IT - уже обработали выше
        # Если не IT - смотрим по контексту
        if 'персонал' in name_lower or 'hr' in name_lower:
            return "HR", "HR-менеджмент"
        elif 'развит' in name_lower:
            return "ADMIN", "Управление проектами"
        elif 'маркетин' in name_lower:
            return "MARKETING", "Бренд-менеджмент"
    
    # Производство
    prod_engineer_keywords = ['инженер', 'конструктор', 'проектировщик', 'механик']
    prod_tech_keywords = ['технолог', 'производств', 'manufacturing']
    prod_quality_keywords = ['контроль качества', 'qc', 'quality control']
    
    if any(kw in name_lower for kw in prod_engineer_keywords):
        return "Производство и технологии", "Инженерия и конструирование"
    if any(kw in name_lower for kw in prod_tech_keywords):
        return "Производство и технологии", "Технология производства"
    if any(kw in name_lower for kw in prod_quality_keywords):
        return "Производство и технологии", "Контроль качества"
    
    # Логистика
    logist_warehouse_keywords = ['склад', 'кладовщик', 'заведующий складом', 'логист склад']
    logist_transport_keywords = ['транспорт', 'доставка', 'логист транспорт']
    logist_ved_keywords = ['вэд', 'тамож', 'импорт', 'экспорт']
    logist_purchase_keywords = ['закуп', 'снабжен', 'procurement', 'buyer']
    
    if any(kw in name_lower for kw in logist_warehouse_keywords):
        return "Логистика и ВЭД", "Складская логистика"
    if any(kw in name_lower for kw in logist_transport_keywords):
        return "Логистика и ВЭД", "Транспортная логистика"
    if any(kw in name_lower for kw in logist_ved_keywords):
        return "Логистика и ВЭД", "ВЭД и таможенное оформление"
    if any(kw in name_lower for kw in logist_purchase_keywords):
        return "Логистика и ВЭД", "Закупки и снабжение"
    
    # Медицина
    med_doctor_keywords = ['врач', 'терапевт', 'хирург', 'педиатр', 'кардиолог', 'невролог', 'онколог']
    med_nurse_keywords = ['медсестр', 'медбрат']
    med_pharma_keywords = ['фармацевт', 'провизор', 'аптек']
    med_stom_keywords = ['стоматолог', 'зубной']
    
    if any(kw in name_lower for kw in med_doctor_keywords):
        return "Медицина и фармацевтика", "Лечебное дело (терапевты)"
    if any(kw in name_lower for kw in med_nurse_keywords):
        return "Медицина и фармацевтика", "Сестринское дело"
    if any(kw in name_lower for kw in med_pharma_keywords):
        return "Медицина и фармацевтика", "Фармация"
    if any(kw in name_lower for kw in med_stom_keywords):
        return "Медицина и фармацевтика", "Стоматология"
    
    # Образование
    edu_school_keywords = ['учитель', 'преподаватель', 'школа', 'классный руководитель']
    edu_university_keywords = ['преподаватель вуза', 'доцент', 'профессор', 'университет']
    edu_tutor_keywords = ['репетитор']
    edu_preschool_keywords = ['воспитатель', 'дошколь', 'детский сад']
    
    if any(kw in name_lower for kw in edu_school_keywords):
        return "Образование и наука", "Преподавание в школе"
    if any(kw in name_lower for kw in edu_university_keywords):
        return "Образование и наука", "Преподавание в ВУЗе"
    if any(kw in name_lower for kw in edu_tutor_keywords):
        return "Образование и наука", "Репетиторство"
    if any(kw in name_lower for kw in edu_preschool_keywords):
        return "Образование и наука", "Дошкольное образование"
    
    # Строительство
    constr_build_keywords = ['строитель', 'прораб', 'мастер', 'бригадир']
    constr_smeta_keywords = ['сметчик', 'смета']
    constr_geo_keywords = ['геодезист']
    constr_arch_keywords = ['архитектор', 'дизайнер интерьера']
    
    if any(kw in name_lower for kw in constr_build_keywords):
        return "Строительство и недвижимость", "Строительно-монтажные работы"
    if any(kw in name_lower for kw in constr_smeta_keywords):
        return "Строительство и недвижимость", "Сметное дело"
    if any(kw in name_lower for kw in constr_geo_keywords):
        return "Строительство и недвижимость", "Геодезия"
    if any(kw in name_lower for kw in constr_arch_keywords):
        return "Строительство и недвижимость", "Архитектура и дизайн"
    
    # HORECA
    horeca_kitchen_keywords = ['повар', 'шеф-повар', 'су-шеф', 'кухня', 'кондитер']
    horeca_hall_keywords = ['официант', 'хостес', 'администратор зала']
    horeca_bar_keywords = ['бармен', 'бариста']
    
    if any(kw in name_lower for kw in horeca_kitchen_keywords):
        return "Рестораны и общественное питание", "Кухня (повара)"
    if any(kw in name_lower for kw in horeca_hall_keywords):
        return "Рестораны и общественное питание", "Зал (официанты)"
    if any(kw in name_lower for kw in horeca_bar_keywords):
        return "Рестораны и общественное питание", "Бар"
    
    # Красота
    beauty_hair_keywords = ['парикмахер', 'стилист', 'колорист', 'барбер']
    beauty_cosmeto_keywords = ['косметолог', 'эстетист']
    beauty_nail_keywords = ['маникюр', 'педикюр', 'мастер ногтевого сервиса', 'наращивание']
    beauty_makeup_keywords = ['визаж', 'визажист', 'makeup']
    beauty_fit_keywords = ['фитнес', 'тренер', 'инструктор']
    
    if any(kw in name_lower for kw in beauty_hair_keywords):
        return "Красота и фитнес", "Парикмахерское искусство"
    if any(kw in name_lower for kw in beauty_cosmeto_keywords):
        return "Красота и фитнес", "Косметология"
    if any(kw in name_lower for kw in beauty_nail_keywords):
        return "Красота и фитнес", "Маникюр и педикюр"
    if any(kw in name_lower for kw in beauty_makeup_keywords):
        return "Красота и фитнес", "Визаж и стилистика"
    if any(kw in name_lower for kw in beauty_fit_keywords):
        return "Красота и фитнес", "Фитнес-тренер"
    
    # Юриспруденция
    legal_corp_keywords = ['юрист', 'юрисконсульт', 'правовед', 'корпоративный юрист']
    legal_court_keywords = ['адвокат', 'суд', 'судебный']
    legal_notary_keywords = ['нотариус']
    
    if any(kw in name_lower for kw in legal_corp_keywords):
        return "Юриспруденция", "Корпоративное право"
    if any(kw in name_lower for kw in legal_court_keywords):
        return "Юриспруденция", "Судебная практика"
    if any(kw in name_lower for kw in legal_notary_keywords):
        return "Юриспруденция", "Патентное право"
    
    # Административный
    admin_office_keywords = ['офис', 'офис-менеджер', 'администратор офиса']
    admin_secretary_keywords = ['секретар', 'ассистент', 'помощник']
    admin_doc_keywords = ['делопроизвод', 'документооборот']
    
    if any(kw in name_lower for kw in admin_office_keywords):
        return "Административный персонал", "Офис-менеджмент"
    if any(kw in name_lower for kw in admin_secretary_keywords):
        return "Административный персонал", "Секретариат"
    if any(kw in name_lower for kw in admin_doc_keywords):
        return "Административный персонал", "Делопроизводство"
    
    # Творчество
    creative_design_keywords = ['дизайнер', 'графический дизайнер', 'web дизайнер', 'ux', 'ui']
    creative_photo_keywords = ['фотограф', 'видеограф']
    creative_3d_keywords = ['3d', 'трехмерный', 'моделлер']
    
    if any(kw in name_lower for kw in creative_design_keywords):
        return "Творчество и дизайн", "Графический дизайн"
    if any(kw in name_lower for kw in creative_photo_keywords):
        return "Творчество и дизайн", "Фотография"
    if any(kw in name_lower for kw in creative_3d_keywords):
        return "Творчество и дизайн", "3D моделирование"
    
    # СМИ
    media_journal_keywords = ['журналист', 'корреспондент', 'репортер']
    media_editor_keywords = ['редактор', 'выпускающий редактор']
    media_copy_keywords = ['копирайтер', 'рерайтер', 'контент']
    media_pr_keywords = ['pr', 'пиар', 'пресс']
    
    if any(kw in name_lower for kw in media_journal_keywords):
        return "СМИ и издательское дело", "Журналистика"
    if any(kw in name_lower for kw in media_editor_keywords):
        return "СМИ и издательское дело", "Редактура"
    if any(kw in name_lower for kw in media_copy_keywords):
        return "СМИ и издательское дело", "Копирайтинг"
    if any(kw in name_lower for kw in media_pr_keywords):
        return "СМИ и издательское дело", "PR и коммуникации"
    
    # Транспорт
    transport_driver_keywords = ['водитель', 'шофер', 'курьер']
    transport_dispatcher_keywords = ['диспетчер']
    
    if any(kw in name_lower for kw in transport_driver_keywords):
        return "Транспорт и связь", "Водители легкового транспорта"
    if any(kw in name_lower for kw in transport_dispatcher_keywords):
        return "Транспорт и связь", "Диспетчеры"
    
    # По умолчанию
    return "Другое", "Другое"


def build_professions_from_db() -> Dict[str, Any]:
    """Построить каталог профессий из БД."""
    print("🔍 Чтение данных из БД...")
    
    # Читаем данные из БД
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{DB_PATH}")
    
    try:
        df = pd.read_sql("SELECT * FROM vacancies", engine)
    except Exception as e:
        print(f"❌ Ошибка чтения БД: {e}")
        return {"professions": {}, "total": 0}
    
    print(f"📊 Вакансий в БД: {len(df)}")
    
    # Группируем по профессиям
    professions = defaultdict(lambda: {
        "vacancies": [],
        "hard_skills": set(),
        "tools": set(),
        "soft_skills": set(),
        "salaries": [],
        "areas": defaultdict(int),
        "employers": set()
    })
    
    for _, row in df.iterrows():
        # Нормализуем название
        vacancy_name = row.get('vacancy_name', '')
        if not vacancy_name:
            continue
        
        # Определяем категорию
        domain, sphere = categorize_profession(vacancy_name)
        
        # Создаем ключ профессии (название + категория)
        prof_key = f"{domain}|{sphere}|{vacancy_name[:80]}"
        
        # Добавляем вакансию
        prof = professions[prof_key]
        prof["vacancies"].append({
            "id": row.get('vacancy_id', ''),
            "title": vacancy_name[:100],
            "company": row.get('employer_name', '')[:50] if pd.notna(row.get('employer_name')) else "Не указано",
            "salary": int(row.get('salary_from', 0)) if pd.notna(row.get('salary_from')) else None,
            "area": row.get('area', '')[:50] if pd.notna(row.get('area')) else "Не указано",
            "url": row.get('vacancy_url', '')
        })
        
        # Собираем навыки
        for col, skill_set in [('hard_skills', prof["hard_skills"]),
                               ('tools', prof["tools"]),
                               ('soft_skills', prof["soft_skills"])]:
            if col in row and isinstance(row[col], str):
                skills = [s.strip() for s in row[col].split(',') if s.strip()]
                skill_set.update(skills)
        
        # Собираем зарплаты
        if pd.notna(row.get('salary_from')):
            prof["salaries"].append(row['salary_from'])
        
        # Собираем регионы
        if pd.notna(row.get('area')):
            prof["areas"][row['area']] += 1
        
        # Работодатели
        if pd.notna(row.get('employer_name')):
            prof["employers"].add(row['employer_name'])
    
    # Форматируем результат
    result = {}
    for prof_key, prof in professions.items():
        parts = prof_key.split('|')
        domain = parts[0]
        sphere = parts[1]
        name = parts[2] if len(parts) > 2 else prof_key
        
        # Считаем среднюю зарплату
        avg_salary = int(sum(prof["salaries"]) / len(prof["salaries"])) if prof["salaries"] else None
        
        # Все уникальные навыки
        all_skills = list(prof["hard_skills"]) + list(prof["tools"])
        top_skills = all_skills[:5] if len(all_skills) >= 5 else all_skills
        
        # Топ регионов
        top_areas = dict(sorted(prof["areas"].items(), key=lambda x: x[1], reverse=True)[:5])
        
        # Топ работодателей
        top_employers = list(prof["employers"])[:10]
        
        result[prof_key] = {
            "key": prof_key,
            "name": name,
            "domain": domain,
            "sphere": sphere,
            "vacancies_count": len(prof["vacancies"]),
            "avg_salary": avg_salary,
            "top_skills": top_skills,
            "hard_skills_count": len(prof["hard_skills"]),
            "tools_count": len(prof["tools"]),
            "soft_skills_count": len(prof["soft_skills"]),
            "total_skills": len(all_skills),
            "hard_skills": sorted(list(prof["hard_skills"]))[:30],
            "tools": sorted(list(prof["tools"]))[:20],
            "soft_skills": sorted(list(prof["soft_skills"]))[:15],
            "top_areas": top_areas,
            "top_employers": top_employers,
            "sample_vacancies": prof["vacancies"][:10]  # Первые 10 вакансий
        }
    
    return {
        "domains": DOMAINS,
        "areas": PROFESSIONAL_AREAS,
        "professions": result,
        "total": len(result)
    }


def main():
    """Главная функция."""
    print("=" * 60)
    print("📚 Создание каталога профессий")
    print("=" * 60)
    
    # Строим каталог
    catalog = build_professions_from_db()
    
    # Сохраняем
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Каталог сохранен: {OUTPUT_FILE}")
    
    # Статистика
    print("\n" + "=" * 60)
    print("📊 Статистика:")
    print(f"  Всего профессий: {catalog['total']}")
    print(f"  Доменов: {len(catalog['domains'])}")
    
    # По доменам
    domain_counts = defaultdict(int)
    for prof in catalog["professions"].values():
        domain_counts[prof["domain"]] += 1
    
    print("\n  По доменам (топ-10):")
    for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"    {domain}: {count}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
