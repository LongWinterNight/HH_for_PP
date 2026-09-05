# -*- coding: utf-8 -*-
"""
Помощник для OAuth-авторизации HH.ru.

С 2025 года HH.ru закрыл анонимный доступ к поиску вакансий (/vacancies
возвращает 403 forbidden). Нужен access_token приложения.

Использование:

  1) Если у тебя уже есть готовый access_token (со страницы dev.hh.ru/admin):
       python scripts/hh_token.py --check <ACCESS_TOKEN>
     Скрипт проверит, открывает ли токен доступ к /vacancies, и покажет,
     что дописать в .env.

  2) Если у тебя есть client_id и client_secret приложения:
       python scripts/hh_token.py --client-id <ID> --client-secret <SECRET>
     Скрипт сам получит access_token (grant_type=client_credentials),
     проверит доступ к вакансиям и выведет строку для .env.

  Необязательный флаг --proxy http://127.0.0.1:7899 — гнать запросы через
  прокси (если твой IP заблокирован сайтом hh.ru по региону).
"""
import argparse
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")

TOKEN_URL = "https://api.hh.ru/token"
VACANCIES_URL = "https://api.hh.ru/vacancies"
UA = "HHAnalytics/1.0 (safanch2705@gmail.com)"


def _session(proxy: str | None) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "HH-User-Agent": UA})
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    return s


def get_token(client_id: str, client_secret: str, proxy: str | None) -> str:
    """Получить access_token приложения через client_credentials."""
    s = _session(proxy)
    resp = s.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"❌ Не удалось получить токен ({resp.status_code}): {resp.text[:300]}")
        sys.exit(1)
    token = resp.json().get("access_token", "")
    print(f"✅ Токен получен (длина {len(token)} символов)")
    return token


def check_token(token: str, proxy: str | None) -> bool:
    """Проверить, открывает ли токен доступ к поиску вакансий."""
    s = _session(proxy)
    s.headers["Authorization"] = f"Bearer {token}"
    resp = s.get(VACANCIES_URL, params={"text": "python", "per_page": 1}, timeout=30)
    print(f"GET /vacancies → HTTP {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Доступ есть! Найдено вакансий: {data.get('found')}")
        print("\nДобавь в .env:")
        print(f"HH_ACCESS_TOKEN={token}")
        if proxy:
            print(f"HH_PROXY={proxy}")
        return True
    print(f"❌ Доступа нет: {resp.text[:300]}")
    if resp.status_code == 403:
        print(
            "\nПодсказка: токен приложения (client_credentials) может не давать "
            "доступ к /vacancies. Тогда нужен пользовательский токен "
            "(authorization_code с логином) — напиши, помогу настроить."
        )
    return False


def main() -> None:
    p = argparse.ArgumentParser(description="OAuth-помощник HH.ru")
    p.add_argument("--check", metavar="TOKEN", help="проверить готовый access_token")
    p.add_argument("--client-id")
    p.add_argument("--client-secret")
    p.add_argument("--proxy", default=None, help="http://127.0.0.1:7899")
    args = p.parse_args()

    if args.check:
        check_token(args.check, args.proxy)
    elif args.client_id and args.client_secret:
        token = get_token(args.client_id, args.client_secret, args.proxy)
        check_token(token, args.proxy)
    else:
        p.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
