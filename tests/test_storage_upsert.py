"""
Тесты записи вакансий в базу.

Проверяют главное свойство хранилища: сбор данных пополняет базу, а не
заменяет её. До перевода записи на upsert каждый сбор оставлял в базе
только что найденное, стирая собранное раньше, — история из-за этого не
накапливалась вовсе.

Запуск: pytest tests/test_storage_upsert.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage import VacancyStorage


def vacancy(vacancy_id: str, name: str = "Аналитик данных", salary_from: float = 100000) -> dict:
    """Одна строка в том виде, в каком её отдаёт нормализация сбора."""
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": name,
        "published_at": "2026-09-01T10:00:00+0300",
        "salary_from": salary_from,
        "salary_to": salary_from * 1.5,
        "salary_currency": "RUB",
        "employer_name": "Компания",
        "employer_id": "1",
        "employer_url": "",
        "vacancy_url": "",
        "experience": "От 1 года до 3 лет",
        "employment": "Полная занятость",
        "schedule": "Удалённо",
        "area": "Москва",
        "all_skills": "python, sql",
        "hard_skills": "python, sql",
        "soft_skills": "",
        "tools": "",
        "skill_count": 2,
        "hard_skill_count": 2,
        "soft_skill_count": 0,
        "tools_count": 0,
    }


@pytest.fixture
def storage(tmp_path):
    """Хранилище на отдельной базе: тесты не трогают рабочие данные."""
    store = VacancyStorage(db_path=tmp_path / "test.db")
    yield store
    store.close()


class TestUpsertСохраняетСобранное:
    """Сбор не должен терять то, что уже лежит в базе."""

    def test_второй_сбор_не_стирает_первый(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1"), vacancy("2")]))
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("3")]))

        saved = storage.get_all_vacancies()
        assert len(saved) == 3
        assert set(saved["vacancy_id"]) == {"1", "2", "3"}

    def test_статистика_различает_новое_и_известное(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1"), vacancy("2")]))

        stats = storage.save_vacancies_incremental(
            pd.DataFrame([vacancy("2", salary_from=200000), vacancy("3")])
        )

        assert stats["inserted"] == 1
        assert stats["updated"] == 1

    def test_возвращаются_идентификаторы_а_не_только_счётчики(self, storage):
        """
        Сбор раскладывает эти множества по поисковым запросам: без них в
        истории видно только итог, а не что принёс каждый запрос.
        """
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))

        stats = storage.save_vacancies_incremental(
            pd.DataFrame([vacancy("1", salary_from=200000), vacancy("2")])
        )

        assert stats["updated_ids"] == {"1"}
        assert stats["inserted_ids"] == {"2"}
        assert len(stats["inserted_ids"]) == stats["inserted"]
        assert len(stats["updated_ids"]) == stats["updated"]

    def test_известная_вакансия_обновляется(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1", salary_from=100000)]))
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1", salary_from=250000)]))

        saved = storage.get_all_vacancies()
        assert len(saved) == 1
        assert saved.iloc[0]["salary_from"] == 250000

    def test_момент_появления_записи_не_меняется(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))
        created_at = storage.get_all_vacancies().iloc[0]["created_at"]

        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1", salary_from=300000)]))
        saved = storage.get_all_vacancies().iloc[0]

        assert saved["created_at"] == created_at

    def test_без_обновления_известное_остаётся_прежним(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1", salary_from=100000)]))

        stats = storage.save_vacancies_incremental(
            pd.DataFrame([vacancy("1", salary_from=999999)]), update_existing=False
        )

        assert stats["updated"] == 0
        assert stats["skipped"] == 1
        assert storage.get_all_vacancies().iloc[0]["salary_from"] == 100000


class TestУстойчивостьЗаписи:
    """Что делает запись с данными, которые не годятся как есть."""

    def test_строки_без_идентификатора_пропускаются(self, storage):
        rows = pd.DataFrame([vacancy("1"), vacancy(None), vacancy("")])

        stats = storage.save_vacancies_incremental(rows)

        assert stats["inserted"] == 1
        assert stats["skipped"] == 2

    def test_повтор_внутри_одной_пачки_не_ломает_запись(self, storage):
        # SQLite отвергает вторую строку с тем же ключом в пределах
        # одного запроса: ON CONFLICT для неё уже не срабатывает.
        rows = pd.DataFrame([vacancy("1", salary_from=100000), vacancy("1", salary_from=200000)])

        stats = storage.save_vacancies_incremental(rows)

        saved = storage.get_all_vacancies()
        assert len(saved) == 1
        assert saved.iloc[0]["salary_from"] == 200000
        assert stats["skipped"] == 1

    def test_лишние_колонки_не_мешают(self, storage):
        row = vacancy("1")
        row["поле_которого_нет_в_таблице"] = "значение"

        stats = storage.save_vacancies_incremental(pd.DataFrame([row]))

        assert stats["inserted"] == 1

    def test_пустой_набор_не_трогает_базу(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))

        stats = storage.save_vacancies_incremental(pd.DataFrame())

        assert (stats["inserted"], stats["updated"], stats["skipped"]) == (0, 0, 0)
        assert len(storage.get_all_vacancies()) == 1

    def test_данные_без_идентификатора_вызывают_ошибку(self, storage):
        with pytest.raises(ValueError):
            storage.save_vacancies_incremental(pd.DataFrame([{"vacancy_name": "Без ключа"}]))


class TestПолнаяПерезапись:
    """Перезапись стирает данные, но не схему."""

    def test_заменяет_содержимое(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1"), vacancy("2")]))

        written = storage.replace_all_vacancies(pd.DataFrame([vacancy("3")]))

        saved = storage.get_all_vacancies()
        assert written == 1
        assert set(saved["vacancy_id"]) == {"3"}

    def test_индексы_переживают_перезапись(self, storage):
        """
        Прежняя реализация делала to_sql(if_exists="replace") и сносила
        таблицу вместе с первичным ключом и всеми индексами — следующий
        сбор писал уже в бесключевую таблицу, где upsert невозможен.
        """
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))
        before = _index_names(storage)

        storage.replace_all_vacancies(pd.DataFrame([vacancy("2")]))

        assert _index_names(storage) == before
        assert "ix_vacancies_vacancy_id" in before

    def test_после_перезаписи_upsert_работает(self, storage):
        storage.replace_all_vacancies(pd.DataFrame([vacancy("1")]))

        stats = storage.save_vacancies_incremental(pd.DataFrame([vacancy("1"), vacancy("2")]))

        assert stats["updated"] == 1
        assert stats["inserted"] == 1

    def test_пустой_набор_не_очищает_базу(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))

        written = storage.replace_all_vacancies(pd.DataFrame())

        assert written == 0
        assert len(storage.get_all_vacancies()) == 1


class TestЖизненныйЦикл:
    """Что запись помнит о своей судьбе между сборами."""

    def test_момент_первой_встречи_не_сдвигается(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))
        first_seen = storage.get_all_vacancies().iloc[0]["first_seen_at"]

        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1", salary_from=200000)]))

        assert storage.get_all_vacancies().iloc[0]["first_seen_at"] == first_seen

    def test_последняя_встреча_обновляется(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))
        before = storage.get_all_vacancies().iloc[0]["last_seen_at"]

        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))
        after = storage.get_all_vacancies().iloc[0]["last_seen_at"]

        assert after >= before

    def test_запросы_накапливаются(self, storage):
        first = vacancy("1")
        first["source_keyword"] = "Python"
        storage.save_vacancies_incremental(pd.DataFrame([first]))

        second = vacancy("1")
        second["source_keyword"] = "Backend developer"
        storage.save_vacancies_incremental(pd.DataFrame([second]))

        saved = storage.get_all_vacancies().iloc[0]["source_keyword"]
        assert saved == "Python, Backend developer"

    def test_повтор_запроса_не_дублируется(self, storage):
        row = vacancy("1")
        row["source_keyword"] = "Python"
        storage.save_vacancies_incremental(pd.DataFrame([row]))
        storage.save_vacancies_incremental(pd.DataFrame([row]))

        assert storage.get_all_vacancies().iloc[0]["source_keyword"] == "Python"

    def test_похожий_запрос_не_считается_тем_же(self, storage):
        first = vacancy("1")
        first["source_keyword"] = "Python"
        storage.save_vacancies_incremental(pd.DataFrame([first]))

        second = vacancy("1")
        second["source_keyword"] = "Python разработчик"
        storage.save_vacancies_incremental(pd.DataFrame([second]))

        assert storage.get_all_vacancies().iloc[0]["source_keyword"] == "Python, Python разработчик"

    def test_собранное_описание_не_теряется(self, storage):
        detailed = vacancy("1")
        detailed["has_details"] = True
        storage.save_vacancies_incremental(pd.DataFrame([detailed]))

        plain = vacancy("1")
        plain["has_details"] = False
        storage.save_vacancies_incremental(pd.DataFrame([plain]))

        assert bool(storage.get_all_vacancies().iloc[0]["has_details"]) is True


class TestЗаписьИзАрхива:
    """
    Разбор старых файлов сборов приносит записи задним числом. Они
    уточняют историю и не должны портить текущее состояние.
    """

    def архивная(self, vacancy_id, first_seen, last_seen, active=False):
        row = vacancy(vacancy_id)
        row["first_seen_at"] = pd.Timestamp(first_seen)
        row["last_seen_at"] = pd.Timestamp(last_seen)
        row["is_active"] = active
        return row

    def test_дата_первой_встречи_сдвигается_назад(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))

        storage.save_vacancies_incremental(
            pd.DataFrame([self.архивная("1", "2026-03-27 01:01:36", "2026-03-27 01:01:36")])
        )

        saved = storage.get_all_vacancies(include_inactive=True).iloc[0]
        assert str(saved["first_seen_at"]).startswith("2026-03-27")

    def test_старая_запись_не_затирает_свежую_встречу(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))
        свежая = storage.get_all_vacancies().iloc[0]["last_seen_at"]

        storage.save_vacancies_incremental(
            pd.DataFrame([self.архивная("1", "2026-03-27 01:01:36", "2026-03-27 01:01:36")])
        )

        assert storage.get_all_vacancies().iloc[0]["last_seen_at"] == свежая

    def test_архивная_запись_не_гасит_живую_вакансию(self, storage):
        storage.save_vacancies_incremental(pd.DataFrame([vacancy("1")]))

        storage.save_vacancies_incremental(
            pd.DataFrame([self.архивная("1", "2026-03-27 01:01:36", "2026-03-27 01:01:36")])
        )

        assert len(storage.get_all_vacancies()) == 1

    def test_новая_архивная_вакансия_приходит_погашенной(self, storage):
        """Вакансия, которой нет в последних сборах, живой не считается."""
        storage.save_vacancies_incremental(
            pd.DataFrame([self.архивная("9", "2026-03-27 01:01:36", "2026-03-27 01:01:36")])
        )

        assert len(storage.get_all_vacancies()) == 0
        assert len(storage.get_all_vacancies(include_inactive=True)) == 1

    def test_свежий_сбор_воскрешает_погашенную(self, storage):
        storage.save_vacancies_incremental(
            pd.DataFrame([self.архивная("9", "2026-03-27 01:01:36", "2026-03-27 01:01:36")])
        )

        storage.save_vacancies_incremental(pd.DataFrame([vacancy("9")]))

        assert len(storage.get_all_vacancies()) == 1


class TestГашениеПропавших:
    """Вакансия, исчезнувшая из выдачи, гаснет, но не удаляется."""

    def _collect(self, storage, ids, keyword="Python"):
        rows = []
        for value in ids:
            row = vacancy(value)
            row["source_keyword"] = keyword
            rows.append(row)
        storage.save_vacancies_incremental(pd.DataFrame(rows))

    def test_пропавшая_гаснет_и_остаётся_в_базе(self, storage):
        self._collect(storage, ["1", "2", "3"])

        погашено = storage.deactivate_missing("Python", {"1", "2"})

        всего = storage.get_all_vacancies(include_inactive=True)
        активные = storage.get_all_vacancies()
        assert погашено == 1
        assert len(всего) == 3
        assert set(активные["vacancy_id"]) == {"1", "2"}

    def test_вернувшаяся_вакансия_снова_активна(self, storage):
        self._collect(storage, ["1", "2"])
        storage.deactivate_missing("Python", {"1"})

        self._collect(storage, ["1", "2"])

        assert len(storage.get_all_vacancies()) == 2

    def test_чужой_запрос_не_гасится(self, storage):
        self._collect(storage, ["1"], keyword="Python")
        self._collect(storage, ["2"], keyword="Data Scientist")

        storage.deactivate_missing("Python", {"9"})

        активные = set(storage.get_all_vacancies()["vacancy_id"])
        assert "2" in активные
        assert "1" not in активные

    def test_пустой_список_увиденного_ничего_не_гасит(self, storage):
        """Пустой результат — признак сбоя, а не отсутствия вакансий."""
        self._collect(storage, ["1", "2"])

        погашено = storage.deactivate_missing("Python", set())

        assert погашено == 0
        assert len(storage.get_all_vacancies()) == 2

    def test_запрос_с_общим_началом_не_задевается(self, storage):
        self._collect(storage, ["1"], keyword="Python")
        self._collect(storage, ["2"], keyword="Python разработчик")

        storage.deactivate_missing("Python", {"5"})

        активные = set(storage.get_all_vacancies()["vacancy_id"])
        assert активные == {"2"}


def _index_names(storage) -> set:
    from sqlalchemy import text

    with storage.engine.connect() as conn:
        rows = conn.execute(text("PRAGMA index_list(vacancies)"))
        return {row[1] for row in rows}
