"""
Минимальная версия веб-приложения HH.ru Analytics.
"""

from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import sys
from datetime import datetime
from typing import Optional
from collections import defaultdict

# Пути
WEB_DIR = Path(__file__).parent  # web/app
WEB_ROOT = WEB_DIR.parent  # web
PROJECT_ROOT = WEB_ROOT.parent  # hh_analytics
STATIC_DIR = WEB_ROOT / "static"  # web/static

sys.path.insert(0, str(PROJECT_ROOT))

# Логгер
from src.utils import get_logger
logger = get_logger(__name__)

# Приложение
app = FastAPI(title="HH.ru Analytics", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Статика
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

# Состояние парсера
parser_state = {
    "is_running": False,
    "status": "idle",
    "progress": 0,
    "current_keyword": "",
    "current_page": 0,
    "total_pages": 0,
    "vacancies_collected": 0,
    "keywords": [],
    "error_message": None,
    "started_at": None,
    "completed_at": None,
    "stop_requested": False  # Флаг для остановки
}

# =============================================================================
# Endpoints
# =============================================================================

@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/favicon.ico")
def favicon():
    """Возвращает favicon.ico или заглушку."""
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    # Возвращаем пустую заглушку если favicon нет
    from fastapi.responses import Response
    return Response(content="", status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools():
    """Заглушка для Chrome DevTools."""
    from fastapi.responses import JSONResponse
    return JSONResponse(content={})

@app.get("/analytics")
def analytics_page():
    """Отдельная страница аналитики."""
    return FileResponse(STATIC_DIR / "analytics.html")

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/vacancies")
def get_vacancies(
    page: int = 1,
    per_page: int = 20,
    search: str = "",
    area: str = "",
    experience: str = "",
    skill: str = "",
    salary_only: bool = False
):
    from src.storage import VacancyStorage
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {"total": 0, "page": page, "items": []}

        # Применяем фильтры
        if search:
            df = df[df["vacancy_name"].str.contains(search, case=False, na=False)]
        
        if area:
            df = df[df["area"].str.contains(area, case=False, na=False)]
        
        if experience:
            df = df[df["experience"] == experience]
        
        if skill:
            # Поиск по навыкам (hard_skills, tools, soft_skills)
            skill_lower = skill.lower()
            mask = (
                df["hard_skills"].str.contains(skill_lower, case=False, na=False) |
                df["tools"].str.contains(skill_lower, case=False, na=False) |
                df["soft_skills"].str.contains(skill_lower, case=False, na=False)
            )
            df = df[mask]
        
        if salary_only:
            df = df[df["salary_from"].notna()]

        total = len(df)
        start = (page - 1) * per_page
        df_page = df.iloc[start:start + per_page]

        items = []
        for _, row in df_page.iterrows():
            item = {}
            for col in df.columns:
                val = row.get(col)
                if pd.isna(val):
                    val = None
                elif hasattr(val, 'isoformat'):
                    val = str(val)
                else:
                    val = val
                item[col] = val
            items.append(item)

        return {"total": total, "page": page, "items": items}
    finally:
        storage.close()

@app.get("/api/dashboard")
def get_dashboard():
    """Дашборд с расширенной статистикой."""
    from src.storage import VacancyStorage
    import pandas as pd
    import math

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {
                "total_vacancies": 0,
                "total_skills": 0,
                "avg_salary": None,
                "recent_vacancies": [],
                "top_skills": [],
                "vacancies_by_currency": {},
                "vacancies_by_area": {},
                "salary_trend": []
            }

        def get_top_skills(column, limit=10):
            counts = {}
            for s in column.dropna():
                if isinstance(s, str):
                    for skill in s.split(","):
                        skill = skill.strip()
                        if skill:
                            counts[skill] = counts.get(skill, 0) + 1
            return [{"name": k, "value": v} for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]]

        def safe_value(val):
            """Преобразует NaN/None в None для JSON-сериализации."""
            if val is None:
                return None
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return None
            return val

        top_skills = get_top_skills(df["hard_skills"], 10) if "hard_skills" in df.columns else []

        # Недавние вакансии с валютами
        recent = df.sort_values(by="published_at", ascending=False).head(5) if "published_at" in df.columns else df.head(5)
        recent_vacancies = []
        for _, row in recent.iterrows():
            recent_vacancies.append({
                "name": str(row.get("vacancy_name", ""))[:50] if pd.notna(row.get("vacancy_name")) else "",
                "company": str(row.get("employer_name", ""))[:30] if pd.notna(row.get("employer_name")) else "",
                "area": str(row.get("area", "")) if pd.notna(row.get("area")) else "",
                "salary": safe_value(row.get("salary_from")),
                "currency": row.get("salary_currency", "RUB") if pd.notna(row.get("salary_currency")) else "RUB"
            })

        # Статистика по зарплате
        salary_df = df[df["salary_from"].notna()] if "salary_from" in df.columns else pd.DataFrame()
        avg_salary = None
        if not salary_df.empty:
            mean_val = salary_df["salary_from"].mean()
            avg_salary = safe_value(mean_val)

        # Распределение по валютам
        vacancies_by_currency = {}
        if "salary_currency" in df.columns:
            currency_counts = df["salary_currency"].value_counts().to_dict()
            for currency, count in currency_counts.items():
                curr_df = df[(df["salary_currency"] == currency) & (df["salary_from"].notna())]
                if not curr_df.empty:
                    vacancies_by_currency[currency] = {
                        "count": count,
                        "avg_salary": float(curr_df["salary_from"].mean())
                    }

        # Топ регионов
        vacancies_by_area = {}
        if "area" in df.columns:
            vacancies_by_area = df["area"].value_counts().head(5).to_dict()

        # Тренд зарплат по датам (по неделям)
        salary_trend = []
        if "published_at" in df.columns and "salary_from" in df.columns:
            df_with_dates = df[df["published_at"].notna() & df["salary_from"].notna()].copy()
            if not df_with_dates.empty:
                df_with_dates["published_at"] = pd.to_datetime(df_with_dates["published_at"])
                # Исправляем warning - убираем timezone перед конвертацией
                df_with_dates["published_at"] = df_with_dates["published_at"].dt.tz_localize(None)
                df_with_dates["week"] = df_with_dates["published_at"].dt.to_period("W").apply(lambda r: r.start_time)
                weekly = df_with_dates.groupby("week")["salary_from"].mean().reset_index()
                for _, row in weekly.tail(8).iterrows():
                    salary_trend.append({
                        "date": str(row["week"].date()),
                        "avg_salary": float(row["salary_from"])
                    })

        return {
            "total_vacancies": len(df),
            "total_skills": int(df["skill_count"].sum()) if "skill_count" in df.columns and pd.notna(df["skill_count"].sum()) else 0,
            "avg_salary": avg_salary,
            "recent_vacancies": recent_vacancies,
            "top_skills": top_skills,
            "vacancies_by_currency": vacancies_by_currency,
            "vacancies_by_area": vacancies_by_area,
            "salary_trend": salary_trend
        }
    finally:
        storage.close()

@app.get("/api/analytics/advanced")
def get_analytics():
    """Расширенная аналитика + распределение."""
    from src.storage import VacancyStorage
    from src.advanced_analyzer import AdvancedAnalytics
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {
                "technologies": {},
                "hard_skills": {},
                "soft_skills": {},
                "salary_stats": {},
                "total_vacancies": 0
            }

        analytics = AdvancedAnalytics(df)
        
        # Получаем упрощенные данные по навыкам (только названия и количество)
        tech_summary = analytics.compute_technology_summary()
        hard_summary = analytics.compute_hard_skills_summary()
        soft_summary = analytics.compute_soft_skills_summary()
        
        # Преобразуем в простой формат {навык: количество}
        def simplify_skills(data):
            if not data:
                return {}
            result = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    # Если это группа с count
                    result[key] = value.get("count", 0)
                else:
                    # Если это просто число
                    result[key] = value
            return result
        
        # Статистика по зарплате
        salary_stats = {}
        if "salary_from" in df.columns:
            salary_df = df[df["salary_from"].notna()]
            if not salary_df.empty:
                salary_stats = {
                    "min": float(salary_df["salary_from"].min()),
                    "max": float(salary_df["salary_from"].max()),
                    "median": float(salary_df["salary_from"].median()),
                    "avg": float(salary_df["salary_from"].mean())
                }

        return {
            "technologies": simplify_skills(tech_summary),
            "hard_skills": simplify_skills(hard_summary),
            "soft_skills": simplify_skills(soft_summary),
            "salary_stats": salary_stats,
            "total_vacancies": len(df)
        }
    finally:
        storage.close()

@app.get("/api/analytics/distribution")
def get_distribution():
    """Распределение вакансий по категориям для графиков с конвертацией валют."""
    from src.storage import VacancyStorage
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {
                "experience": {},
                "employment": {},
                "salary_distribution": {},
                "top_areas": {},
                "salary_stats": {},
                "salary_stats_kzt": {},
                "salary_stats_usd": {},
                "currencies": {}
            }

        # Распределение по опыту
        experience_counts = {}
        if "experience" in df.columns:
            experience_counts = df["experience"].value_counts().to_dict()

        # Распределение по занятости
        employment_counts = {}
        if "employment" in df.columns:
            employment_counts = df["employment"].value_counts().to_dict()

        # Курсы валют (примерные)
        EXCHANGE_RATES = {
            "RUB": 1.0,
            "KZT": 0.18,      # 1 KZT = 0.18 RUB
            "UZS": 0.0072,    # 1 UZS = 0.0072 RUB
            "BYN": 28.0,      # 1 BYN = 28 RUB
            "USD": 92.0,      # 1 USD = 92 RUB
            "EUR": 100.0,     # 1 EUR = 100 RUB
        }
        
        def convert_to_rub(row):
            salary = row.get("salary_from")
            currency = row.get("salary_currency", "RUB")
            if pd.isna(salary):
                return None
            rate = EXCHANGE_RATES.get(currency, 1.0)
            return salary * rate
        
        # Создаем копию с конвертированными зарплатами
        df_rub = df.copy()
        df_rub["salary_from_rub"] = df_rub.apply(convert_to_rub, axis=1)
        
        # Распределение по зарплате в RUB (конвертированное)
        salary_distribution = {"< 50k": 0, "50k-100k": 0, "100k-150k": 0, "150k-200k": 0, "200k+": 0}
        if "salary_from_rub" in df_rub.columns:
            salary_df = df_rub[df_rub["salary_from_rub"].notna()]
            for salary in salary_df["salary_from_rub"]:
                if salary < 50000:
                    salary_distribution["< 50k"] += 1
                elif salary < 100000:
                    salary_distribution["50k-100k"] += 1
                elif salary < 150000:
                    salary_distribution["100k-150k"] += 1
                elif salary < 200000:
                    salary_distribution["150k-200k"] += 1
                else:
                    salary_distribution["200k+"] += 1

        # Топ регионов
        top_areas = {}
        if "area" in df.columns:
            top_areas = df["area"].value_counts().head(10).to_dict()

        # Статистика по зарплате в RUB
        salary_stats = {}
        if "salary_from_rub" in df_rub.columns:
            salary_df = df_rub[df_rub["salary_from_rub"].notna()]
            if not salary_df.empty:
                salary_stats = {
                    "min": float(salary_df["salary_from_rub"].min()),
                    "max": float(salary_df["salary_from_rub"].max()),
                    "median": float(salary_df["salary_from_rub"].median()),
                    "avg": float(salary_df["salary_from_rub"].mean())
                }

        # Статистика по валютам
        salary_stats_by_currency = {}
        if "salary_currency" in df.columns:
            for currency in df["salary_currency"].unique():
                if pd.isna(currency):
                    continue
                df_curr = df[df["salary_currency"] == currency]
                if "salary_from" in df_curr.columns:
                    salary_df_curr = df_curr[df_curr["salary_from"].notna()]
                    if not salary_df_curr.empty:
                        salary_stats_by_currency[currency] = {
                            "min": float(salary_df_curr["salary_from"].min()),
                            "max": float(salary_df_curr["salary_from"].max()),
                            "median": float(salary_df_curr["salary_from"].median()),
                            "avg": float(salary_df_curr["salary_from"].mean()),
                            "count": len(salary_df_curr)
                        }

        # Распределение по валютам
        currencies = {}
        if "salary_currency" in df.columns:
            currencies = df["salary_currency"].value_counts().to_dict()

        return {
            "experience": experience_counts,
            "employment": employment_counts,
            "salary_distribution": salary_distribution,
            "top_areas": top_areas,
            "salary_stats": salary_stats,
            "salary_stats_by_currency": salary_stats_by_currency,
            "currencies": currencies
        }
    finally:
        storage.close()

@app.get("/api/parser/status")
def parser_status():
    return {"state": parser_state}

@app.get("/api/parser/stop")
def stop_parser():
    """Остановка парсера."""
    global parser_state
    if parser_state["is_running"]:
        parser_state["stop_requested"] = True
        parser_state["status"] = "stopping"
        logger.info("Запрошена остановка парсера")
        return {"message": "Остановка запрошена", "state": parser_state}
    else:
        raise HTTPException(400, "Парсер не запущен")

@app.get("/api/parser/cache/stats")
def cache_stats():
    """Статистика кэша API."""
    from optimized_parser import APICache
    
    try:
        cache = APICache()
        stats = cache.get_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/parser/cache/clear")
def clear_cache(days: int = Query(default=7, description="Очистить кэш старше N дней")):
    """Очистка кэша API."""
    from optimized_parser import APICache
    
    try:
        cache = APICache()
        cache.clear_old(days)
        return {
            "success": True,
            "message": f"Кэш очищен (старше {days} дней)"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/parser/start")
def start_parser(
    background_tasks: BackgroundTasks,
    keywords: Optional[list[str]] = Query(None),
    max_pages: Optional[int] = Query(None),
    days_back: Optional[int] = Query(None),
    incremental: bool = Query(False),
    use_cache: bool = Query(True)
):
    """Запуск парсера (поддерживает обычный и оптимизированный режим)."""
    global parser_state
    if parser_state["is_running"]:
        raise HTTPException(400, "Парсер уже запущен")

    # Используем пользовательские ключевые слова или берём из конфига
    if keywords:
        from src.config import config_loader
        if not keywords or keywords == [""]:
            keywords = config_loader.search_queries
    else:
        from src.config import config_loader
        keywords = config_loader.search_queries

    parser_state = {
        "is_running": True,
        "status": "running",
        "progress": 0,
        "current_keyword": keywords[0] if keywords else "",
        "current_page": 0,
        "total_pages": max_pages or 10,
        "vacancies_collected": 0,
        "keywords": keywords,
        "incremental": incremental,
        "use_cache": use_cache,
        "error_message": None,
        "started_at": datetime.now().isoformat(),
        "completed_at": None
    }

    def run():
        global parser_state
        try:
            # Используем оптимизированный парсер если включены соответствующие режимы
            if incremental or use_cache:
                from optimized_parser import OptimizedVacancyCollector
                collector = OptimizedVacancyCollector(
                    max_pages=max_pages,
                    days_back=days_back,
                    use_cache=use_cache,
                    incremental=incremental
                )
            else:
                from src.collector import VacancyCollector
                collector = VacancyCollector(max_pages=max_pages, days_back=days_back)

            # Передаём флаг остановки в collector
            collector.stop_requested = False

            # Переопределяем метод сбора для обновления прогресса
            if hasattr(collector, '_collect_by_keyword'):
                original_collect_by_keyword = collector._collect_by_keyword

                def collect_by_keyword_with_progress(keyword, delay_between_pages=1.0, progress_bar=None):
                    parser_state["current_keyword"] = keyword
                    logger.info(f"Запрос: {keyword}")
                    return original_collect_by_keyword(keyword, delay_between_pages, progress_bar)

                collector._collect_by_keyword = collect_by_keyword_with_progress

                # Переопределяем метод search_vacancies для отслеживания страниц
                if hasattr(collector.client, 'search_vacancies'):
                    original_search = collector.client.search_vacancies
                    def search_with_progress(keyword, page, per_page=100):
                        parser_state["current_page"] = page
                        if parser_state.get("stop_requested", False):
                            collector.stop_requested = True
                            return None
                        result = original_search(keyword, page, per_page)
                        if result:
                            items = result.get("items", [])
                            parser_state["vacancies_collected"] = len(collector._seen_ids)
                        return result
                    collector.client.search_vacancies = search_with_progress

            result = collector.collect_all(keywords=keywords, save_raw=True, show_progress=False)
            parser_state["progress"] = 100
            parser_state["status"] = "completed"
            parser_state["completed_at"] = datetime.now().isoformat()
            parser_state["vacancies_collected"] = result.get("unique", 0)
            collector.close()
        except Exception as e:
            parser_state["status"] = "error"
            parser_state["error_message"] = str(e)
            parser_state["completed_at"] = datetime.now().isoformat()
        finally:
            parser_state["is_running"] = False
            parser_state["stop_requested"] = False

    background_tasks.add_task(run)
    return {"message": "Парсер запущен", "state": parser_state}

@app.get("/api/reports/list")
def list_reports():
    from src.config import settings
    from datetime import datetime
    
    reports_dir = settings.reports_dir
    if not reports_dir.exists():
        return {"reports": []}
    
    reports = [{"name": f.name, "size": f.stat().st_size, "created_at": datetime.fromtimestamp(f.stat().st_ctime).isoformat()} for f in reports_dir.glob("*.xlsx")]
    return {"reports": sorted(reports, key=lambda x: x["created_at"], reverse=True)}

@app.get("/api/reports/download/{filename:path}")
def download_report(filename: str):
    from src.config import settings
    from fastapi.responses import FileResponse
    
    filepath = settings.reports_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "Отчёт не найден")
    
    return FileResponse(path=filepath, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.post("/api/reports/generate")
def generate_report(background_tasks: BackgroundTasks):
    def run():
        from src.storage import VacancyStorage
        from src.analyzer import VacancyAnalyzer
        from src.advanced_analyzer import AdvancedAnalytics
        
        storage = VacancyStorage()
        try:
            df = storage.get_all_vacancies()
            if not df.empty:
                VacancyAnalyzer(df).generate_excel_report()
                AdvancedAnalytics(df).generate_detailed_excel_report()
        finally:
            storage.close()
    
    background_tasks.add_task(run)
    return {"message": "Генерация запущена"}

@app.get("/api/export/vacancies")
def export_vacancies(format: str = "csv"):
    from src.storage import VacancyStorage
    from src.config import settings
    from datetime import datetime
    
    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            raise HTTPException(404, "Нет данных")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == "csv":
            filepath = settings.reports_dir / f"vacancies_export_{timestamp}.csv"
            df.to_csv(filepath, index=False, encoding="utf-8-sig")
            media_type = "text/csv"
        else:
            filepath = settings.reports_dir / f"vacancies_export_{timestamp}.xlsx"
            df.to_excel(filepath, index=False, engine="openpyxl")
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return FileResponse(path=filepath, filename=filepath.name, media_type=media_type)
    finally:
        storage.close()

# =============================================================================
# API для профессий
# =============================================================================

# Кэш для каталога профессий
_professions_catalog_cache = None

def _load_professions_catalog():
    """Загрузить каталог профессий из файла."""
    global _professions_catalog_cache
    
    if _professions_catalog_cache is not None:
        return _professions_catalog_cache
    
    catalog_path = PROJECT_ROOT / "data" / "professions_catalog.json"
    
    if catalog_path.exists():
        import json
        with open(catalog_path, "r", encoding="utf-8") as f:
            _professions_catalog_cache = json.load(f)
    else:
        _professions_catalog_cache = {"professions": {}, "total": 0}
    
    return _professions_catalog_cache

@app.get("/api/professions/list")
def get_professions_list(
    domain: Optional[str] = None,
    sphere: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100
):
    """Получить список профессий с фильтрами."""
    catalog = _load_professions_catalog()
    
    professions = list(catalog.get("professions", {}).values())
    
    # Фильтр по домену
    if domain:
        professions = [p for p in professions if p.get("domain") == domain]
    
    # Фильтр по сфере
    if sphere:
        professions = [p for p in professions if p.get("sphere") == sphere]
    
    # Поиск по названию
    if search:
        search_lower = search.lower()
        professions = [p for p in professions if search_lower in p.get("name", "").lower()]
    
    # Сортировка по количеству вакансий
    professions.sort(key=lambda x: x.get("vacancies_count", 0), reverse=True)
    
    # Ограничение
    professions = professions[:limit]
    
    # Форматируем ответ
    return {
        "professions": professions,
        "total": len(professions),
        "domains": catalog.get("domains", {}),
        "areas": catalog.get("areas", {})
    }

@app.get("/api/professions/detail/{profession_key:path}")
def get_profession_detail(profession_key: str):
    """Получить детальную информацию о профессии."""
    catalog = _load_professions_catalog()
    
    profession = catalog.get("professions", {}).get(profession_key)
    
    if not profession:
        raise HTTPException(status_code=404, detail="Профессия не найдена")
    
    return profession

@app.get("/api/professions/domains")
def get_domains():
    """Получить список доменов и сфер."""
    catalog = _load_professions_catalog()
    
    # Считаем количество профессий по доменам
    domain_counts = defaultdict(int)
    for prof in catalog.get("professions", {}).values():
        domain_counts[prof.get("domain", "Другое")] += 1
    
    return {
        "domains": catalog.get("domains", {}),
        "areas": catalog.get("areas", {}),
        "domain_counts": dict(domain_counts)
    }

@app.get("/api/professions/vacancies")
def get_profession_vacancies(name: str):
    """Получить вакансии для профессии."""
    catalog = _load_professions_catalog()
    
    # Ищем профессию по названию
    profession = None
    for prof in catalog.get("professions", {}).values():
        if name.lower() in prof.get("name", "").lower():
            profession = prof
            break
    
    if not profession:
        return {"vacancies": []}
    
    # Возвращаем примеры вакансий
    return {
        "vacancies": profession.get("sample_vacancies", [])[:10]
    }

# =============================================================================
# Запуск
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 HH.ru Analytics — Веб-приложение")
    print("=" * 60)
    print(f"📁 Project: {PROJECT_ROOT}")
    print(f"📁 Static: {STATIC_DIR}")
    print(f"✅ Static exists: {STATIC_DIR.exists()}")
    print()
    print("🌐 Откройте в браузере:")
    print("   http://localhost:8000")
    print("   http://localhost:8000/docs")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
