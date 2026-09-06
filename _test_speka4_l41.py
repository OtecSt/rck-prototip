#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессия Разработчик_Спека4-79: Ломтик Л4.1 — инфраструктура LLM-вызова
(Спека № 4, разделы 2.1–2.3).

Проверки (по миссии):
  1. Мок-ответ LLM (валидный JSON по контракту 2.2) → QC-гейты 1–3 pass.
  2. Мок с галлюцинацией id инструмента → QC fail с нарушением гейта 1.
  3. Без LLM_API_KEY → glubokiy_ili_bystriy() откатывается на
     детерминированный генератор с пометкой rezhim="bystriy_otkat".
  4. Кэш: два одинаковых вызова → второй из кэша (флаг iz_kesha, HTTP-вызов
     не повторялся).
  5. Лимит: месячный расход исчерпан → LLMError с пометкой «лимит».
  6. Контрольные НЕ сломаны (живой сервер :8000): /api/meropriyatiya
     (Σ ΔВПП 23,7), /api/oee (0,704167), /api/potok_calc (2,00 / 7004,19).

Реальных платных вызовов нет: HTTP-уровень (_post_chat) замокан.
Запуск: python3 _test_speka4_l41.py (сервер на :8000 должен быть запущен
— проверки п. 6; без сервера они отмечаются SKIP).
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

PROT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROT))

# Тестовая БД (кэш/расход) — во временном файле, ui/agent_ceh.db не трогаем
_TMP_DB = Path(tempfile.mkdtemp(prefix="llm_l41_")) / "test_llm.db"
os.environ["LLM_DB_PATH"] = str(_TMP_DB)

import llm_sloy  # noqa: E402
from _test_meropriyatiya_l2 import ЭТАЛОН_ОКЗ  # noqa: E402

результаты = []


def итог(проверка, статус, детали=""):
    результаты.append((проверка, статус, детали))
    print(f"[{статус}] {проверка} {детали}")


# ---------------------------------------------------------------------------
# Моки ответов LLM (контракт спеки 2.2)
# ---------------------------------------------------------------------------

def _валидный_ответ():
    return {
        "problema_formulirovka": ("Участок «фасовка»: ВПП 38,7 % сменного "
                                  "времени, разрыв 23,7 п.п. до нормы"),
        "vetki": [{"poterya_id": "простои_оборудования",
                   "obsuzhdenie": "простои подтверждены замером 47 мин/смену",
                   "zapros_dannyh": "структура простоев по видам"}],
        "prichiny": [{
            "vetka_id": "простои_оборудования",
            "cep_5pochemu": [
                {"otvet": "оборудование простаивает в течение смены",
                 "opora": "fakt_vhoda",
                 "opora_fakt": "zamery.простои_оборудования = 47 мин/смену"},
                {"otvet": "остановки уходят в переналадки и ремонты",
                 "opora": "nuzhen_fakt"},
            ],
            "koren": "нет системы автономного обслуживания и ППР",
            "nuzhny_fakty": ["график ППР участка"],
        }],
        "meropriyatiya_konkretika": [{
            "prichina_id": "простои_оборудования",
            "instrument_id": "Автономное обслуживание",
            "konkretika": "закрепить чистку и осмотр фасовочной линии за "
                          "оператором смены по чек-листу",
            "argument": "снимает микроостановки из-за загрязнения датчика",
        }],
        "riski_zamechaniya": ["сопротивление персонала — низкое"],
    }


_ВХОД_МИН = {
    "predpriyatie": "Тест",
    "uchastok": "фасовка",
    "vpp_pct": 38.7,
    "razryv": {"value": 23.7, "unit": "п.п. ВПП", "evidence": "fact"},
    "priznaki": {"простои_оборудования": True},
    "zamery": {"простои_оборудования": {"value": 47, "unit": "мин/смену"}},
}


