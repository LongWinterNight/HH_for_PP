"""
Написания навыка в словаре (S10‑12a, S10‑12e).

Словарь правят и руками, поэтому запись построчная: проверяется, что
она попадает под нужный канон, не плодит второй ключ того же канона в
другом регистре и не трогает остальной файл.
"""

from __future__ import annotations

import pytest
import yaml

from src import skills_store

СЛОВАРЬ = """hard:
- python
- ai-инструменты
soft:
- внимательность
tools:
- figma
synonyms:
  3ds Max:
  - 3dsmax
  ChatGPT: []
  Ai-инструменты:
  - ai инструменты
"""


@pytest.fixture
def файл(tmp_path):
    путь = tmp_path / "skills.yaml"
    путь.write_text(СЛОВАРЬ, encoding="utf-8")
    return путь


def синонимы(путь):
    return yaml.safe_load(путь.read_text(encoding="utf-8"))["synonyms"]


def test_к_канону_со_списком_дописывается_в_конец_его_списка(файл):
    assert skills_store.в_синонимы("Ai-инструменты", ["ИИ-инструменты", "AI"], файл) == 2
    assert синонимы(файл)["Ai-инструменты"] == ["ai инструменты", "ии-инструменты", "ai"]


def test_канон_ищется_без_учёта_регистра(файл):
    skills_store.в_синонимы("AI-инструменты", ["ии"], файл)
    ключи = [к for к in синонимы(файл) if к.lower() == "ai-инструменты"]
    assert ключи == ["Ai-инструменты"], "второй ключ того же канона не заводится"


def test_пустой_список_канона_раскрывается(файл):
    skills_store.в_синонимы("ChatGPT", ["chat gpt", "чат gpt"], файл)
    assert синонимы(файл)["ChatGPT"] == ["chat gpt", "чат gpt"]


def test_новый_канон_встаёт_в_конец_раздела(файл):
    skills_store.в_синонимы("Function calling", ["tool calling", "c#"], файл)
    assert синонимы(файл)["Function calling"] == ["tool calling", "c#"]


def test_повтор_и_сам_канон_не_дописываются(файл):
    assert skills_store.в_синонимы("3ds Max", ["3dsmax", "3DS MAX"], файл) == 0
    assert файл.read_text(encoding="utf-8") == СЛОВАРЬ


def test_остальной_файл_не_меняется(файл):
    skills_store.в_синонимы("ChatGPT", ["chat gpt"], файл)
    прежние = СЛОВАРЬ.split("\n")
    новые = файл.read_text(encoding="utf-8").split("\n")
    добавлено = [с for с in новые if с not in прежние]
    assert добавлено == ["  ChatGPT:", "  - chat gpt"]
    assert yaml.safe_load(файл.read_text(encoding="utf-8"))["hard"] == ["python", "ai-инструменты"]
