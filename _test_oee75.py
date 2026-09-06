# -*- coding: utf-8 -*-
"""Регрессия Разработчик_OEE-75: OEE-калькулятор + базовая связка с диагностикой.

Проверки (по миссии OEE-75):
  1. Эталон OEE: плановое 480 мин; простои аварии 47 / переналадка 38 /
     микроостановки 22; идеальное Тц 1,0 мин; выпуск 350 шт; брак 12 шт.
     Ожидания (посчитаны руками, дважды сверены):
       A = 373/480 = 0,777083  (77,71 %)
       P = 350/373 = 0,938338  (93,83 %)
       Q = 338/350 = 0,965714  (96,57 %)
       OEE = A·P·Q = 338/480 = 0,704167  (70,42 %)
     Потери: аварии 47 мин (9,79 %), переналадка 38 (7,92 %),
     микроостановки 22 (4,58 %), скорость 23 (4,79 %), брак 12 (2,50 %).
     Узкая составляющая — Доступность; топ-потеря — аварии;
     потенциал OEE′ = (420/480)·P·Q = 0,792895 (+8,87 п.п.);
     разрыв до мирового класса = 14,58 п.п.
  2. Контрольные НЕ сломаны: /api/potok_calc (такт 2,00, ВПП 7004,19),
     /api/meropriyatiya (Σ ΔВПП 23,7), /api/zamer (шаг −1 на эталоне);
  3. Ядро: валидация (выпуск не укладывается в оперативное время, мусор).

Запуск: python3 _test_oee75.py (сервер на :8000 должен быть запущен).
"""
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
AUTH = ("рцк", "H8BgJlzfjESRDv4F")
PROT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROT))

результаты = []


def итог(инструмент, статус, детали=""):
    результаты.append((инструмент, статус, детали))
    print(f"[{статус}] {инструмент} {детали}")


def req(method, path, body=None):
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("Authorization", "Basic " + base64.b64encode(
        f"{AUTH[0]}:{AUTH[1]}".encode()).decode())
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, data=data, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"ok": False, "errors": [f"HTTP {e.code}: {e.read()[:300]}"]}


# --- 1. Эталон OEE через /api/oee ---
ЭТАЛОН_OEE = {"поток": "Линия (эталон OEE-75)",
              "плановое_время_мин": 480,
              "простои": {"аварии_мин": 47, "переналадка_мин": 38,
                          "микроостановки_мин": 22},
              "идеальное_тц_мин": 1.0,
              "выпуск_всего_шт": 350,
              "брак_шт": 12}

ОЖ = {"A": 373 / 480, "P": 350 / 373, "Q": 338 / 350, "OEE": 338 / 480}

res = req("POST", "/api/oee", ЭТАЛОН_OEE)
ит = res.get("итоги") or {}
ок = (res.get("ok")
      and all(ит.get(k) is not None and abs(ит[k] - v) < 1e-4
              for k, v in ОЖ.items()))
итог("/api/oee (эталон A/P/Q/OEE)", "PASS" if ок else "FAIL",
     f"A {ит.get('A')} (эт. 0,777083), P {ит.get('P')} (эт. 0,938338), "
     f"Q {ит.get('Q')} (эт. 0,965714), OEE {ит.get('OEE')} (эт. 0,704167)"
     + ("" if ок else " · " + json.dumps(res, ensure_ascii=False)[:200]))

rz = res.get("результат") or {}
потери = {п["ключ"]: п for п in rz.get("потери", [])}
ож_потери = {"аварии": 47, "переналадка": 38, "микроостановки": 22,
             "скорость": 23, "брак": 12, "запуск": 0}
ок_п = (len(потери) == 6
        and all(k in потери and abs(потери[k]["мин"] - v) < 1e-9
                for k, v in ож_потери.items())
        and abs(потери["аварии"]["пкт_планового"] - 47 / 480 * 100) < 1e-6)
итог("/api/oee (шесть потерь)", "PASS" if ок_п else "FAIL",
     "; ".join(f"{потери[k]['название']} {потери[k]['мин']:g} мин "
               f"({потери[k]['пкт_планового']:.2f} %)" for k in ож_потери)
     if ок_п else json.dumps(rz.get("потери"), ensure_ascii=False)[:250])

уз = ит.get("узкая_составляющая")
потенц_ож = (420 / 480) * (350 / 373) * (338 / 350)  # 0,792895
ок_у = (уз == "Доступность (A)" and ит.get("топ_потеря") == "Аварии и поломки"
        and abs((ит.get("потенциал_oee") or 0) - потенц_ож) < 1e-4
        and abs((ит.get("разрыв_до_класса_пп") or 0) - (0.85 - 338 / 480) * 100) < 0.01)
