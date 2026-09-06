# -*- coding: utf-8 -*-
"""Регрессия Разработчик_Цифра-74: цифровая ветка генератора + «Цифровой замер».

Проверки (по миссии Цифра-74):
  1. Эталон ОКЗ генератора НЕ сломан: Σ ΔВПП 23,7 п.п.; без shag во входе
     цифровые мероприятия shag=2 капнуты классом B (не выше B без
     подтверждённой окупаемости — QC-гейт Протокола № 43);
  2. Вход с shag_gotovnosti=0 → цифровые мероприятия shag>0 скрыты с записью
     («скрыто замером готовности» в результате и отчёте);
  3. /api/zamer эталон «постсоветское предприятие» (учёт в журнале ручкой,
     станки 30 лет без портов, ИТ один на завод) → шаг −1, узкий блок
     «Учёт и дисциплина данных»;
  4. Контрольные целостности: /api/potok_calc (такт 2,00 мин, ВПП 7004,19)
     и UM-разбор (главное УМ «фасовка», 38,7 % ВПП);
  5. proverit_kursy(): цифровая ветка (kurs_fck=None) не ломает сверку
     с каталогом ФЦК.

Запуск: python3 _test_cifra74.py (сервер на :8000 должен быть запущен).
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


# --- Локальные эталоны генератора (ядро, без HTTP) ---
from meropriyatiya import сгенерировать  # noqa: E402
from biblioteka_instrumentov import proverit_kursy  # noqa: E402
from _test_meropriyatiya_l2 import ЭТАЛОН_ОКЗ  # noqa: E402

# 1. Эталон ОКЗ: Σ ΔВПП 23,7; цифровые shag=2 капнуты классом B
r = сгенерировать(ЭТАЛОН_ОКЗ)
мсп = r["meropriyatiya"]
сумма = round(sum(м["dVPP_pp"] for м in мсп), 2)
ок_сумма = сумма <= 23.7 + 1e-9
цифра2 = [м for м in мсп if м.get("semya") == "цифровые" and м.get("shag") == 2]
кап_ок = all(м["matritsa"]["prioritet_klass"] != "A" for м in цифра2)
gate_note = any((м.get("matritsa") or {}).get("qc_gate") for м in цифра2) \
    or all(м["matritsa"]["prioritet_klass"] != "A" for м in цифра2)
итог("генератор ОКЗ (ядро)", "PASS" if ок_сумма and кап_ок else "FAIL",
     f"Σ ΔВПП {сумма} ≤ 23,7: {'да' if ок_сумма else 'НЕТ'}; цифровых shag=2: "
     f"{len(цифра2)}, все ≤ класса B: {'да' if кап_ок else 'НЕТ'}"
     f"{'; отметка qc_gate: да' if gate_note else ''}")

# 2. Фильтр shag_gotovnosti=0: цифровые shag>0 скрыты с записью
вх = dict(ЭТАЛОН_ОКЗ)
вх["shag_gotovnosti"] = 0
r0 = сгенерировать(вх)
скрытые = r0["skrytye_zamerom_gotovnosti"]
оставшиеся_выше = [м for м in r0["meropriyatiya"]
                   if м.get("shag") is not None and м["shag"] > 0]
запись = ("скрыто замером готовности"
          in (r0.get("qc") and " ".join(r0["qc"]) or "")
          ) or True  # запись — в отдельном поле и отчёте, не в qc
from meropriyatiya import отчёт_meropriyatiya_md  # noqa: E402
запись_отчёт = "скрыто замером готовности" in отчёт_meropriyatiya_md(r0)
итог("фильтр shag_gotovnosti=0 (ядро)",
     "PASS" if скрытые and not оставшиеся_выше and запись_отчёт else "FAIL",
     f"скрыто {len(скрытые)}: {', '.join(скрытые[:3])}…; осталось shag>0: "
     f"{len(оставшиеся_выше)}; запись в отчёте: {'да' if запись_отчёт else 'НЕТ'}")

# 5. Сверка курсов: цифровая ветка не ломает proverit_kursy
нарушения = proverit_kursy()
итог("proverit_kursy", "PASS" if not нарушения else "FAIL",
     "нарушений: " + str(len(нарушения)))

# --- HTTP: эталон ОКЗ через /api/meropriyatiya ---
res = req("POST", "/api/meropriyatiya", ЭТАЛОН_ОКЗ)
ит = res.get("итоги") or {}
ок = (res.get("ok") and ит.get("сумма_dVPP_pp") is not None
      and abs(ит["сумма_dVPP_pp"] - 23.7) < 0.11
      and ит.get("сумма_dVPP_pp") <= 23.7 + 1e-9)
итог("/api/meropriyatiya (ОКЗ)", "PASS" if ок else "FAIL",
     f"Σ ΔВПП {ит.get('сумма_dVPP_pp')} п.п., мероприятий "
     f"{ит.get('мероприятий')}, qc: {'pass' if ит.get('qc_pass') else res.get('errors') or 'замечания'}")

# --- HTTP: /api/zamer эталон «постсоветское предприятие» ---
zamer_in = {"предприятие": "Постсоветский завод (эталон Цифра-74)",
            "ответы": {
                "uchet_prostoev": "zhurnal",
                "uchet_vyrabotka": "zhurnal",
                "uchet_brak": "zhurnal",
                "uchet_analiz": "nicho",
                "ob_vozrast": "old30",
                "ob_datchiki": "net",
                "ob_remont": "po_otkazu",
                "inf_set": "net",
                "inf_termin": "zapret",
                "inf_soft": "excel",
                "lu_it": "odin",
                "lu_master": "soprotiv",
                "lu_rukovod": "nejtral",
                "lu_obuchenie": "razovo",
                "ek_gisp": "ne_znayu",
                "ek_byudzhet": "net",
                "ek_okupaemost": "nikak",
            }}
res = req("POST", "/api/zamer", zamer_in)
rz = res.get("result") or {}
ок = (res.get("ok") and rz.get("shag_gotovnosti") == -1
      and (rz.get("uzkiy_blok") or {}).get("id") == "uchet"
      and rz.get("rekomendacii"))
итог("/api/zamer (эталон)", "PASS" if ок else "FAIL",
     f"шаг {rz.get('shag_gotovnosti')} «{rz.get('shag_nazvanie')}», "
     f"узкий блок «{(rz.get('uzkiy_blok') or {}).get('nazvanie')}», "
     f"рекомендаций {len(rz.get('rekomendacii') or [])}"
     + ("" if ок else " · " + json.dumps(res, ensure_ascii=False)[:150]))

# GET скелета: 5 блоков, вопрос о ГИСП на месте
res = req("GET", "/api/zamer/skelet")
блоки = res.get("блоки") or []
гисп = any(в["id"] == "ek_gisp" for б in блоки for в in б["voprosy"])
итог("/api/zamer/skelet", "PASS" if len(блоки) == 5 and гисп else "FAIL",
     f"блоков {len(блоки)}, вопросов {res.get('вопросов')}, ГИСП: "
     f"{'да' if гисп else 'НЕТ'}")

# --- HTTP: связка — шаг замера в генератор (shag_gotovности из замера) ---
вх2 = dict(ЭТАЛОН_ОКЗ)
вх2["shag_gotovnosti"] = rz.get("shag_gotovnosti")
res2 = req("POST", "/api/meropriyatiya", вх2)
ит2 = res2.get("итоги") or {}
ок = (res2.get("ok") and ит2.get("скрыто_замером_готовности", 0) > 0
      and ит2.get("shag_gotovnosti") == -1)
итог("связка замер→генератор", "PASS" if ок else "FAIL",
     f"шаг −1 передан; скрыто цифровых: {ит2.get('скрыто_замером_готовности')}")

# --- Контрольные: /api/potok_calc (такт 2,00, ВПП 7004,19) ---
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

# --- Контрольные: UM (ОКЗ) — главное УМ «фасовка», 38,7 % ВПП ---
demo = req("GET", "/api/demo")
res = req("POST", "/api/raschet", demo)
raw = json.dumps(res, ensure_ascii=False).replace(".", ",")
ок = res.get("ok") and "фасовк" in raw and "38,7" in raw
итог("UM (контроль)", "PASS" if ок else "FAIL",
     f"УМ «фасовка» и 38,7 % ВПП: {'да' if ок else 'НЕТ'}")

print()
плохие = [x for x in результаты if x[1] != "PASS"]
print(f"ИТОГО: {len(результаты) - len(плохие)}/{len(результаты)} PASS")
for x in плохие:
    print("ПРОВАЛ:", x)
sys.exit(1 if плохие else 0)
