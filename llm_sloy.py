#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM-слой генератора мероприятий — Ломтик Л4.1 (Спека № 4, разделы 2.1–2.3).

Инфраструктура вызова LLM без реального промпта (Л4.2) и без UI (Л4.4):

  * klient()              — конфигурация из env; нет ключа → «недоступно»,
                            сервис не падает никогда (спека 2.1).
  * vyzov()               — POST на chat-completions-совместимый endpoint,
                            response_format=json_object, таймаут 30 с,
                            одна повторная попытка при сетевой ошибке,
                            кэш по sha256, учёт расхода и месячный лимит.
  * vyzov_s_meta()        — то же + метаданные (флаг кэша, токены) для
                            тестов и прогона.
  * validirovat_otvet_llm — QC-гейты 1–3 спеки 2.3 (детерминированные):
                            схема JSON; id признаков только из справочника
                            15 (otbor_potok.ПРИЗНАКИ_ПОТЕРЬ); id инструментов
                            только из biblioteka_instrumentov; каждое
                            мероприятие привязано к причине, причина — к
                            ветке; каждый шаг 5-почему имеет опору на факт
                            входа или пометку «нужен факт».
  * sobrat_prompty()      — заготовка промпта: система «методолог ФЦК» с
                            запретами (не считать цифры, не выдумывать
                            инструменты/признаки, только id из справочников,
                            строгий JSON по схеме, деловой русский стиль без
                            ИИ-оборотов); контекст: вход + прогоны + корпус
                            (последние два — параметры-заглушки None, Л4.2/Л4.3).
  * glubokiy_ili_bystriy()— обёртка-откат (спека 2.1, 3): LLM недоступен /
                            лимит исчерпан / QC fail после одного повтора →
                            детерминированный сгенерировать() с пометкой
                            rezhim="bystriy_otkat".

Хранилище кэша и расхода: ТА ЖЕ БД ui/agent_ceh.db (таблицы llm_kesh и
llm_rashod), а не отдельный файл — менее инвазивно: прод-хранилище
(volume /app/data + симлинк entrypoint.sh) и миграция при старте
(CREATE TABLE IF NOT EXISTS, как СХЕМА_SQL в ui/app.py) уже покрывают её;
отдельный файл в /app/ui не переживал бы пересоздание контейнера.
Переопределение пути для тестов: env LLM_DB_PATH.

env-переменные (значения — на сервере, в репозиторий не вбиваются):
  LLM_API_KEY          — ключ API; без него режим «недоступно», только откат.
  LLM_BASE_URL         — база chat-completions-совместимого API
                         (дефолт-заглушка https://api.openai.com/v1; выбор
                         российского API — отдельным протоколом, спека 2.1).
  LLM_MODEL            — модель (дефолт-заглушка «gpt-4o-mini»).
  LLM_MONTH_LIMIT_RUB  — месячный лимит расхода, руб. (дефолт 1000).
  LLM_PRICE_1K_TOK_RUB — оценка цены за 1000 токенов для учёта расхода
                         (дефолт 0,5 руб. — консервативно; уточняется
                         протоколом при выборе API).
