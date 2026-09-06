# -*- coding: utf-8 -*-
"""_test_ekstraktor_pa.py — прогон экстрактора ПА по образцам и точечная сверка.

Эталон: ОЗМК «Свод ПА_ОЗМК Балка сварная.xlsx» (формат A, КПСЦ-транспонированный).
Сверка руками: 3–5 операций точечно против значений из дампа разведки.
Результаты: ИИ-направление/результаты/ekstraktor_pa_v01/*.json + sverka.md
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # Прототип/
WORK = ROOT.parent.parent                        # Методички/
OUT = WORK / "ИИ-направление" / "результаты" / "ekstraktor_pa_v01"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

import ekstraktor_pa  # noqa: E402

OBRAZCY = {
    "ozmk_etalon": WORK / "ИИ-направление" / "образцы_па" / "Свод ПА_ОЗМК Балка сварная.xlsx",
    "gayfa_pochasovoy": WORK / "ИИ-направление" / "образцы_па" / "Пример листа производственного анализа.xlsx",
    "vishnevskogo_hronometrazh": WORK / "ИИ-направление" / "образцы_па" / "Производственный анализ №1.xlsx",
    "fck_neraspoznano": WORK / "ИИ-направление" / "образцы_па" / "Производственный+анализ+на+28.09.2020+с+тех.заданием..xlsx",
}

# Контрольные значения из дампа разведки (разведка_па/dump_ozmk.txt, лист КПСЦ):
# r15 Тц, ч.: резка=2, сборка=0.3, сварка=2.5, правка=0.5, резка св.балки=0.4
# r19 НЗП: сборка=4, сварка=3; r20 Персонал: выдача=2, резка=4
SVERKA = [
    ("резка металла", "tc_min", 120.0),   # 2 ч → 120 мин
    ("сборка сварной балки", "tc_min", 18.0),   # 0.3 ч → 18 мин
    ("сварка балки автоматическая", "tc_min", 150.0),  # 2.5 ч → 150 мин
    ("сборка сварной балки", "zapas", 4.0),     # НЗП = 4
    ("выдача металл", "personal", 2.0),          # персонал = 2
]


def main():
    protokol = ["# Сверка ekstraktor_pa v01\n"]
    ok_vse = True
    for key, path in OBRAZCY.items():
        r = ekstraktor_pa.izvlech(path.read_bytes(), path.name)
        (OUT / f"{key}.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        protokol.append(f"\n## {key}: {path.name}\n")
        protokol.append(f"- формат: `{r['format']}`, лист: `{r.get('format_list')}`, "
                        f"ok={r['ok']}, операций: {len(r['operacii'])}, "
                        f"численность: {r['chislennost']}, такт: {r['takt_min']}")
        for w in r["preduprezhdeniya"]:
            protokol.append(f"  - ! {w}")

    # точечная сверка эталона
    etalon = json.loads((OUT / "ozmk_etalon.json").read_text(encoding="utf-8"))
    protokol.append("\n## Точечная сверка эталона (ОЗМК, формат A)\n")
    for fragment, pole, ozhidano in SVERKA:
        op = next((o for o in etalon["operacii"]
                   if fragment in o["nazvanie"].lower()), None)
        fact = op.get(pole) if op else None
        status = "OK" if (op and fact == ozhidano) else "НЕ СОШЛОСЬ"
        if status != "OK":
            ok_vse = False
        protokol.append(f"- [{status}] «{fragment}».{pole}: ожидалось {ozhidano}, "
                        f"получено {fact} (операция: {op['nazvanie'][:60] if op else '—'})")
    protokol.append(f"\n**Итог сверки: {'ВСЁ СОШЛОСЬ' if ok_vse else 'ЕСТЬ РАСХОЖДЕНИЯ'}**\n")
    (OUT / "sverka.md").write_text("\n".join(protokol), encoding="utf-8")
    print("\n".join(protokol))
    return 0 if ok_vse else 1


if __name__ == "__main__":
    sys.exit(main())
