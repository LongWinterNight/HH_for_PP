"""
Сбор с экрана всегда дописывает, пользуется кешем и собирает глубоко.

Решение владельца 13.10.2026: отключить эти режимы пользователь не может.
Дописывание раньше было параметром маршрута с выключенным значением по
умолчанию, и запрос без него стирал таблицу вакансий целиком.
"""
import inspect

from web.app import main


def test_у_запуска_сбора_нет_параметров_режимов():
    параметры = inspect.signature(main.start_parser).parameters
    for снятый in ("incremental", "use_cache", "глубоко"):
        assert снятый not in параметры, f"маршрут снова принимает «{снятый}»"


def test_режимы_заданы_в_теле_и_включены():
    код = inspect.getsource(main.start_parser)
    for строка in ("incremental = True", "use_cache = True", "глубоко = True"):
        assert строка in код