"""

import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from otbor_potok import ПРИЗНАКИ_ПОТЕРЬ
from biblioteka_instrumentov import БИБЛИОТЕКА, ЦИФРОВЫЕ_ПО_ID
import meropriyatiya as _детерминированный

# Версия промпта входит в ключ кэша: смена формулировок (Л4.2) автоматически
# инвалидирует старые записи.
ВЕРСИЯ_ПРОМПТА = "л4.1-заготовка"

ТАЙМАУТ_С = 30          # спека 2.1
_ПОВТОРОВ_СЕТЬ = 1      # одна повторная попытка при сетевой ошибке

# Дефолты-заглушки (реальный API выбирается отдельным протоколом, спека 2.1)
_ДЕФОЛТ_BASE_URL = "https://api.openai.com/v1"
_ДЕФОЛТ_MODEL = "gpt-4o-mini"
_ДЕФОЛТ_ЛИМИТ_РУБ = 1000.0
_ДЕФОЛТ_ЦЕНА_1К_РУБ = 0.5

# Путь к БД: та же agent_ceh.db, что у ui/app.py (см. docstring модуля).
_ДЕФОЛТ_БД = Path(__file__).resolve().parent / "ui" / "agent_ceh.db"

# Справочник допустимых id признаков потерь — 15 ключей пп. 6.2–6.16
# Прил. № 5 (импорт из otbor_potok, гейт 1 спеки 2.3).
ПРИЗНАКИ_ID = frozenset(ключ for ключ, _ in ПРИЗНАКИ_ПОТЕРЬ)

# Справочник допустимых id инструментов (гейт 1 спеки 2.3): id цифровой
# ветки (ЦИФРОВЫЕ_ПО_ID) + названия instrument базовой библиотеки — у базовых
# инструментов машинного id нет, их название играет роль id (задокументировано).
ИНСТРУМЕНТЫ_ID = frozenset(
    list(ЦИФРОВЫЕ_ПО_ID.keys())
    + [ин["instrument"] for инструменты in БИБЛИОТЕКА.values() for ин in инструменты]
)

# Классы опоры шага 5-почему (гейт 3): evidence-классы сохраняются (спека 2.3).
_ОПОРА_ФАКТ = "fakt_vhoda"
_ОПОРА_НУЖЕН = "nuzhen_fakt"


class LLMError(Exception):
    """Ошибка LLM-слоя. klass: «nedostupno» (нет ключа/конфигурации),
    «setevaya» (сеть/таймаут после повтора), «kontrakt» (ответ не JSON /
    не та структура), «limit» (исчерпан месячный лимит, пометка «лимит»)."""

    def __init__(self, soobshchenie, klass="setevaya"):
        super().__init__(soobshchenie)
        self.klass = klass


# ---------------------------------------------------------------------------
# Конфигурация (env)
# ---------------------------------------------------------------------------

def klient():
    """Конфигурация LLM из env. Нет LLM_API_KEY → dostupno=False: режим
    «недоступно», вызовы не выполняются, исключение не бросается."""
    ключ = (os.environ.get("LLM_API_KEY") or "").strip()
    try:
        лимит = float(os.environ.get("LLM_MONTH_LIMIT_RUB") or _ДЕФОЛТ_ЛИМИТ_РУБ)
    except ValueError:
        лимит = _ДЕФОЛТ_ЛИМИТ_РУБ
    try:
        цена = float(os.environ.get("LLM_PRICE_1K_TOK_RUB") or _ДЕФОЛТ_ЦЕНА_1К_РУБ)
    except ValueError:
        цена = _ДЕФОЛТ_ЦЕНА_1К_РУБ
    return {
        "dostupno": bool(ключ),
        "api_key": ключ or None,
        "base_url": (os.environ.get("LLM_BASE_URL") or _ДЕФОЛТ_BASE_URL).rstrip("/"),
        "model": os.environ.get("LLM_MODEL") or _ДЕФОЛТ_MODEL,
        "month_limit_rub": лимит,
        "price_1k_tok_rub": цена,
    }


# ---------------------------------------------------------------------------
# Хранилище: кэш (llm_kesh) и учёт расхода (llm_rashod) в ui/agent_ceh.db
# ---------------------------------------------------------------------------

_СХЕМА_LLM = """
CREATE TABLE IF NOT EXISTS llm_kesh (
  hesh TEXT PRIMARY KEY,
  otvet_json TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  sozdan TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_rashod (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data TEXT NOT NULL,
  tokeny_in INTEGER NOT NULL DEFAULT 0,
  tokeny_out INTEGER NOT NULL DEFAULT 0,
  otsenka_rub REAL NOT NULL DEFAULT 0,
  model TEXT NOT NULL DEFAULT ''
);
"""


def _путь_бд():
    return Path(os.environ.get("LLM_DB_PATH") or _ДЕФОЛТ_БД)


def init_llm_db():
    """Миграция таблиц llm_* при старте/первом обращении — CREATE TABLE
    IF NOT EXISTS, как СХЕМА_SQL в ui/app.py (прод-БД из volume дополняется
    на месте, локальная БД на прод не копируется)."""
    путь = _путь_бд()
    путь.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(путь) as con:
        con.executescript(_СХЕМА_LLM)


def _ключ_кэша(система, контекст, model):
    сырьё = json.dumps({"sistema": система, "kontekst": контекст,
                        "model": model, "versiya_prompta": ВЕРСИЯ_ПРОМПТА},
                       ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(сырьё.encode("utf-8")).hexdigest()


def kesh(система, контекст, model):
    """Поиск в кэше по sha256(вход + версия промпта + модель).
    Попадание = бесплатно (спека 2.1): возвращает распарсенный JSON или None."""
    init_llm_db()
    with sqlite3.connect(_путь_бд()) as con:
        row = con.execute("SELECT otvet_json FROM llm_kesh WHERE hesh = ?",
                          (_ключ_кэша(система, контекст, model),)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None  # битая запись не считается попаданием


def _записать_кэш(система, контекст, model, js):
    init_llm_db()
    with sqlite3.connect(_путь_бд()) as con:
        con.execute(
            "INSERT OR REPLACE INTO llm_kesh (hesh, otvet_json, model, sozdan)"
            " VALUES (?, ?, ?, ?)",
            (_ключ_кэша(система, контекст, model),
             json.dumps(js, ensure_ascii=False), model,
             date.today().isoformat()))


# ---------------------------------------------------------------------------
# Учёт расхода и месячный лимит
# ---------------------------------------------------------------------------

def _расход_за_месяц(сегодня=None):
    """Сумма оценки расхода (руб.) за текущий месяц по llm_rashod."""
    init_llm_db()
    месяц = (сегодня or date.today()).isoformat()[:7]  # ГГГГ-ММ
    with sqlite3.connect(_путь_бд()) as con:
        row = con.execute(
            "SELECT COALESCE(SUM(otsenka_rub), 0) FROM llm_rashod"
            " WHERE data LIKE ?", (месяц + "-%",)).fetchone()
    return float(row[0])


def uchyot_rashoda(tokeny_in, tokeny_out, model, klient_cfg, сегодня=None):
    """Записать расход вызова в llm_rashod (дата, токены, оценка руб.).
    Перед записью проверяет месячный лимит из env: превышение → LLMError
    с пометкой «лимит» (спека 5: «лимит руб./мес в env»)."""
    оценка = round((tokeny_in + tokeny_out) / 1000.0
                   * klient_cfg["price_1k_tok_rub"], 4)
    потрачено = _расход_за_месяц(сегодня)
    if потрачено + оценка > klient_cfg["month_limit_rub"]:
        raise LLMError(
            f"месячный лимит LLM исчерпан («лимит»): потрачено "
            f"{потрачено:.2f} руб. из {klient_cfg['month_limit_rub']:.2f} руб.",
            klass="limit")
    init_llm_db()
    with sqlite3.connect(_путь_бд()) as con:
        con.execute(
            "INSERT INTO llm_rashod (data, tokeny_in, tokeny_out, otsenka_rub,"
            " model) VALUES (?, ?, ?, ?, ?)",
            ((сегодня or date.today()).isoformat(), int(tokeny_in),
             int(tokeny_out), оценка, model))
    return оценка


# ---------------------------------------------------------------------------
# Вызов chat-completions-совместимого API (stdlib urllib, без внешних пакетов)
# ---------------------------------------------------------------------------

def _оценка_токенов(текст):
    """Грубая оценка токенов (~4 символа/токен), если API не вернул usage."""
    return max(1, len(текст) // 4)


def _post_chat(cfg, система, контекст, shema_json):
    """Один HTTP-вызов. response_format=json_object запрашивается всегда;
    если API вернул 400 с упоминанием response_format (режим не
    поддерживается) — повтор без него."""
    тело = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": система},
            {"role": "user", "content": контекст},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    if shema_json:
        тело["messages"][0]["content"] += (
            "\n\nСхема ответа (строгий JSON):\n"
            + json.dumps(shema_json, ensure_ascii=False))
    payload = json.dumps(тело, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        cfg["base_url"] + "/chat/completions", data=payload, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {cfg['api_key']}"})
    try:
        with urllib.request.urlopen(req, timeout=ТАЙМАУТ_С) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        тело_ош = ""
        try:
            тело_ош = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            pass
        if e.code == 400 and "response_format" in тело_ош:
            # API без JSON-режима: честный повтор без response_format
            del тело["response_format"]
            payload = json.dumps(тело, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                cfg["base_url"] + "/chat/completions", data=payload,
                method="POST",
                headers={"Content-Type": "application/json; charset=utf-8",
                         "Authorization": f"Bearer {cfg['api_key']}"})
            with urllib.request.urlopen(req, timeout=ТАЙМАУТ_С) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise LLMError(f"HTTP {e.code} от LLM API: {тело_ош or e.reason}",
                       klass="kontrakt" if e.code < 500 else "setevaya")


def vyzov_s_meta(prompt_sistema, prompt_kontekst, shema_json=None):
    """Вызов LLM с метаданными. Возвращает (js, meta), где
    meta = {"iz_kesha": bool, "tokeny_in": int, "tokeny_out": int,
            "otsenka_rub": float|None, "model": str}.
    Бросает LLMError (nedostupno/setevaya/kontrakt/limit)."""
    cfg = klient()
    if not cfg["dostupno"]:
        raise LLMError("LLM_API_KEY не задан — режим «недоступно», "
                       "вызов не выполнялся", klass="nedostupno")

    # Кэш: попадание = бесплатно, до проверки лимита (спека 2.1)
    из_кэша = kesh(prompt_sistema, prompt_kontekst, cfg["model"])
    if из_кэша is not None:
        return из_кэша, {"iz_kesha": True, "tokeny_in": 0, "tokeny_out": 0,
                         "otsenka_rub": 0.0, "model": cfg["model"]}

    # Лимит проверяется до платного вызова (нулевая оценка — лишь барьер)
    if _расход_за_месяц() >= cfg["month_limit_rub"]:
        raise LLMError(
            f"месячный лимит LLM исчерпан («лимит»): "
            f"{_расход_за_месяц():.2f} руб. из {cfg['month_limit_rub']:.2f} руб.",
            klass="limit")

    последняя = None
    for попытка in range(_ПОВТОРОВ_СЕТЬ + 1):
        try:
            ответ = _post_chat(cfg, prompt_sistema, prompt_kontekst, shema_json)
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            последняя = e  # сетевая ошибка — единственный повтор (спека 2.1)
            continue
        except LLMError as e:
            if e.klass == "setevaya":  # 5xx — тот же единственный повтор
                последняя = e
                continue
            raise
    else:
        raise LLMError(f"LLM API недоступен после повтора: {последняя}",
                       klass="setevaya")

    try:
        содержимое = ответ["choices"][0]["message"]["content"]
        js = json.loads(содержимое)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise LLMError(f"ответ LLM не распарсился как JSON: {e}",
                       klass="kontrakt")
    usage = ответ.get("usage") or {}
    т_in = usage.get("prompt_tokens") or _оценка_токенов(
        prompt_sistema + prompt_kontekst)
    т_out = usage.get("completion_tokens") or _оценка_токенов(содержимое)
    оценка = uchyot_rashoda(т_in, т_out, cfg["model"], cfg)
    _записать_кэш(prompt_sistema, prompt_kontekst, cfg["model"], js)
    return js, {"iz_kesha": False, "tokeny_in": int(т_in),
                "tokeny_out": int(т_out), "otsenka_rub": оценка,
                "model": cfg["model"]}


def vyzov(prompt_sistema, prompt_kontekst, shema_json=None):
    """Вызов LLM → распарсенный JSON; при любой неудаче — LLMError."""
    js, _ = vyzov_s_meta(prompt_sistema, prompt_kontekst, shema_json)
    return js


# ---------------------------------------------------------------------------
# QC-контур: гейты 1–3 (спека 2.3), все детерминированные
# ---------------------------------------------------------------------------

# Обязательные ключи контракта ответа (спека 2.2)
_КЛЮЧИ_КОНТРАКТА = {
    "problema_formulirovka": str,
    "vetki": list,
    "prichiny": list,
    "meropriyatiya_konkretika": list,
    "riski_zamechaniya": list,
}


def validirovat_otvet_llm(js, vhod):
    """QC-гейты 1–3. Возвращает (ok: bool, narusheniya: list[str]).

    Гейт 1 — схема JSON по контракту спеки 2.2; poterya_id только из
    справочника 15 признаков (otbor_potok); instrument_id только из
    библиотеки инструментов (галлюцинация id = fail).
    Гейт 2 — каждое мероприятие привязано к причине (prichina_id ∈
    prichiny.vetka_id), каждая причина — к ветке (vetka_id ∈ vetki.poterya_id).
    Привязка причины в Л4.1 — через её vetka_id (id причины = vetka_id,
    задокументировано; выделенный id появится в Л4.2 при реальном промпте).
    Гейт 3 — каждый шаг cep_5pochemu имеет опору: {"otvet": ..., "opora":
    "fakt_vhoda"} (с непустым полем opora_fakt — на какой факт входа опирается)
    ИЛИ {"opora": "nuzhen_fakt"} (evidence-классы сохраняются, спека 2.3).
    """
    нарушения = []

    # --- Гейт 1: схема и справочники -------------------------------------
    if not isinstance(js, dict):
        return False, ["ответ LLM — не JSON-объект верхнего уровня"]
    for ключ, тип in _КЛЮЧИ_КОНТРАКТА.items():
        if ключ not in js:
            нарушения.append(f"гейт 1: нет обязательного ключа «{ключ}»")
        elif not isinstance(js[ключ], тип):
            нарушения.append(f"гейт 1: «{ключ}» — не тип {тип.__name__}")
    if нарушения:
        return False, нарушения  # без схемы гейты 2–3 бессмысленны

    ветки = js["vetki"]
    причины = js["prichiny"]
    мероприятия = js["meropriyatiya_konkretika"]
    id_веток = set()
    for i, в in enumerate(ветки):
        if not isinstance(в, dict) or not isinstance(в.get("poterya_id"), str):
            нарушения.append(f"гейт 1: vetki[{i}] без строкового poterya_id")
            continue
        if в["poterya_id"] not in ПРИЗНАКИ_ID:
            нарушения.append(
                f"гейт 1: poterya_id «{в['poterya_id']}» — вне справочника "
                "15 признаков (галлюцинация id)")
        else:
            id_веток.add(в["poterya_id"])
    id_причин = set()
    for i, п in enumerate(причины):
        if not isinstance(п, dict):
            нарушения.append(f"гейт 1: prichiny[{i}] — не объект")
            continue
        vid = п.get("vetka_id")
        if not isinstance(vid, str):
            нарушения.append(f"гейт 1: prichiny[{i}] без строкового vetka_id")
        elif vid in id_веток:
            id_причин.add(vid)
        if not isinstance(п.get("cep_5pochemu"), list):
            нарушения.append(f"гейт 1: prichiny[{i}].cep_5pochemu — не список")
        if not isinstance(п.get("koren"), str):
            нарушения.append(f"гейт 1: prichiny[{i}] без строкового koren")
    for i, м in enumerate(мероприятия):
        if not isinstance(м, dict):
            нарушения.append(f"гейт 1: meropriyatiya_konkretika[{i}] — не объект")
            continue
        iid = м.get("instrument_id")
        if not isinstance(iid, str):
            нарушения.append(f"гейт 1: meropriyatiya_konkretika[{i}] без "
                             "строкового instrument_id")
        elif iid not in ИНСТРУМЕНТЫ_ID:
            нарушения.append(
                f"гейт 1: instrument_id «{iid}» — вне библиотеки инструментов "
                "(галлюцинация id)")

    # --- Гейт 2: привязки -------------------------------------------------
    for i, п in enumerate(причины):
        if isinstance(п, dict) and isinstance(п.get("vetka_id"), str) \
                and п["vetka_id"] not in id_веток:
            нарушения.append(
                f"гейт 2: prichiny[{i}].vetka_id «{п['vetka_id']}» не "
                "привязан ни к одной ветке")
    for i, м in enumerate(мероприятия):
        if not isinstance(м, dict):
            continue
        pid = м.get("prichina_id")
        if not isinstance(pid, str) or pid not in id_причин:
            нарушения.append(
                f"гейт 2: meropriyatiya_konkretika[{i}].prichina_id "
                f"«{pid}» не привязан ни к одной причине")

    # --- Гейт 3: опора шагов 5-почему -------------------------------------
    for i, п in enumerate(причины):
        if not isinstance(п, dict) or not isinstance(п.get("cep_5pochemu"), list):
            continue
        for j, шаг in enumerate(п["cep_5pochemu"]):
            if not isinstance(шаг, dict):
                нарушения.append(
                    f"гейт 3: prichiny[{i}].cep_5pochemu[{j}] без опоры — "
                    "шаг строкой не принимается (нужен объект с opora)")
                continue
            опора = шаг.get("opora")
            if опора == _ОПОРА_ФАКТ:
                if not (isinstance(шаг.get("opora_fakt"), str)
                        and шаг["opora_fakt"].strip()):
                    нарушения.append(
                        f"гейт 3: prichiny[{i}].cep_5pochemu[{j}] заявлена "
                        "опора на факт входа, но opora_fakt пуст")
            elif опора != _ОПОРА_НУЖЕН:
                нарушения.append(
                    f"гейт 3: prichiny[{i}].cep_5pochemu[{j}] без опоры на "
                    "факт входа и без пометки «нужен факт»")

    return (not нарушения), нарушения


# ---------------------------------------------------------------------------
# Промпт-заготовка (Л4.1: без реального прожаривания формулировок — Л4.2)
# ---------------------------------------------------------------------------

_СИСТЕМА_ШАПКА = """Ты — методолог ФЦК (Федеральный центр компетенций в сфере
производительности труда). Разбираешь узкое место производственного потока
по методике ФЦК: проблема по правилу «факт — где — сколько — последствие»,
дерево потерь по 15 признакам Прил. № 5, коренные причины через 5 почему,
мероприятия из библиотеки инструментов ФЦК.

Жёсткие запреты:
- Не считай цифры: ΔВПП, ΔПТ, ΔЭЭ, окупаемость и любые расчёты выполняют
  детерминированные калькуляторы, не ты. Числа в ответе — только цитаты
  фактов входа.
- Не выдумывай инструменты и признаки: poterya_id — только из приложенного
  справочника 15 признаков, instrument_id — только из приложенной библиотеки.
- Каждое мероприятие привязывай к причине (prichina_id), каждую причину —
  к ветке (vetka_id).
- Каждый шаг «5 почему» снабжай опорой: opora="fakt_vhoda" + opora_fakt
  (какой факт входа подтверждает шаг) ИЛИ opora="nuzhen_fakt".
- Ответ — строго один JSON-объект по схеме, без markdown-обёрток и пояснений.

Стиль: деловой русский язык методички ФЦК; без канцелярско-рекламных и
«ИИ-шных» оборотов («важно отметить», «в современном мире», «ключевой
аспект», «погрузимся», тире-наращивания и т. п.); короткие конкретные
формулировки под этот цех, не общие слова."""


def sobrat_prompty(vhod, kontekst_progony=None, korpus=None):
    """Возвращает (sistema, kontekst) для вызова LLM.

    sistema — роль «методолог ФЦК» + запреты + стиль + справочники id.
    kontekst — JSON: вход генератора + (Л4.2) прогоны проекта +
    (Л4.3) корпус разборов; сейчас оба параметра — None-заглушки."""
    справочники = {
        "spravochnik_priznakov_15": sorted(ПРИЗНАКИ_ID),
        "biblioteka_instrumentov_id": sorted(ИНСТРУМЕНТЫ_ID),
    }
    sistema = (_СИСТЕМА_ШАПКА + "\n\nСправочники допустимых id:\n"
               + json.dumps(справочники, ensure_ascii=False, indent=1))
    контекст_д = {
        "vhod": vhod,
        # Л4.2: прогоны проекта (УМ, поток, OEE, замер); Л4.3: корпус разборов
        "progony_proekta": kontekst_progony,
        "korpus_razborov": korpus,
        "skhema_otveta": {к: "…" for к in _КЛЮЧИ_КОНТРАКТА},
    }
    kontekst = json.dumps(контекст_д, ensure_ascii=False, indent=1)
    return sistema, kontekst


# ---------------------------------------------------------------------------
# Откат: глубокий режим с автоматическим возвратом на быстрый (спека 2.1, 3)
# ---------------------------------------------------------------------------

def _быстрый_откат(vhod, причина):
    """Детерминированный генератор + пометка отката (спека: «сервис не
    падает никогда»; пометка видна в прогоне)."""
    результат = _детерминированный.сгенерировать(vhod)
    результат["rezhim"] = "bystriy_otkat"
    результат["otkat_prichina"] = причина
    return результат


def glubokiy_ili_bystriy(vhod):
    """Обёртка режима «глубокий» (агентский слой):
      LLM недоступен (нет ключа) / лимит / сетевая ошибка / QC fail после
      одного повтора с перечнем нарушений → детерминированный
      сгенерировать() с пометкой rezhim="bystriy_otkat".
    При успехе: rezhim="glubokiy", otvet_llm (контракт спеки 2.2), qc-отчёт.
    Сшивка содержательного ответа LLM с шагами 5–6 (квантификация, план) —
    ломтик Л4.2; здесь — инфраструктура вызова и QC-гейты 1–3."""
    cfg = klient()
    if not cfg["dostupno"]:
        return _быстрый_откат(vhod, "LLM недоступен: LLM_API_KEY не задан")

    sistema, kontekst = sobrat_prompty(vhod)
    try:
        js, meta = vyzov_s_meta(sistema, kontekst)
    except LLMError as e:
        return _быстрый_откат(vhod, f"LLM-вызов не удался ({e.klass}): {e}")

    ok, нарушения = validirovat_otvet_llm(js, vhod)
    if not ok:
        # Один повтор с перечнем нарушений (спека 2, шаг 3)
        try:
            js2, meta2 = vyzov_s_meta(
                sistema,
                kontekst + "\n\nПредыдущий ответ отклонён QC-контуром. "
                "Нарушения, исправь их:\n- " + "\n- ".join(нарушения))
        except LLMError as e:
            return _быстрый_откат(vhod,
                                  f"повторный LLM-вызов не удался "
                                  f"({e.klass}): {e}")
        ok2, нарушения2 = validirovat_otvet_llm(js2, vhod)
        if not ok2:
            return _быстрый_откат(
                vhod, "QC fail после повтора: " + "; ".join(нарушения2))
        js, meta, нарушения = js2, meta2, []

    return {
        "rezhim": "glubokiy",
        "otvet_llm": js,
        "qc": {"ok": True, "narusheniya": [],
               "primechanie": "гейты 1–3 спеки 2.3; гейты 4–5 — ломтик Л4.2"},
        "llm_meta": meta,
    }
