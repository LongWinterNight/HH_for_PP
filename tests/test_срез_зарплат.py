"""
Срез зарплат: окно «Распределение зарплат» в раскрытом виде.

Проверяется расчёт без веб-сервера: срезы, корзины с отметкой медианы,
зарплатные уровни и состав корзины. Главное правило — блоки окна
описывают одну и ту же выборку, поэтому их числа обязаны сходиться.

Запуск: pytest tests/test_срез_зарплат.py -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import salary_slice
from src.salary_slice import Срез, формат_работы

ОПЫТ = ["Нет опыта", "От 1 года до 3 лет", "От 3 до 6 лет", "Более 6 лет"]


def _база(сейчас=None) -> pd.DataFrame:
    """Сто двадцать вакансий: четыре уровня опыта, три сферы, три формата."""
    сейчас = сейчас or pd.Timestamp.now(tz="UTC")
    строки = []
    for i in range(120):
        уровень = i % 4
        строки.append({
            "vacancy_id": str(i),
            "vacancy_name": f"Вакансия {i}",
            "employer_name": f"Компания {i}",
            # Зарплата растёт с опытом — чтобы лестница уровней была видна.
            "salary_from": 50_000 + уровень * 40_000 + (i % 7) * 3_000,
            "salary_currency": "RUB",
            "salary_from_rub": 50_000 + уровень * 40_000 + (i % 7) * 3_000,
            "salary_doubt": None,
            "salary_mode": "MONTH",
            "experience": ОПЫТ[уровень],
            "source_keyword": ["Python", "Дизайнер", "HR"][i % 3],
            "schedule": ["Удалённо · 5/2", "На месте работодателя · 5/2", "Гибрид · 5/2"][i % 3],
            "area": "Москва" if i % 2 else "Казань",
            "published_at": (сейчас - pd.Timedelta(days=i)).isoformat(),
            "hard_skills": "python, sql" if i % 3 == 0 else "figma",
            "tools": "git",
        })
    return pd.DataFrame(строки)


@pytest.fixture
def база() -> pd.DataFrame:
    return _база()


class TestФорматРаботы:

    @pytest.mark.parametrize("график, ожидается", [
        ("На месте работодателя · 5/2", "На месте"),
        ("Удалённо · 5/2", "Удалённо"),
        ("Удалённо · Свободный", "Удалённо"),
        ("Гибрид · 5/2", "Гибрид"),
        ("На месте работодателя, Гибрид · 5/2", "На выбор"),
        ("На месте работодателя, Удалённо, Гибрид · 5/2", "На выбор"),
        ("На месте работодателя, Разъездной · 5/2", "На месте"),
        ("Удалённо", "Удалённо"),
        ("", "Не указан"),
        (None, "Не указан"),
    ])
    def test_написания_источника_сводятся_к_немногим_значениям(self, график, ожидается):
        assert формат_работы(график) == ожидается

    def test_несколько_форматов_не_засчитываются_удалёнке(self):
        # Иначе доля удалённой работы завышалась бы каждой вакансией,
        # где она названа одним из трёх вариантов.
        assert формат_работы("На месте работодателя, Удалённо · 5/2") != "Удалённо"


class TestСрез:

    def test_пустой_срез_берёт_всю_выборку(self, база):
        ответ = salary_slice.собрать(база, Срез())
        assert ответ["sample"] == 120 and ответ["slice_total"] == 120

    def test_срез_по_опыту_сужает_и_выборку_и_гистограмму(self, база):
        ответ = salary_slice.собрать(база, Срез(опыт="Нет опыта"))
        assert ответ["sample"] == 30
        assert sum(к["count"] for к in ответ["histogram"]) == 30

    def test_срезы_складываются(self, база):
        ответ = salary_slice.собрать(база, Срез(опыт="Нет опыта", сфера="Python", формат="Удалённо"))
        ожидается = len(база[(база["experience"] == "Нет опыта") & (база["source_keyword"] == "Python")
                             & (база["schedule"].str.startswith("Удалённо"))])
        assert ответ["sample"] == ожидается > 0

    def test_период_считается_по_дате_публикации(self, база):
        ответ = salary_slice.собрать(база, Срез(период="week"))
        assert 6 <= ответ["sample"] <= 8, "вакансии публиковались по одной в день"

    def test_неизвестная_сфера_даёт_пустой_срез_а_не_ошибку(self, база):
        ответ = salary_slice.собрать(база, Срез(сфера="такой сферы нет"))
        assert ответ["sample"] == 0 and ответ["histogram"] == [] and ответ["stats"] == {}
        assert ответ["bucket"] is None

    def test_вакансии_без_зарплаты_в_срезе_есть_а_в_расчёте_нет(self, база):
        база.loc[база.index[:20], ["salary_from", "salary_from_rub"]] = None
        ответ = salary_slice.собрать(база, Срез())
        assert ответ["slice_total"] == 120 and ответ["sample"] == 100

    def test_чужая_валюта_в_валютном_виде_не_считается(self, база):
        база.loc[база.index[:10], "salary_currency"] = "KZT"
        assert salary_slice.собрать(база, Срез())["sample"] == 110
        assert salary_slice.собрать(база, Срез(вид="rub"))["sample"] == 120, "в рублёвом виде считаются все валюты"

    def test_средней_в_ответе_нет(self, база):
        текст = str(salary_slice.собрать(база, Срез())).lower()
        assert "avg" not in текст and "mean" not in текст and "average" not in текст


class TestГистограмма:

    def test_маркер_стоит_ровно_на_одной_корзине_и_в_ней_медиана(self, база):
        ответ = salary_slice.собрать(база, Срез())
        отмеченные = [к for к in ответ["histogram"] if к["has_median"]]
        assert len(отмеченные) == 1
        корзина = отмеченные[0]
        assert корзина["from"] <= ответ["stats"]["median"] <= корзина["to"]
        assert ответ["histogram"][ответ["median_bin"]] is корзина

    def test_доли_корзин_складываются_в_целое(self, база):
        доли = [к["share"] for к in salary_slice.собрать(база, Срез())["histogram"]]
        assert abs(sum(доли) - 100) < 0.6

    def test_малая_выборка_гистограммы_не_даёт(self, база):
        ответ = salary_slice.собрать(база.head(4), Срез())
        assert ответ["histogram"] == [] and ответ["stats"] == {}


class TestУровни:

    def test_опыт_идёт_по_росту_стажа(self, база):
        уровни = salary_slice.собрать(база, Срез(), по="experience")["levels"]["items"]
        assert [у["label"] for у in уровни] == ОПЫТ
        медианы = [у["median"] for у in уровни]
        assert медианы == sorted(медианы), "в этих данных зарплата растёт с опытом"

    def test_вилка_охватывает_медиану(self, база):
        for уровень in salary_slice.собрать(база, Срез(), по="sphere")["levels"]["items"]:
            assert уровень["q1"] <= уровень["median"] <= уровень["q3"]

    def test_слабая_группа_опыта_остаётся_но_без_чисел(self, база):
        редкая = база[база["experience"] == "Более 6 лет"].index[3:]
        уровни = salary_slice.собрать(база.drop(редкая), Срез(), по="experience")["levels"]["items"]
        слабая = next(у for у in уровни if у["label"] == "Более 6 лет")
        assert слабая["weak"] is True and слабая["median"] is None and слабая["sample"] == 3

    def test_слабая_сфера_уходит_из_списка_и_названа_числом(self, база):
        база.loc[база.index[:2], "source_keyword"] = "Редкая сфера"
        уровни = salary_slice.собрать(база, Срез(), по="sphere")["levels"]
        assert "Редкая сфера" not in [у["label"] for у in уровни["items"]]
        assert уровни["hidden_small"] == 1

    def test_формат_работы_раскладывается_на_уровни(self, база):
        подписи = {у["label"] for у in salary_slice.собрать(база, Срез(), по="format")["levels"]["items"]}
        assert подписи == {"Удалённо", "На месте", "Гибрид"}

    def test_срез_по_своему_измерению_список_уровней_не_схлопывает(self, база):
        # Замечание владельца: после нажатия на «Более 6 лет» в списке
        # оставалась одна строка, и вернуться к остальным было нечем.
        ответ = salary_slice.собрать(база, Срез(опыт="Более 6 лет"), по="experience")
        assert [у["label"] for у in ответ["levels"]["items"]] == ОПЫТ
        assert ответ["sample"] == 30, "гистограмма и числа окна при этом сужены"

    def test_чужие_срезы_на_список_уровней_действуют(self, база):
        все = salary_slice.собрать(база, Срез(), по="experience")["levels"]["items"]
        удалёнка = salary_slice.собрать(база, Срез(формат="Удалённо", опыт="Нет опыта"), по="experience")["levels"]["items"]
        assert len(удалёнка) == 4, "срез по опыту списку опыта не мешает"
        assert sum(у["sample"] for у in удалёнка) < sum(у["sample"] for у in все), "а срез по формату — сужает"

    def test_незнакомое_измерение_не_роняет_расчёт(self, база):
        assert salary_slice.собрать(база, Срез(), по="выдумка")["levels"]["by"] == "experience"


class TestЧислаСходятся:
    """Строка уровней обещает выборку — нажатие на неё обязано дать ту же."""

    def test_счёт_строки_уровней_равен_выборке_после_среза_по_ней(self, база):
        # Копии одной вакансии по городам с разным опытом: именно на них
        # счёт расходился — «по 449» в строке и 453 после нажатия.
        копии = база.head(12).copy()
        копии["vacancy_id"] = [f"копия-{i}" for i in range(12)]
        копии["experience"] = "Нет опыта"
        с_копиями = pd.concat([база, копии], ignore_index=True)

        уровни = salary_slice.собрать(с_копиями, Срез(), по="experience")["levels"]["items"]
        for уровень in уровни:
            после = salary_slice.собрать(с_копиями, Срез(опыт=уровень["label"]))
            assert после["sample"] == уровень["sample"], уровень["label"]

    def test_счёт_в_меню_равен_выборке_после_выбора(self, база):
        меню = salary_slice.собрать(база, Срез())["options"]
        for пункт in меню["sphere"]:
            assert salary_slice.собрать(база, Срез(сфера=пункт["value"]))["sample"] == пункт["count"]
        for пункт in меню["format"]:
            assert salary_slice.собрать(база, Срез(формат=пункт["value"]))["sample"] == пункт["count"]


class TestСоставКорзины:

    def test_без_выбора_показана_корзина_с_медианой(self, база):
        ответ = salary_slice.собрать(база, Срез())
        assert ответ["bucket"]["index"] == ответ["median_bin"]

    def test_счёт_состава_сходится_с_высотой_столбца(self, база):
        ответ = salary_slice.собрать(база, Срез())
        for номер, корзина in enumerate(ответ["histogram"]):
            состав = salary_slice.собрать(база, Срез(), корзина=номер)["bucket"]
            assert состав["count"] == корзина["count"], f"корзина {номер}"
            assert sum(п["value"] for п in состав["experience"]) == корзина["count"]

    def test_навык_считается_один_раз_на_вакансию(self, база):
        ответ = salary_slice.собрать(база, Срез(), корзина=0)
        навыки = {п["label"]: п["value"] for п in ответ["bucket"]["skills"]}
        assert навыки["git"] == ответ["bucket"]["count"], "git есть у каждой вакансии — и ровно по разу"

    def test_при_равном_счёте_порядок_навыков_задан_а_не_случаен(self, база):
        # У каждой вакансии свой редкий навык — все со счётом «один».
        # Прежде в список из восьми попадали разные навыки от запуска к
        # запуску: порядок зависел от обхода множества.
        база["hard_skills"] = [f"навык-{i % 40:02d}" for i in range(len(база))]
        база["tools"] = ""
        корзина = salary_slice.собрать(база, Срез(), корзина=0)["bucket"]
        подписи = [п["label"] for п in корзина["skills"]]
        счёт = [п["value"] for п in корзина["skills"]]
        assert счёт == sorted(счёт, reverse=True)
        for число in set(счёт):
            равные = [п for п, ч in zip(подписи, счёт) if ч == число]
            assert равные == sorted(равные), "при равном счёте — по алфавиту"

    def test_последняя_корзина_без_верхней_границы(self, база):
        корзины = salary_slice.собрать(база, Срез())["histogram"]
        assert salary_slice.собрать(база, Срез(), корзина=len(корзины) - 1)["bucket"]["to"] is None

    def test_номер_несуществующей_корзины_возвращает_к_медианной(self, база):
        ответ = salary_slice.собрать(база, Срез(), корзина=99)
        assert ответ["bucket"]["index"] == ответ["median_bin"]


class TestВарианты:

    def test_меню_не_сужается_выбранным_срезом(self, база):
        меню = salary_slice.собрать(база, Срез(опыт="Нет опыта", сфера="Python"))["options"]
        assert {п["value"] for п in меню["sphere"]} == {"Python", "Дизайнер", "HR"}
        assert [п["value"] for п in меню["experience"]] == ОПЫТ

    def test_пункт_без_зарплат_в_меню_не_попадает(self, база):
        база.loc[база["source_keyword"] == "HR", ["salary_from", "salary_from_rub"]] = None
        меню = salary_slice.собрать(база, Срез())["options"]
        assert "HR" not in {п["value"] for п in меню["sphere"]}


class TestРядВоВремени:
    """Блок времени: медиана и вилка по периодам, объём, сравнение рядов."""

    def test_недели_идут_без_пропусков_и_последняя_не_закрыта(self, база):
        ряд = salary_slice.собрать(база, Срез(), шаг="week")["trend"]
        периоды = ряд["periods"]
        assert ряд["step"] == "week" and len(периоды) >= 16, "сто двадцать дней — это семнадцать недель"
        assert [п["open"] for п in периоды] == [False] * (len(периоды) - 1) + [True]
        assert sum(п["sample"] for п in периоды) == 120, "ни одна вакансия не потерялась между неделями"

    def test_месячный_шаг_даёт_месяцы(self, база):
        ряд = salary_slice.собрать(база, Срез(), шаг="month")["trend"]
        assert ряд["step"] == "month" and 4 <= len(ряд["periods"]) <= 6
        assert sum(п["sample"] for п in ряд["periods"]) == 120

    def test_незнакомый_шаг_считается_неделями(self, база):
        assert salary_slice.собрать(база, Срез(), шаг="выдумка")["trend"]["step"] == "week"

    def test_вилка_охватывает_медиану_а_малый_период_без_чисел(self, база):
        for период in salary_slice.собрать(база, Срез(), шаг="week")["trend"]["periods"]:
            if период["sample"] < salary_slice.МАЛО:
                assert период["median"] is None and период["q1"] is None, период["title"]
            else:
                assert период["q1"] <= период["median"] <= период["q3"], период["title"]

    def test_сравнение_по_опыту_даёт_ряды_по_росту_стажа(self, база):
        ряд = salary_slice.собрать(база, Срез(), шаг="month", сравнить="experience")["trend"]
        assert [р["label"] for р in ряд["series"]] == ОПЫТ and ряд["by"] == "experience"
        for р in ряд["series"]:
            assert len(р["points"]) == len(ряд["periods"]), "у каждого ряда точка на каждый период сетки"
            assert sum(т["sample"] for т in р["points"]) == р["sample"]

    def test_срез_по_своему_измерению_ряды_сравнения_не_схлопывает(self, база):
        ряд = salary_slice.собрать(база, Срез(опыт="Нет опыта"), шаг="month", сравнить="experience")["trend"]
        assert len(ряд["series"]) == 4, "иначе после выбора уровня сравнивать было бы не с чем"

    def test_без_сравнения_рядов_нет(self, база):
        ряд = salary_slice.собрать(база, Срез())["trend"]
        assert ряд["series"] == [] and ряд["by"] == ""

    def test_рядов_не_больше_четырёх(self, база):
        база["source_keyword"] = [f"сфера {i % 9}" for i in range(len(база))]
        ряд = salary_slice.собрать(база, Срез(), шаг="month", сравнить="sphere")["trend"]
        assert len(ряд["series"]) == salary_slice.РЯДОВ

    def test_итог_не_строится_от_ненадёжного_периода(self, база):
        # Неделя с семью вакансиями даёт точку на графике, но не конец
        # фразы «медиана выросла на 25 %»: так сравнивали пятнадцать
        # вакансий августа с пятью сотнями октября.
        ряд = salary_slice.собрать(база, Срез(), шаг="week")["trend"]
        assert all(п["sample"] < salary_slice.НАДЁЖНО for п in ряд["periods"])
        assert ряд["change"] is None

    def test_изменение_считается_между_закрытыми_периодами(self, база, monkeypatch):
        monkeypatch.setattr(salary_slice, "НАДЁЖНО", 5)
        ряд = salary_slice.собрать(база, Срез(), шаг="week")["trend"]
        открытый = ряд["periods"][-1]
        изменение = ряд["change"]
        assert изменение and изменение["to"] != открытый["title"], "неполная неделя в итог не идёт"
        ожидается = round((изменение["to_median"] / изменение["from_median"] - 1) * 100, 1)
        assert изменение["percent"] == ожидается

    def test_пустой_срез_ряда_не_даёт(self, база):
        ряд = salary_slice.собрать(база, Срез(сфера="такой сферы нет"))["trend"]
        assert ряд["periods"] == [] and ряд["change"] is None

    def test_сетка_ограничена_последними_периодами(self):
        старая = _база()
        старая["published_at"] = [
            (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=i * 4)).isoformat() for i in range(len(старая))
        ]
        периоды = salary_slice.собрать(старая, Срез(), шаг="week")["trend"]["periods"]
        assert len(периоды) == 26, "полтора года по четыре дня — но на оси последние полгода"


class TestПравилаРяда:
    """
    Правила, которые прежде защищал тест окна «Медиана по месяцам».

    Окно убрано 13.10.2026 — его заменил блок времени в раскрытом окне
    зарплат, — а правила остались: ряд во времени считается по тем же
    зарплатам, что и остальные числа продукта.
    """

    def _неделя(self, суммы, **поля) -> pd.DataFrame:
        """Вакансии одной закрытой недели — прошлой."""
        дата = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
        return pd.DataFrame([
            {"vacancy_id": f"в{i}", "vacancy_name": f"Вакансия {i}", "employer_name": f"Компания {i}",
             "salary_from": сумма, "salary_from_rub": сумма, "salary_currency": "RUB", "salary_mode": None,
             "experience": "Нет опыта", "source_keyword": "Python", "schedule": "Удалённо", "area": "Москва",
             "published_at": дата.isoformat(), "hard_skills": "", "tools": "", **поля}
            for i, сумма in enumerate(суммы)
        ])

    def _точка(self, df, срез=None):
        ряд = salary_slice.собрать(df, срез or Срез(), шаг="week")["trend"]["periods"]
        return next(п for п in ряд if п["sample"])

    ОБЫЧНЫЕ = [80000, 85000, 90000, 95000, 100000, 105000]

    def test_медиана_устойчива_к_выбросу(self):
        # Ради этого свойства средняя и заменена медианой: одна вакансия
        # на 800 000 сдвинула бы среднюю с 92 500 до 193 571.
        было = self._точка(self._неделя(self.ОБЫЧНЫЕ))["median"]
        стало = self._точка(self._неделя(self.ОБЫЧНЫЕ + [800000]))["median"]
        assert было == 92500 and стало == 95000, "медиана сдвинулась на один шаг выборки"

    def test_часовая_ставка_в_ряд_не_входит(self):
        # Правило Л: «1 000 ₽ за час» — честная ставка, но среди месячных
        # окладов ей делать нечего.
        df = pd.concat([self._неделя(self.ОБЫЧНЫЕ), self._неделя([1000, 1200], salary_mode="HOUR")], ignore_index=True)
        df["vacancy_name"] = [f"Вакансия {i}" for i in range(len(df))]
        точка = self._точка(df)
        assert точка["sample"] == 6 and точка["median"] == 92500

    def test_сомнительная_сумма_в_ряд_не_входит(self):
        # Правило E8: «50 ₽» в месяц — опечатка работодателя.
        точка = self._точка(self._неделя(self.ОБЫЧНЫЕ + [50]))
        assert точка["sample"] == 6 and точка["median"] == 92500

    def test_рублёвый_вид_считает_по_эквиваленту(self):
        df = self._неделя(self.ОБЫЧНЫЕ)
        df["salary_from_rub"] = 40000.0
        assert self._точка(df)["median"] == 92500
        assert self._точка(df, Срез(вид="rub"))["median"] == 40000


class TestСрезПоРегиону:
    """
    Регион как срез окна зарплат. Сама география — страны, регионы,
    города — считается в `src/geo_slice.py` и проверяется в
    `tests/test_география.py`.
    """

    def test_срез_по_региону_точный_а_не_по_вхождению(self, база):
        # «Ростов» не должен захватить «Ростов-на-Дону».
        база.loc[база.index[:10], "area"] = "Ростов"
        база.loc[база.index[10:30], "area"] = "Ростов-на-Дону"
        assert salary_slice.собрать(база, Срез(регион="Ростов"))["sample"] == 10
        assert salary_slice.собрать(база, Срез(регион="Ростов-на-Дону"))["sample"] == 20

    def test_счёт_строки_региона_равен_выборке_после_среза_по_нему(self, база):
        for уровень in salary_slice.собрать(база, Срез(), по="area")["levels"]["items"]:
            assert salary_slice.собрать(база, Срез(регион=уровень["label"]))["sample"] == уровень["sample"]

    def test_уровни_по_региону_не_схлопываются_при_выбранном_регионе(self, база):
        уровни = salary_slice.собрать(база, Срез(регион="Москва"), по="area")["levels"]["items"]
        assert {у["label"] for у in уровни} == {"Москва", "Казань"}