итог("/api/oee (узкая + потенциал)", "PASS" if ок_у else "FAIL",
     f"узкая «{уз}», топ «{ит.get('топ_потеря')}», потенциал "
     f"{ит.get('потенциал_oee')} (эт. {потенц_ож:.6f}), разрыв "
     f"{ит.get('разрыв_до_класса_пп')} п.п. (эт. 14,58)")

# отчёт md содержит раскладку и источник
ок_мд = (res.get("ok") and "OEE = A × P × Q" in res.get("report_md", "")
         and "Анализ эффективности оборудования" in res.get("report_md", ""))
итог("/api/oee (отчёт md)", "PASS" if ок_мд else "FAIL",
     "раскладка A × P × Q и источник (МР «Анализ эффективности "
     "оборудования») в отчёте: " + ("да" if ок_мд else "НЕТ"))

# --- 1б. Ядро: валидация ---
import oee_kalkulator  # noqa: E402

плохой = dict(ЭТАЛОН_OEE)
плохой["выпуск_всего_шт"] = 500  # 500×1,0 > 373 мин оперативного времени
ош1 = oee_kalkulator.validirovat(плохой)
мусор = dict(ЭТАЛОН_OEE)
мусор["плановое_время_мин"] = "abc"
ош2 = oee_kalkulator.validirovat(мусор)
итог("ядро: валидация", "PASS" if ош1 and ош2 else "FAIL",
     f"выпуск > оперативного времени: «{ош1[0][:60] if ош1 else 'НЕ ПОЙМАНО'}…»; "
     f"мусор в плановом времени: {'поймано' if ош2 else 'НЕ ПОЙМАНО'}")

# --- 2. Контрольные НЕ сломаны ---
# /api/potok_calc (такт 2,00, ВПП 7004,19)
potok_in = {"поток": "Тестовый поток", "спрос_шт_в_период": 240,
            "доступное_время_мин": 480, "численность_чел": 5,
            "операции": [
                {"имя": "Оп1", "тц_мин": 1.25, "запас_после_шт": 2000},
                {"имя": "Оп2", "тц_мин": 1.5, "запас_после_шт": 700},
                {"имя": "Оп3", "тц_мин": 1.44, "запас_после_шт": 800}]}
res = req("POST", "/api/potok_calc", potok_in)
ит3 = res.get("итоги") or {}
такт_ок = ит3.get("такт_мин") == 2.0
впп_ок = ит3.get("впп_мин") is not None and abs(ит3["впп_мин"] - 7004.19) < 0.01
итог("/api/potok_calc (контроль)", "PASS" if такт_ок and впп_ок else "FAIL",
     f"такт {ит3.get('такт_мин')} мин (эталон 2,00), ВПП "
     f"{ит3.get('впп_мин')} мин (эталон 7004,19), УМ «{ит3.get('узкое_место')}»")

# /api/meropriyatiya (Σ ΔВПП 23,7)
from _test_meropriyatiya_l2 import ЭТАЛОН_ОКЗ  # noqa: E402

res = req("POST", "/api/meropriyatiya", ЭТАЛОН_ОКЗ)
ит4 = res.get("итоги") or {}
ок = (res.get("ok") and ит4.get("сумма_dVPP_pp") is not None
      and abs(ит4["сумма_dVPP_pp"] - 23.7) < 0.11
      and ит4["сумма_dVPP_pp"] <= 23.7 + 1e-9)
итог("/api/meropriyatiya (контроль)", "PASS" if ок else "FAIL",
     f"Σ ΔВПП {ит4.get('сумма_dVPP_pp')} п.п. (эталон 23,7), "
     f"мероприятий {ит4.get('мероприятий')}")

# /api/zamer (шаг −1 на эталоне)
zamer_in = {"предприятие": "Постсоветский завод (контроль OEE-75)",
            "ответы": {
                "uchet_prostoev": "zhurnal", "uchet_vyrabotka": "zhurnal",
                "uchet_brak": "zhurnal", "uchet_analiz": "nicho",
                "ob_vozrast": "old30", "ob_datchiki": "net",
                "ob_remont": "po_otkazu", "inf_set": "net",
                "inf_termin": "zapret", "inf_soft": "excel",
                "lu_it": "odin", "lu_master": "soprotiv",
                "lu_rukovod": "nejtral", "lu_obuchenie": "razovo",
                "ek_gisp": "ne_znayu", "ek_byudzhet": "net",
                "ek_okupaemost": "nikak"}}
res = req("POST", "/api/zamer", zamer_in)
rz2 = res.get("result") or {}
ок = (res.get("ok") and rz2.get("shag_gotovnosti") == -1)
итог("/api/zamer (контроль)", "PASS" if ок else "FAIL",
     f"шаг {rz2.get('shag_gotovnosti')} «{rz2.get('shag_nazvanie')}» "
     f"(эталон −1)")

# --- Итог ---
провалы = [x for x in результаты if x[1] != "PASS"]
print(f"\nИТОГ: {len(результаты) - len(провалы)}/{len(результаты)} PASS")
sys.exit(1 if провалы else 0)
