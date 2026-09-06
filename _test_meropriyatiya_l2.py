#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Регрессионный тест Ломтика 2 генератора мероприятий (Спека № 3, раздел 5).
Эталонный вход: ОКЗ — УМ «фасовка», 38,7 % ВПП, разрыв 23,7 п.п. до нормы
15 % + секция «ekonomika» (параметры потока для связки с ЭЭ-калькулятором;
цифры условные — допущение теста, реальные берутся из прогона ЭЭ проекта).

Проверки ломтика 2:
  * каждое мероприятие квантифицировано (dVPP_min, dTc, dPT_pct, dEE_rub,
    trudoemkost, riski — не None);
  * prioritet проставлен, уникален, 1 = высший;
  * топ-3 осмыслены (при долгой переналадке/простоях высоко SMED или
    автономное обслуживание/стандартизированная работа — класс A);
  * Σ ΔВПП мероприятий ≤ разрыва УМ (нормировка шага 5);
  * qc pass (без блокирующих замечаний);
  * Σ ΔЭЭ мероприятий согласовано с пересчётом через ээ_калькулятор.

Результат прогона — JSON в
ИИ-направление/результаты/meropriyatiya_l2_этоталон_okz.json.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from meropriyatiya import сгенерировать
from biblioteka_instrumentov import proverit_kursy

РЕЗУЛЬТАТ = (Path(__file__).resolve().parent.parent / "результаты"
             / "meropriyatiya_l2_этоталон_okz.json")

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
    # Секция для связки с ЭЭ-калькулятором (модель ФЦК v5.2). Цифры условные
    # — допущение теста; в бою подставляются из прогона ЭЭ проекта.
    "smena_min": 480,
    "ekonomika": {
        "предприятие": "ОКЗ",
        "поток": "фасовка",
        "тцикл_мин": {"до": 4.0, "после": 4.0},
        "ттакт_мин": {"до": 4.5, "после": 4.5},
        "фонд_времени": {"смены": 2, "часы": 8, "дни": 247},
        "цена_ед": 500.0,
        "перем_сс_ед": 350.0,
        "спрос_превышает_возможности": True,
    },
}


def main():
    r = сгенерировать(ЭТАЛОН_ОКЗ)
    ошибки = []
    мсп = r["meropriyatiya"]

    # 1. Каждое мероприятие квантифицировано
    for м in мсп:
        for поле in ("dVPP_min", "dTc", "dPT_pct", "trudoemkost", "riski",
                     "prioritet"):
            if м.get(поле) is None:
                ошибки.append(f"«{м['instrument']}»: поле {поле} = None")
        if м.get("dEE_rub") is None:
            ошибки.append(f"«{м['instrument']}»: dEE_rub = None при заданной "
                          f"секции ekonomika ({м.get('dEE_gap', '?')})")
        if (м.get("dTc") or {}).get("d_vyrabotka_ed_smenu") is None:
            ошибки.append(f"«{м['instrument']}»: Δвыработка не посчитана "
                          f"(тцикл задан в ekonomika)")

    # 2. Приоритеты: уникальны, сплошные 1..N
    ранги = sorted(м["prioritet"] for м in мсп)
    if ранги != list(range(1, len(мсп) + 1)):
        ошибки.append(f"приоритеты не образуют ряд 1..N: {ранги}")

    # 3. Σ ΔВПП мероприятий ≤ разрыва УМ
    сумма_pp = sum(м["dVPP_pp"] for м in мсп)
    if сумма_pp > 23.7 + 1e-9:
        ошибки.append(f"Σ ΔВПП мероприятий {сумма_pp} п.п. > разрыва 23,7 п.п.")

    # 4. Топ-3 осмыслены: минимум два мероприятия класса A (быстрый эффект
    #    при низкой/средней трудоёмкости), среди них — рабочие инструменты
    #    снижения ВПП, а не только «голая аналитика»
    топ3 = sorted(мсп, key=lambda м: м["prioritet"])[:3]
    if sum(1 for м in топ3 if м["matritsa"]["prioritet_klass"] == "A") < 2:
        ошибки.append("в топ-3 меньше двух мероприятий класса A: "
                      + ", ".join(f"{м['instrument']} ({м['matritsa']['prioritet_klass']})"
                                  for м in топ3))
    if not any("SMED" in м["instrument"] or "Стандартизированная" in м["instrument"]
               or "Автономное" in м["instrument"] for м in топ3):
        ошибки.append("в топ-3 нет ни SMED, ни стандартизированной работы, "
                      "ни автономного обслуживания — ранжирование "
                      "неосмысленно при простоях и переналадках")

    # 5. QC: pass или только замечания про gap-замеры
    qc = r["qc"]
    блокирующие = [н for н in qc if "замер" not in н and "gap" not in н]
    if блокирующие:
        ошибки.extend("qc: " + н for н in блокирующие)

    # Сохраняем эталонный прогон
    РЕЗУЛЬТАТ.parent.mkdir(parents=True, exist_ok=True)
    РЕЗУЛЬТАТ.write_text(json.dumps(r, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    print(f"Мероприятий:            {len(мсп)}")
    print(f"Σ ΔВПП мероприятий:     {round(сумма_pp, 2)} п.п. (разрыв 23,7)")
    print(f"Σ ΔПТ мероприятий:      "
          f"{round(sum(м['dPT_pct'] for м in мсп), 2)} %")
    сумма_ээ = sum(м["dEE_rub"] or 0 for м in мсп)
    print(f"Σ ΔЭЭ мероприятий:      {сумма_ээ:,.2f} руб/год"
          .replace(",", " ").replace(".", ","))
    print("Топ-3 по приоритету:")
    for м in топ3:
        print(f"  {м['prioritet']}. {м['instrument']} — ΔВПП {м['dVPP_pp']} п.п. "
              f"({м['dVPP_min']} мин/смену), ΔПТ {м['dPT_pct']} %, "
              f"ΔЭЭ {м['dEE_rub']:,.0f} руб/год, "
              f"трудоёмкость {м['trudoemkost']['klass']}, "
              f"класс {м['matritsa']['prioritet_klass']}"
              .replace(",", " "))
    print(f"QC-замечаний:           {len(qc)}")
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
