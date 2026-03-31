#!/usr/bin/env python3
"""
Скрипт проверки готовности проекта к демонстрации.

Запустите перед презентацией чтобы убедиться что всё работает.
"""

import sys
import os
from pathlib import Path

# Цвета для вывода
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")

def check_python_version():
    """Проверка версии Python."""
    version = sys.version_info
    required = (3, 10)
    
    if version >= required:
        print_success(f"Python {version.major}.{version.minor}.{version.micro} (требуется 3.10+)")
        return True
    else:
        print_error(f"Python {version.major}.{version.minor}.{version.micro} (требуется 3.10+)")
        return False

def check_dependencies():
    """Проверка установленных зависимостей."""
    required_packages = [
        'fastapi',
        'uvicorn',
        'pandas',
        'numpy',
        'pyyaml',
        'sqlalchemy',
        'openpyxl',
        'xlsxwriter',
        'reportlab',
        'pymorphy3',
        'requests'
    ]
    
    missing = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{package} установлен")
        except ImportError:
            print_error(f"{package} НЕ установлен")
            missing.append(package)
    
    if missing:
        print_warning(f"Отсутствуют пакеты: {', '.join(missing)}")
        print_info("Установите: pip install -r requirements.txt")
        return False
    
    return True

def check_env_file():
    """Проверка наличия .env файла."""
    env_path = Path('.env')
    env_example_path = Path('.env.example')
    
    if env_path.exists():
        print_success(".env файл существует")
        return True
    elif env_example_path.exists():
        print_warning(".env файл отсутствует, но есть .env.example")
        print_info("Скопируйте: copy .env.example .env (Windows) или cp .env.example .env (Linux/macOS)")
        return False
    else:
        print_error(".env файл отсутствует")
        return False

def check_database():
    """Проверка базы данных."""
    db_path = Path('data/hh_analytics.db')
    
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        print_success(f"База данных существует ({size_mb:.2f} MB)")
        
        # Проверка наличия данных
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Проверка таблицы vacancies
            cursor.execute("SELECT COUNT(*) FROM vacancies")
            count = cursor.fetchone()[0]
            
            if count > 0:
                print_success(f"В базе {count} вакансий")
                
                if count >= 200:
                    print_success("✓ Достаточно данных для демонстрации")
                elif count >= 50:
                    print_warning("Минимум данных для демонстрации")
                else:
                    print_error("Мало данных! Запустите парсер.")
                    return False
            else:
                print_error("База данных пуста!")
                return False
            
            conn.close()
            return True
            
        except Exception as e:
            print_error(f"Ошибка проверки БД: {e}")
            return False
    else:
        print_error("База данных не найдена!")
        print_info("Запустите парсер для создания базы данных")
        return False

def check_web_files():
    """Проверка файлов веб-приложения."""
    required_files = [
        Path('web/app/main.py'),
        Path('web/static/index.html'),
        Path('config.yaml'),
        Path('requirements.txt'),
        Path('README.md')
    ]
    
    all_exist = True
    
    for file_path in required_files:
        if file_path.exists():
            print_success(f"{file_path} существует")
        else:
            print_error(f"{file_path} НЕ найден")
            all_exist = False
    
    return all_exist

def check_server_port():
    """Проверка занятости порта 8000."""
    import socket
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        result = sock.connect_ex(('127.0.0.1', 8000))
        if result == 0:
            print_warning("Порт 8000 занят (возможно сервер уже запущен)")
            return False
        else:
            print_success("Порт 8000 свободен")
            return True
    finally:
        sock.close()

def check_data_files():
    """Проверка дополнительных файлов данных."""
    files = [
        Path('data/professions_catalog.json'),
    ]
    
    all_exist = True
    
    for file_path in files:
        if file_path.exists():
            print_success(f"{file_path} существует")
        else:
            print_warning(f"{file_path} отсутствует (не критично)")
            all_exist = False
    
    return all_exist

def main():
    """Основная функция."""
    print_header("HH.ru Analytics — Проверка готовности к демонстрации")
    
    # Перейти в директорию проекта
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    results = []
    
    # 1. Python версия
    print_info("1. Проверка версии Python...")
    results.append(check_python_version())
    
    # 2. Зависимости
    print_info("2. Проверка зависимостей...")
    results.append(check_dependencies())
    
    # 3. .env файл
    print_info("3. Проверка .env файла...")
    results.append(check_env_file())
    
    # 4. База данных
    print_info("4. Проверка базы данных...")
    results.append(check_database())
    
    # 5. Файлы веб-приложения
    print_info("5. Проверка файлов веб-приложения...")
    results.append(check_web_files())
    
    # 6. Порт 8000
    print_info("6. Проверка порта 8000...")
    results.append(check_server_port())
    
    # 7. Файлы данных
    print_info("7. Проверка файлов данных...")
    results.append(check_data_files())
    
    # Итоги
    print_header("Результаты")
    
    success_count = sum(results)
    total_count = len(results)
    
    if all(results):
        print_success(f"Все проверки пройдены ({success_count}/{total_count})")
        print("\n" + "="*60)
        print(f"{Colors.GREEN}{Colors.BOLD}🚀 ПРОЕКТ ГОТОВ К ДЕМОНСТРАЦИИ!{Colors.END}")
        print("="*60)
        print("\nДля запуска выполните:")
        print(f"  {Colors.BLUE}python web/app/main.py{Colors.END}")
        print(f"\nЗатем откройте в браузере:")
        print(f"  {Colors.BLUE}http://localhost:8000{Colors.END}")
        print()
        return 0
    else:
        print_error(f"Некоторые проверки не пройдены ({success_count}/{total_count})")
        print("\n" + "="*60)
        print(f"{Colors.YELLOW}⚠ ПРОЕКТ НЕ ГОТОВ К ДЕМОНСТРАЦИИ{Colors.END}")
        print("="*60)
        print("\nУстраните ошибки и запустите проверку снова:")
        print(f"  {Colors.BLUE}python check_demo_ready.py{Colors.END}")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
