"""
Расписание сбора: установить, снять, посмотреть.

Зачем. Сбор запускался только руками: за семь месяцев — 37 запусков.
Тренды, главный товар рыночной аналитики, по такой истории не
построить, а прошедшее время не докупить.

Как устроено. Запуск по времени делает планировщик Windows: он
переживает перезагрузку и не требует, чтобы приложение было открыто.
Задание запускает `scripts/собрать.py` — тот же сбор, что с экрана.

Что задание умеет и чего нет:
  — пропущенный запуск догоняется, когда компьютер включат;
  — задание идёт от имени вошедшего пользователя и без его входа в
    систему не запускается: пароль учётной записи для этого нужен, а
    хранить его здесь негде и незачем;
  — окна не открывает: сбор пишет в журнал, а об отказе сообщает сам.

Запуск:
    python scripts/расписание.py --состояние
    python scripts/расписание.py --установить --время 03:30
    python scripts/расписание.py --установить --время 03:30 --каждые 2
    python scripts/расписание.py --снять
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import schedule  # noqa: E402

КОРЕНЬ = Path(__file__).resolve().parents[1]


def _питон_без_окна() -> Path:
    """
    Интерпретатор, который не открывает окно консоли.

    Обычный `python.exe` по расписанию показывал бы чёрное окно посреди
    чужой работы; `pythonw.exe` лежит рядом и делает то же молча.
    """
    обычный = Path(sys.executable)
    тихий = обычный.with_name("pythonw.exe")
    return тихий if тихий.exists() else обычный


def _powershell(команда: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", команда],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def команда_установки(время: str, каждые_дней: int) -> str:
    """Команда PowerShell, которая заводит задание. Отдельно — чтобы её можно было проверить без планировщика."""
    питон = _питон_без_окна()
    скрипт = КОРЕНЬ / "scripts" / "собрать.py"
    return (
        f"$a = New-ScheduledTaskAction -Execute '{питон}' -Argument '\"{скрипт}\"' -WorkingDirectory '{КОРЕНЬ}'; "
        f"$t = New-ScheduledTaskTrigger -Daily -DaysInterval {каждые_дней} -At '{время}'; "
        # StartWhenAvailable — догнать пропущенный запуск; сбор идёт и от
        # батареи; сутки — потолок, после которого зависший сбор снимается.
        "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12); "
        f"Register-ScheduledTask -TaskName '{schedule.ЗАДАНИЕ}' -Action $a -Trigger $t -Settings $s "
        "-Description 'BaseVacancy: сбор вакансий по расписанию' -Force | Out-Null"
    )


def установить(время: str, каждые_дней: int) -> int:
    try:
        datetime.strptime(время, "%H:%M")
    except ValueError:
        print(f"Время «{время}» не разобрано. Нужен вид ЧЧ:ММ, например 03:30.")
        return 2
    if каждые_дней < 1:
        print("Сбор не может идти чаще, чем раз в день.")
        return 2

    итог = _powershell(команда_установки(время, каждые_дней))
    if итог.returncode != 0:
        print("Задание в планировщике не создано:")
        print((итог.stderr or итог.stdout).strip())
        return 1

    schedule.записать(время, каждые_дней)
    как_часто = "каждый день" if каждые_дней == 1 else f"раз в {каждые_дней} дн."
    print(f"Расписание установлено: {как_часто} в {время}.")
    print(f"Задание планировщика: {schedule.ЗАДАНИЕ}")
    print("Сбор возьмёт запросы с экрана «Сбор данных»: python scripts/собрать.py --проверить")
    return 0


def снять() -> int:
    итог = _powershell(
        f"if (Get-ScheduledTask -TaskName '{schedule.ЗАДАНИЕ}' -ErrorAction SilentlyContinue) "
        f"{{ Unregister-ScheduledTask -TaskName '{schedule.ЗАДАНИЕ}' -Confirm:$false; 'снято' }} else {{ 'не было' }}"
    )
    if итог.returncode != 0:
        print("Задание не снято:")
        print((итог.stderr or итог.stdout).strip())
        return 1
    был_файл = schedule.убрать()
    было = "снято" in итог.stdout
    print("Расписание снято." if (было or был_файл) else "Расписания не было.")
    return 0


def показать() -> int:
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        с = schedule.состояние(storage)
    finally:
        storage.close()

    итог = _powershell(
        f"$t = Get-ScheduledTask -TaskName '{schedule.ЗАДАНИЕ}' -ErrorAction SilentlyContinue; "
        "if ($t) { $i = $t | Get-ScheduledTaskInfo; "
        "'{0}|{1}|{2}|{3}' -f $t.State, $i.LastRunTime.ToString('s'), $i.LastTaskResult, $i.NextRunTime.ToString('s') } else { 'нет' }"
    )
    в_планировщике = итог.stdout.strip() if итог.returncode == 0 else ""

    if not с["установлено"]:
        print("Расписание не установлено.")
        if в_планировщике and в_планировщике != "нет":
            print(f"Но задание {schedule.ЗАДАНИЕ} в планировщике есть — снимите его: python scripts/расписание.py --снять")
        return 0

    как_часто = "каждый день" if с["каждые_дней"] == 1 else f"раз в {с['каждые_дней']} дн."
    print(f"Расписание: {как_часто} в {с['время']}.")
    print(f"Следующий запуск: {с['следующий'].replace('T', ' ')}")
    print(f"Последний удачный сбор: {(с['последний_сбор'] or 'не было').replace('T', ' ')}")

    if в_планировщике == "нет" or not в_планировщике:
        print(f"ВНИМАНИЕ: задания {schedule.ЗАДАНИЕ} в планировщике нет — сбор сам не пойдёт. Установите заново.")
        return 1
    состояние_задания, последний, код, следующий = (в_планировщике.split("|") + ["", "", "", ""])[:4]
    # 267011 — код планировщика «задание ещё не запускалось».
    if код == "267011":
        print(f"Задание планировщика: {состояние_задания}; ещё не запускалось")
    else:
        print(f"Задание планировщика: {состояние_задания}; последний запуск {последний.replace('T', ' ')}, код {код}")

    if с["пропущен"]:
        print(f"ВНИМАНИЕ: сбора не было {с['дней_без_сбора']} дн. — дольше, чем обещает расписание.")
        return 1
    return 0


def main() -> int:
    разбор = argparse.ArgumentParser(description="Расписание сбора вакансий")
    действие = разбор.add_mutually_exclusive_group(required=True)
    действие.add_argument("--установить", action="store_true", help="завести задание в планировщике Windows")
    действие.add_argument("--снять", action="store_true", help="убрать задание")
    действие.add_argument("--состояние", action="store_true", help="показать расписание и его исполнение")
    разбор.add_argument("--время", default="03:30", help="время запуска, ЧЧ:ММ (по умолчанию 03:30)")
    разбор.add_argument("--каждые", type=int, default=1, help="раз во сколько дней (по умолчанию каждый день)")
    аргументы = разбор.parse_args()

    if sys.platform != "win32" and not аргументы.состояние:
        print("Расписание ставится планировщиком Windows. На этой системе заведите задание cron на scripts/собрать.py.")
        return 2

    if аргументы.установить:
        return установить(аргументы.время, аргументы.каждые)
    if аргументы.снять:
        return снять()
    return показать()


if __name__ == "__main__":
    sys.exit(main())
