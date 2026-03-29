#!/usr/bin/env python3
"""
CLI интерфейс для работы с базой данных HH Analytics.

Предоставляет удобные команды для:
- Просмотра вакансий
- Поиска по навыкам
- Аналитики и статистики
- Экспорта данных

Использование:
    python -m src.db_cli              # Интерактивный режим
    python -m src.db_cli --list       # Список всех вакансий
    python -m src.db_cli --skill LLM  # Поиск по навыку
    python -m src.db_cli --stats      # Статистика
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, List

import pandas as pd

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import settings
from src.storage import VacancyStorage
from src.advanced_analyzer import AdvancedAnalytics
from src.utils import get_logger

logger = get_logger(__name__)


class DatabaseCLI:
    """CLI интерфейс для работы с базой данных."""

    def __init__(self):
        """Инициализация CLI."""
        self.storage = None
        self.df = None

    def connect(self) -> bool:
        """Подключение к базе данных."""
        try:
            if not settings.db_path.exists():
                print(f"❌ База данных не найдена: {settings.db_path}")
                print("Сначала запустите полный пайплайн: python main.py")
                return False

            self.storage = VacancyStorage()
            self.df = self.storage.get_all_vacancies()

            if self.df.empty:
                print("⚠️  База данных пуста")
                return False

            print(f"✅ Подключено к базе данных: {settings.db_path}")
            print(f"📈 Вакансий в базе: {len(self.df)}")
            return True

        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def close(self) -> None:
        """Закрытие соединения с БД."""
        if self.storage:
            self.storage.close()
            print("✅ Соединение с БД закрыто")

    def list_vacancies(
        self,
        limit: int = 20,
        area: Optional[str] = None,
        experience: Optional[str] = None
    ) -> None:
        """Вывод списка вакансий."""
        if self.df is None or self.df.empty:
            print("❌ Нет данных")
            return

        # Фильтры
        df = self.df.copy()

        if area:
            df = df[df["area"].str.contains(area, case=False, na=False)]
            print(f"🔍 Фильтр по региону: {area}")

        if experience:
            df = df[df["experience"].str.contains(experience, case=False, na=False)]
            print(f"🔍 Фильтр по опыту: {experience}")

        # Вывод
        print(f"\n📋 Вакансии (показано {min(limit, len(df))} из {len(df)}):")
        print("=" * 80)

        for i, (_, row) in enumerate(df.head(limit).iterrows(), 1):
            print(f"\n{i}. {row['vacancy_name']}")
            print(f"   Компания: {row['employer_name'] or 'Не указано'}")
            print(f"   Регион: {row['area'] or 'Не указано'}")
            print(f"   Опыт: {row['experience'] or 'Не указано'}")
            print(f"   Зарплата: {self._format_salary(row)}")
            print(f"   Навыков: {row.get('skill_count', 0)} (Hard: {row.get('hard_skill_count', 0)}, "
                  f"Soft: {row.get('soft_skill_count', 0)}, Tools: {row.get('tools_count', 0)})")
            print(f"   URL: {row['vacancy_url']}")

        print("\n" + "=" * 80)

    def _format_salary(self, row: pd.Series) -> str:
        """Форматирование зарплаты."""
        salary_from = row.get("salary_from")
        salary_to = row.get("salary_to")
        currency = row.get("salary_currency", "RUB")

        if pd.isna(salary_from) and pd.isna(salary_to):
            return "Не указана"

        from_str = f"{int(salary_from):,}" if not pd.isna(salary_from) else "?"
        to_str = f"{int(salary_to):,}" if not pd.isna(salary_to) else "?"

        return f"{from_str} - {to_str} {currency}"

    def search_by_skill(self, skill: str, limit: int = 20) -> None:
        """Поиск вакансий по навыку."""
        if self.df is None or self.df.empty:
            print("❌ Нет данных")
            return

        skill_lower = skill.lower()

        # Ищем вхождение навыка в любой колонке
        mask = False
        for col in ["hard_skills", "soft_skills", "tools", "all_skills"]:
            if col in self.df.columns:
                mask = mask | self.df[col].str.contains(skill_lower, case=False, na=False)

        df_filtered = self.df[mask] if hasattr(mask, 'any') else self.df.head(0)

        if df_filtered.empty:
            print(f"❌ Вакансии с навыком '{skill}' не найдены")
            return

        print(f"\n✅ Найдено вакансий с навыком '{skill}': {len(df_filtered)}")
        print("=" * 80)

        for i, (_, row) in enumerate(df_filtered.head(limit).iterrows(), 1):
            print(f"\n{i}. {row['vacancy_name']}")
            print(f"   Компания: {row['employer_name'] or 'Не указано'}")
            print(f"   Регион: {row['area'] or 'Не указано'}")

            # Показываем найденные навыки
            for col in ["hard_skills", "soft_skills", "tools"]:
                skills_str = row.get(col, "")
                if skills_str and skill_lower in skills_str.lower():
                    print(f"   {col.replace('_', ' ').title()}: {skills_str[:100]}")

            print(f"   URL: {row['vacancy_url']}")

        print("\n" + "=" * 80)

    def show_statistics(self) -> None:
        """Показ статистики."""
        if self.df is None or self.df.empty:
            print("❌ Нет данных")
            return

        print("\n" + "=" * 80)
        print("📊 СТАТИСТИКА ПО БАЗЕ ДАННЫХ")
        print("=" * 80)

        # Общая статистика
        print(f"\n📈 Всего вакансий: {len(self.df)}")

        # Распределение по регионам
        print("\n📍 Топ-10 регионов:")
        if "area" in self.df.columns:
            area_counts = self.df["area"].value_counts().head(10)
            for area, count in area_counts.items():
                print(f"   {area}: {count}")

        # Распределение по опыту
        print("\n📋 Требуемый опыт:")
        if "experience" in self.df.columns:
            exp_counts = self.df["experience"].value_counts()
            for exp, count in exp_counts.items():
                print(f"   {exp}: {count}")

        # Зарплаты
        print("\n💰 Зарплаты:")
        if "salary_from" in self.df.columns:
            salary_df = self.df[self.df["salary_from"].notna()]
            if not salary_df.empty:
                print(f"   Средняя: {salary_df['salary_from'].mean():,.0f} RUB")
                print(f"   Медиана: {salary_df['salary_from'].median():,.0f} RUB")
                print(f"   Мин: {salary_df['salary_from'].min():,.0f} RUB")
                print(f"   Макс: {salary_df['salary_from'].max():,.0f} RUB")

        # Навыки
        print("\n🛠 Среднее количество навыков на вакансию:")
        if "skill_count" in self.df.columns:
            print(f"   Всего: {self.df['skill_count'].mean():.2f}")
        if "hard_skill_count" in self.df.columns:
            print(f"   Hard Skills: {self.df['hard_skill_count'].mean():.2f}")
        if "soft_skill_count" in self.df.columns:
            print(f"   Soft Skills: {self.df['soft_skill_count'].mean():.2f}")
        if "tools_count" in self.df.columns:
            print(f"   Tools: {self.df['tools_count'].mean():.2f}")

        print("\n" + "=" * 80)

    def show_advanced_analytics(self) -> None:
        """Показ расширенной аналитики."""
        if self.df is None or self.df.empty:
            print("❌ Нет данных")
            return

        print("\n📊 ЗАПУСК РАСШИРЕННОЙ АНАЛИТИКИ...")
        print("=" * 80)

        analytics = AdvancedAnalytics(self.df)
        analytics.print_advanced_summary()

    def export_to_excel(self, output_path: Optional[str] = None) -> None:
        """Экспорт данных в Excel."""
        if self.df is None or self.df.empty:
            print("❌ Нет данных")
            return

        from datetime import datetime

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/reports/vacancies_export_{timestamp}.xlsx"

        # Сохраняем
        self.df.to_excel(output_path, index=False, engine="openpyxl")
        print(f"✅ Данные экспортированы: {output_path}")

    def interactive_mode(self) -> None:
        """Интерактивный режим."""
        print("\n" + "=" * 80)
        print("🖥 ИНТЕРАКТИВНЫЙ РЕЖИМ РАБОТЫ С БАЗОЙ ДАННЫХ")
        print("=" * 80)
        print("\nДоступные команды:")
        print("  list [limit=20]              — Список вакансий")
        print("  search <skill> [limit=20]    — Поиск по навыку")
        print("  stats                        — Статистика")
        print("  advanced                     — Расширенная аналитика")
        print("  export [path]                — Экспорт в Excel")
        print("  filter --area <region>       — Фильтр по региону")
        print("  filter --exp <experience>    — Фильтр по опыту")
        print("  help                         — Помощь")
        print("  quit / exit                  — Выход")
        print("=" * 80)

        while True:
            try:
                command = input("\n>>> ").strip()

                if not command:
                    continue

                parts = command.split()
                cmd = parts[0].lower()

                if cmd in ["quit", "exit", "q"]:
                    print("👋 До свидания!")
                    break

                elif cmd == "help":
                    self._print_help()

                elif cmd == "list":
                    limit = int(parts[1]) if len(parts) > 1 else 20
                    self.list_vacancies(limit=limit)

                elif cmd == "search":
                    if len(parts) < 2:
                        print("❌ Укажите навык для поиска: search <skill>")
                        continue
                    skill = parts[1]
                    limit = int(parts[2]) if len(parts) > 2 else 20
                    self.search_by_skill(skill, limit=limit)

                elif cmd == "stats":
                    self.show_statistics()

                elif cmd == "advanced":
                    self.show_advanced_analytics()

                elif cmd == "export":
                    path = parts[1] if len(parts) > 1 else None
                    self.export_to_excel(path)

                elif cmd == "filter":
                    # Обработка фильтров
                    if "--area" in command:
                        idx = parts.index("--area")
                        area = parts[idx + 1] if idx + 1 < len(parts) else ""
                        self.list_vacancies(area=area)
                    elif "--exp" in command:
                        idx = parts.index("--exp")
                        exp = parts[idx + 1] if idx + 1 < len(parts) else ""
                        self.list_vacancies(experience=exp)
                    else:
                        print("❌ Используйте: filter --area <region> или filter --exp <experience>")

                else:
                    print(f"❌ Неизвестная команда: {cmd}")
                    self._print_help()

            except KeyboardInterrupt:
                print("\n👋 До свидания!")
                break
            except Exception as e:
                print(f"❌ Ошибка: {e}")

    def _print_help(self) -> None:
        """Вывод справки."""
        print("\nДоступные команды:")
        print("  list [limit=20]              — Список вакансий")
        print("  search <skill> [limit=20]    — Поиск по навыку")
        print("  stats                        — Статистика")
        print("  advanced                     — Расширенная аналитика")
        print("  export [path]                — Экспорт в Excel")
        print("  filter --area <region>       — Фильтр по региону")
        print("  filter --exp <experience>    — Фильтр по опыту")
        print("  help                         — Помощь")
        print("  quit / exit                  — Выход")


def main():
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        description="CLI интерфейс для работы с базой данных HH Analytics"
    )

    # Режимы работы
    parser.add_argument(
        "--list",
        action="store_true",
        help="Список всех вакансий"
    )
    parser.add_argument(
        "--skill",
        type=str,
        help="Поиск по навыку (например: --skill LLM)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Показать статистику"
    )
    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Расширенная аналитика"
    )
    parser.add_argument(
        "--export",
        type=str,
        nargs="?",
        const="auto",
        help="Экспорт в Excel (опционально: путь)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Лимит вывода (по умолчанию 20)"
    )
    parser.add_argument(
        "--area",
        type=str,
        help="Фильтр по региону"
    )
    parser.add_argument(
        "--experience",
        type=str,
        help="Фильтр по опыту"
    )

    args = parser.parse_args()

    # Создаём CLI
    cli = DatabaseCLI()

    # Подключаемся к БД
    if not cli.connect():
        sys.exit(1)

    # Если аргументы не указаны — интерактивный режим
    if not any([args.list, args.skill, args.stats, args.advanced, args.export]):
        cli.interactive_mode()
    else:
        # Выполняем указанные действия
        if args.list:
            cli.list_vacancies(
                limit=args.limit,
                area=args.area,
                experience=args.experience
            )

        if args.skill:
            cli.search_by_skill(args.skill, limit=args.limit)

        if args.stats:
            cli.show_statistics()

        if args.advanced:
            cli.show_advanced_analytics()

        if args.export:
            path = args.export if args.export != "auto" else None
            cli.export_to_excel(path)

    # Закрываем соединение
    if cli.storage:
        cli.storage.close()


if __name__ == "__main__":
    main()
