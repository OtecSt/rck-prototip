#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Регрессионный тест Ломтика 1 генератора мероприятий (Спека № 3, раздел 5).
Эталонный вход: ОКЗ — УМ «фасовка», 38,7 % ВПП, разрыв 23,7 п.п. до нормы
15 %, типовые параметры (признаки потерь обхода, один замер простоев).

Проверки: дерево непустое; ≥ 3 мероприятий; каждое привязано к причине;
у каждого kurs_fck РЕАЛЬНО есть в каталог_сырой.txt; qc pass или
осмысленные замечания. Результат прогона — JSON в
ИИ-направление/результаты/meropriyatiya_l1_этоталон_okz.json.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from meropriyatiya import сгенерировать, proverit_qc
from biblioteka_instrumentov import proverit_kursy

КАТАЛОГ = (Path(__file__).resolve().parent.parent
           / "конспекты_курсов" / "каталог_сырой.txt")
РЕЗУЛЬТАТ = (Path(__file__).resolve().parent.parent / "результаты"
             / "meropriyatiya_l1_этоталон_okz.json")

ЭТАЛОН_ОКЗ = {
    "predpriyatie": "ОКЗ",
    "uchastok": "фасовка",
    "vpp_pct": 38.7,
    "norma_vpp_pct": 15.0,
    "razryv": {"value": 23.7, "unit": "п.п. ВПП", "evidence": "fact"},
    "priznaki": {
        "простои_оборудования": True,
        "организация_рабочих_мест": True,
        "простаивающие_сотрудники": True,
        "вариативность_операций": True,
        "пересечения_потоков": True,
        "избыточные_запасы": True,
    },
    "vidy_potery": [
        {"nazvanie": "Ожидание"},
        {"nazvanie": "Перемещения"},
    ],
    "zamery": {
        "простои_оборудования": {"value": 47, "unit": "мин/смену",
                                 "evidence": "fact"},
    },
}


def main():
    r = сгенерировать(ЭТАЛОН_ОКЗ)
    ошибки = []

    # 1. Дерево непустое
    if not r["vetki"]:
        ошибки.append("дерево веток пустое")

    # 2. ≥ 3 мероприятий
    if len(r["meropriyatiya"]) < 3:
        ошибки.append(f"мероприятий {len(r['meropriyatiya'])} < 3")

    # 3. Каждое мероприятие привязано к причине
    корни = {п["koren"] for п in r["prichiny"] if п.get("koren")}
    for м in r["meropriyatiya"]:
        if м["prichina"] not in корни:
            ошибки.append(f"мероприятие «{м['instrument']}» без привязки "
                          f"к причине")

    # 4. Каждый kurs_fck реально есть в каталоге
    #    (цифровая ветка вне каталога ФЦК — kurs_fck=None, Протокол № 43)
    каталог = КАТАЛОГ.read_text(encoding="utf-8")
    for м in r["meropriyatiya"]:
        if м["kurs_fck"] is None:
            continue
        if м["kurs_fck"] not in каталог:
            ошибки.append(f"курс «{м['kurs_fck']}» отсутствует в каталоге")

    # 5. QC: pass или осмысленные замечания (фиксируем, но не валим тест,
    #    если замечания только о gap-замерах)
    qc = r["qc"]
    блокирующие = [н for н in qc if "замер" not in н and "gap" not in н]
    if блокирующие:
        ошибки.extend("qc: " + н for н in блокирующие)

    # Сохраняем эталонный прогон
    РЕЗУЛЬТАТ.parent.mkdir(parents=True, exist_ok=True)
    РЕЗУЛЬТАТ.write_text(json.dumps(r, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    print(f"Веток дерева:      {len(r['vetki'])}")
    print(f"Причин в карте:    {len(r['prichiny'])}")
    print(f"Мероприятий:       {len(r['meropriyatiya'])}")
    print(f"QC-замечаний:      {len(qc)}")
    for н in qc:
        print("  qc: " + н)
    print(f"Сверка библиотеки с каталогом: "
          f"{'OK' if not proverit_kursy() else 'НАРУШЕНИЯ'}")
    print(f"Результат сохранён: {РЕЗУЛЬТАТ}")

    if ошибки:
        print("\nТЕСТ ПРОВАЛЕН:")
        for о in ошибки:
            print(" - " + о)
        return 1
    print("\nТЕСТ ПРОЙДЕН")
    return 0


if __name__ == "__main__":
    sys.exit(main())
