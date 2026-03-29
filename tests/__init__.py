"""
Тесты для модуля src/__init__.py.

Запуск: pytest tests/ -v
"""

import sys
from pathlib import Path

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_package_import():
    """Тест импорта пакета."""
    from src import __version__, __author__
    
    assert __version__ == "1.0.0"
    assert __author__ == "HH Analytics Team"