class _МокСчётчик:
    """Счётчик HTTP-вызовов для проверки кэша."""

    def __init__(self, ответ):
        self.ответ = ответ
        self.вызовов = 0

    def __call__(self, cfg, sistema, kontekst, shema_json):
        self.вызовов += 1
        return {"choices": [{"message": {"content": json.dumps(
            self.ответ, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}}


_orig_post = llm_sloy._post_chat
_orig_env = {k: os.environ.get(k) for k in
             ("LLM_API_KEY", "LLM_MONTH_LIMIT_RUB")}


def _сброс_env():
    for k, v in _orig_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# --- 1. Мок валидный JSON → QC pass -----------------------------------------
ок, нарушения = llm_sloy.validirovat_otvet_llm(_валидный_ответ(), _ВХОД_МИН)
итог("QC: валидный мок-ответ → pass", "PASS" if ок and not нарушения else "FAIL",
     f"ok={ок}, нарушений={len(нарушения)}")

# --- 2. Мок с галлюцинацией id инструмента → QC fail -------------------------
битый = _валидный_ответ()
битый["meropriyatiya_konkretika"][0]["instrument_id"] = "Галлюцинатор 3000"
ок, нарушения = llm_sloy.validirovat_otvet_llm(битый, _ВХОД_МИН)
есть_гейт1 = any("галлюцинация id" in н and "инструмент" in н for н in нарушения)
итог("QC: галлюцинация instrument_id → fail (гейт 1)",
     "PASS" if not ок and есть_гейт1 else "FAIL",
     f"ok={ок}; {нарушения[0] if нарушения else '—'}")

# Дополнительно: галлюцинация poterya_id и шаг 5-почему без опоры
битый2 = _валидный_ответ()
битый2["vetki"][0]["poterya_id"] = "выдуманный_признак"
ок2, нар2 = llm_sloy.validirovat_otvet_llm(битый2, _ВХОД_МИН)
итог("QC: галлюцинация poterya_id → fail (гейт 1)",
     "PASS" if not ок2 and any("15 признаков" in н for н in нар2) else "FAIL",
     f"ok={ок2}")

битый3 = _валидный_ответ()
битый3["prichiny"][0]["cep_5pochemu"][0] = {"otvet": "просто мнение"}
ок3, нар3 = llm_sloy.validirovat_otvet_llm(битый3, _ВХОД_МИН)
итог("QC: шаг 5-почему без опоры → fail (гейт 3)",
     "PASS" if not ок3 and any("гейт 3" in н for н in нар3) else "FAIL",
     f"ok={ок3}")

# --- 3. Без ключа → откат на быстрый режим -----------------------------------
os.environ.pop("LLM_API_KEY", None)
cfg = llm_sloy.klient()
res = llm_sloy.glubokiy_ili_bystriy(ЭТАЛОН_ОКЗ)
ок = (not cfg["dostupno"] and res.get("rezhim") == "bystriy_otkat"
      and res.get("otkat_prichina") and res.get("plan"))
итог("Откат: без ключа → быстрый режим с пометкой",
     "PASS" if ок else "FAIL",
     f"dostupno={cfg['dostupno']}, rezhim={res.get('rezhim')}, "
     f"причина: {res.get('otkat_prichina', '')[:60]}")

# --- 4. Кэш: два одинаковых вызова → второй из кэша --------------------------
os.environ["LLM_API_KEY"] = "тестовый-мок-ключ"
os.environ.pop("LLM_MONTH_LIMIT_RUB", None)
мок = _МокСчётчик(_валидный_ответ())
llm_sloy._post_chat = мок
try:
    js1, meta1 = llm_sloy.vyzov_s_meta("система-кэш", "контекст-кэш")
    js2, meta2 = llm_sloy.vyzov_s_meta("система-кэш", "контекст-кэш")
finally:
    llm_sloy._post_chat = _orig_post
ок = (not meta1["iz_kesha"] and meta2["iz_kesha"] and мок.вызовов == 1
      and js1 == js2 and meta1["otsenka_rub"] > 0)
итог("Кэш: повторный вызов из кэша (бесплатно)", "PASS" if ок else "FAIL",
     f"1-й iz_kesha={meta1['iz_kesha']} ({meta1['otsenka_rub']} руб.), "
     f"2-й iz_kesha={meta2['iz_kesha']}, HTTP-вызовов={мок.вызовов}")

# --- 5. Лимит: исчерпан → LLMError «лимит» -----------------------------------
os.environ["LLM_MONTH_LIMIT_RUB"] = "0"  # любой расход уже сверх лимита
try:
    llm_sloy.vyzov_s_meta("система-лимит", "контекст-лимит")
    итог("Лимит: исчерпан → LLMError «лимит»", "FAIL", "вызов прошёл!")
except llm_sloy.LLMError as e:
    итог("Лимит: исчерпан → LLMError «лимит»",
         "PASS" if e.klass == "limit" and "лимит" in str(e) else "FAIL",
         f"klass={e.klass}: {str(e)[:70]}")
finally:
    os.environ.pop("LLM_MONTH_LIMIT_RUB", None)

# Дополнительно: uchyot_rashoda бросает «лимит» при превышении по факту
os.environ["LLM_MONTH_LIMIT_RUB"] = "0.0001"
try:
    llm_sloy.uchyot_rashoda(10000, 10000, "мок", llm_sloy.klient())
    итог("Лимит: uchyot_rashoda превышение → LLMError", "FAIL", "записалось!")
except llm_sloy.LLMError as e:
    итог("Лимит: uchyot_rashoda превышение → LLMError",
         "PASS" if e.klass == "limit" else "FAIL", f"klass={e.klass}")
finally:
    os.environ.pop("LLM_MONTH_LIMIT_RUB", None)

# --- 5б. Глубокий режим целиком на моке: QC fail → повтор → pass -------------
ответы = [битый, _валидный_ответ()]  # первый с галлюцинацией, второй чистый
мок2 = _МокСчётчик(None)
def _post_серия(cfg, sistema, kontekst, shema_json):
    мок2.вызовов += 1
    отв = ответы.pop(0)
    return {"choices": [{"message": {"content": json.dumps(
        отв, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10}}
llm_sloy._post_chat = _post_серия
try:
    res = llm_sloy.glubokiy_ili_bystriy(_ВХОД_МИН)
finally:
    llm_sloy._post_chat = _orig_post
ок = (res.get("rezhim") == "glubokiy" and res.get("qc", {}).get("ok")
      and мок2.вызовов == 2)
итог("Глубокий режим: QC fail → один повтор → pass",
     "PASS" if ок else "FAIL",
     f"rezhim={res.get('rezhim')}, вызовов={мок2.вызовов}"
     + ("" if ок else " · " + str(res.get("otkat_prichina", ""))[:80]))

_сброс_env()

# --- 6. Контрольные НЕ сломаны (живой сервер :8000) --------------------------
BASE = "http://localhost:8000"


def req(path, body):
    r = urllib.request.Request(BASE + path, method="POST",
                               data=json.dumps(body, ensure_ascii=False).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, data=r.data, timeout=60) as resp:
        return json.loads(resp.read().decode())


try:
    with urllib.request.urlopen(BASE + "/", timeout=5) as resp:
        сервер_жив = resp.status == 200
except Exception:
    сервер_жив = False

if not сервер_жив:
    итог("Контрольные API (:8000)", "SKIP", "сервер не запущен")
else:
    res = req("/api/meropriyatiya", ЭТАЛОН_ОКЗ)
    ит4 = res.get("итоги") or {}
    ок = (res.get("ok") and ит4.get("сумма_dVPP_pp") is not None
          and abs(ит4["сумма_dVPP_pp"] - 23.7) < 0.11
          and ит4["сумма_dVPP_pp"] <= 23.7 + 1e-9)
    итог("/api/meropriyatiya (контроль)", "PASS" if ок else "FAIL",
         f"Σ ΔВПП {ит4.get('сумма_dVPP_pp')} п.п. (эталон 23,7)")

    ЭТАЛОН_OEE = {"поток": "Линия (эталон OEE-75)", "плановое_время_мин": 480,
                  "простои": {"аварии_мин": 47, "переналадка_мин": 38,
                              "микроостановки_мин": 22},
                  "идеальное_тц_мин": 1.0, "выпуск_всего_шт": 350, "брак_шт": 12}
    res = req("/api/oee", ЭТАЛОН_OEE)
    ит5 = res.get("итоги") or {}
    ок = (res.get("ok") and ит5.get("OEE") is not None
          and abs(ит5["OEE"] - 0.704167) < 1e-4)
    итог("/api/oee (контроль)", "PASS" if ок else "FAIL",
         f"OEE {ит5.get('OEE')} (эталон 0,704167)")

    potok_in = {"поток": "Тестовый поток", "спрос_шт_в_период": 240,
                "доступное_время_мин": 480, "численность_чел": 5,
                "операции": [
                    {"имя": "Оп1", "тц_мин": 1.25, "запас_после_шт": 2000},
                    {"имя": "Оп2", "тц_мин": 1.5, "запас_после_шт": 700},
                    {"имя": "Оп3", "тц_мин": 1.44, "запас_после_шт": 800}]}
    res = req("/api/potok_calc", potok_in)
    ит6 = res.get("итоги") or {}
    ок = (res.get("ok") and ит6.get("такт_мин") == 2.0
          and ит6.get("впп_мин") is not None
          and abs(ит6["впп_мин"] - 7004.19) < 0.01)
    итог("/api/potok_calc (контроль)", "PASS" if ок else "FAIL",
         f"такт {ит6.get('такт_мин')} (эталон 2,00), ВПП "
         f"{ит6.get('впп_мин')} (эталон 7004,19)")

# --- Сводка ------------------------------------------------------------------
fails = [п for п, с, _ in результаты if с == "FAIL"]
print()
print(f"ИТОГ: {len(результаты) - len(fails)} ок / {len(fails)} FAIL"
      f" из {len(результаты)}")
if fails:
    print("Провалились: " + "; ".join(fails))
    sys.exit(1)
print("Все проверки пройдены.")
