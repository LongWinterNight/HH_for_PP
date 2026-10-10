"""
Тест сохранности базы при повторных сборах.

Проверяет путь целиком: сырой ответ источника → нормализация → запись.
Тесты хранилища проверяют upsert сам по себе, а здесь — что коллектор
им пользуется. Прежде коллектор отбирал только неизвестные вакансии и
передавал их в запись, заменявшую таблицу целиком: после второго сбора
в базе оставалось лишь то, что нашлось в нём.

Запуск: pytest tests/test_collector_persistence.py -v
"""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.collector import VacancyCollector
from src.storage import VacancyStorage


def raw_vacancy(
    vacancy_id: str,
    name: str = "Аналитик данных",
    salary_from: int = 100000,
    keyword: str = "Python",
) -> dict:
    """Вакансия в том виде, в каком её отдаёт поиск источника."""
    return {
        "_source_keyword": keyword,
        "id": vacancy_id,
        "name": name,
        "published_at": "2026-09-01T10:00:00+0300",
        "salary": {"from": salary_from, "to": salary_from * 2, "currency": "RUR", "gross": False},
        "employer": {"id": "1", "name": "Компания", "url": ""},
        "area": {"id": "1", "name": "Москва"},
        "experience": {"name": "От 1 года до 3 лет"},
        "employment": {"name": "Полная занятость"},
        "schedule": {"name": "Удалённо"},
        "alternate_url": f"https://hh.ru/vacancy/{vacancy_id}",
        "snippet": {"requirement": "Python, SQL", "responsibility": "Аналитика"},
    }


@pytest.fixture
def collector(tmp_path, monkeypatch):
    """
    Коллектор на отдельной базе.

    Путь к базе подменяется в настройках: `_save_to_database` создаёт
    хранилище сам, без параметров, и без подмены тест писал бы в рабочую
    базу проекта.
    """
    from src import config, storage as storage_module

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(storage_module.settings, "db_path", tmp_path / "test.db")

    # Клиент не нужен: проверяется сохранение, а не сбор.
    return VacancyCollector(client=object(), output_dir=tmp_path / "raw")


def stored(tmp_path, include_inactive: bool = False):
    store = VacancyStorage(db_path=tmp_path / "test.db")
    try:
        return store.get_all_vacancies(include_inactive=include_inactive)
    finally:
        store.close()


def test_второй_сбор_не_стирает_собранное_ранее(collector, tmp_path):
    collector._save_to_database([raw_vacancy("1"), raw_vacancy("2")])
    collector._save_to_database([raw_vacancy("3")])

    saved = stored(tmp_path)
    assert set(saved["vacancy_id"]) == {"1", "2", "3"}


def test_повторная_встреча_вакансии_обновляет_её(collector, tmp_path):
    collector._save_to_database([raw_vacancy("1", salary_from=100000)])
    collector._save_to_database([raw_vacancy("1", salary_from=300000)])

    saved = stored(tmp_path)
    assert len(saved) == 1
    assert saved.iloc[0]["salary_from"] == 300000


def test_сбор_без_новых_вакансий_не_очищает_базу(collector, tmp_path):
    collector._save_to_database([raw_vacancy("1"), raw_vacancy("2")])
    collector._save_to_database([raw_vacancy("1"), raw_vacancy("2")])

    assert len(stored(tmp_path)) == 2


def test_запрос_записывается_в_вакансию(collector, tmp_path):
    collector._save_to_database([raw_vacancy("1", keyword="Data Scientist")])

    assert stored(tmp_path).iloc[0]["source_keyword"] == "Data Scientist"


def test_после_полного_прохода_пропавшая_вакансия_гаснет(collector, tmp_path):
    collector._save_to_database([raw_vacancy("1"), raw_vacancy("2")])

    # Выдача прочитана до конца, и вакансии «2» в ней больше нет.
    collector._keyword_seen = {"Python": {"1"}}
    collector._keyword_complete = {"Python": True}
    collector._save_to_database([raw_vacancy("1")])

    assert set(stored(tmp_path)["vacancy_id"]) == {"1"}
    assert set(stored(tmp_path, include_inactive=True)["vacancy_id"]) == {"1", "2"}


def test_сбой_записи_не_проходит_молча(collector, monkeypatch):
    """
    Сбор, не сохранивший данные, обязан закончиться ошибкой. Прежде
    исключение оставалось в логах, а запуск получал статус «завершено»:
    пользователь видел успех там, где в базу ничего не попало.
    """
    from src.storage import VacancyStorage

    def сломанная_запись(self, df, update_existing=True):
        raise RuntimeError("диск переполнен")

    monkeypatch.setattr(VacancyStorage, "save_vacancies_incremental", сломанная_запись)

    with pytest.raises(RuntimeError, match="диск переполнен"):
        collector._save_to_database([raw_vacancy("1")])


def test_после_неполного_прохода_ничего_не_гаснет(collector, tmp_path):
    """
    Сбор, прерванный ошибкой, остановкой или пределом страниц, не видел
    всей выдачи. Гашение по нему объявило бы закрытыми живые вакансии.
    """
    collector._save_to_database([raw_vacancy("1"), raw_vacancy("2")])

    collector._keyword_seen = {"Python": {"1"}}
    collector._keyword_complete = {"Python": False}
    collector._save_to_database([raw_vacancy("1")])

    assert set(stored(tmp_path)["vacancy_id"]) == {"1", "2"}
