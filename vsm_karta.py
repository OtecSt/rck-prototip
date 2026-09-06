#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vsm_karta.py — ядро генератора КПСЦ (карта потока создания ценности) для «Агент-цеха».

Вход : JSON по Спеке № 1 «Узкие места» (поля: поток, операции[имя, тц_мин, впп_сек,
       производительность_т_ч, возврат_пкт, запас_перед_шт], впп_итого_сек, персонал_итого).
       Опционально: "главное_узкое_место": "имя операции" (результат узкие_места.py)
       или параметр CLI --glavnoe.
Выход: SVG-схема (классическая нотация «Learning to See»): процесс-боксы с data-box,
       треугольники запасов, инфопоток сверху, зубчатая линия времени VA/NVA внизу.

CLI:
    python3 vsm_karta.py данные.json                      # → <имя>_кпсц.svg рядом
    python3 vsm_karta.py данные.json -o карта.svg
    python3 vsm_karta.py данные.json --html превью.html
    python3 vsm_karta.py данные.json --glavnoe "Процесс фасовки..."

Зависимости: только stdlib. Идемпотентность: SVG зависит только от входа и даты.

v02 (визуальная ревизия): шапка без наложений (статус — отдельной строкой слева),
все подписи ≥ 10.5 px в масштабе 100 %, viewBox + max-width:100 % (масштаб под
контейнер без горизонтального скролла), перенос длинных строк легенды/итогов,
«время →» и все координаты строго внутри viewBox.
"""
import argparse
import datetime
import json
import sys
import xml.sax.saxutils as sax
from pathlib import Path

# ---------- Палитра (тёплая, низконасыщенная; согласована с UI) ----------
CREAM = "#faf7f2"
TERRA = "#a4572f"      # терракота — акценты, узкое место
TERRA_SOFT = "#c98a63"
INK = "#333333"        # тело
MUTED = "#8a7f74"      # приглушённые подписи
LINE = "#b9ada0"       # линии, стрелки
BOX_FILL = "#fffdf9"
DATA_FILL = "#f3ede4"
TRI_FILL = "#f0e3d2"
VA_FILL = "#a4572f"
NVA_FILL = "#d8c9b8"
WARN = "#8a4b2a"

FONT_SERIF = "Georgia, 'Times New Roman', serif"
FONT_SANS = "'Helvetica Neue', Arial, sans-serif"

# ---------- Геометрия layout ----------
M = 48                 # внешнее поле
BOX_W = 200            # ширина процесс-бокса
NAME_LINE_H = 15       # высота строки имени
NAME_MAX_LINES = 3
NAME_AREA = 14 + NAME_MAX_LINES * NAME_LINE_H   # область имени (59)
DATABOX_ROW_H = 16
DATABOX_MAX_ROWS = 5
DATABOX_H = 8 + DATABOX_MAX_ROWS * DATABOX_ROW_H  # 88
GAP = 72               # зазор между боксами (стрелка + треугольник запасов)
HDR_TITLE_Y = 34
HDR_LINE2_Y = 56       # «Дата: … · операций: n» + «ВПП итого» справа
HDR_LINE3_Y = 74       # «Главное узкое место: …»
HDR_STATUS_Y = 94      # «СТАТУС: …» отдельной строкой (без наложений)
INFO_Y = 122           # полоса инфопотока
PROC_Y = 202           # верх процесс-боксов
TRI_R = 14             # «радиус» треугольника запасов
TL_GAP = 56            # расстояние от data-box до линии времени
TL_STEP = 22           # высота зубца линии времени
FOOTER_GAP = 44        # от линии времени до легенды
FOOTER_LINE_H = 17     # шаг строк легенды/итогов
FOOTER_PAD = 26        # нижнее поле после последней строки

MAX_CHARS = 30         # перенос имён операций
CHAR_RATIO = 0.56      # честный запас ширины символа (доля от кегля; кириллица шире)


def esc(t):
    return sax.escape(str(t))


def fmt(x, nd=1):
    """Вывод с 1 знаком после запятой (как в отчётах ядра), целые — без хвоста."""
    if x is None:
        return None
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.{nd}f}"


def wrap_name(name, max_chars=MAX_CHARS, max_lines=NAME_MAX_LINES):
    """Перенос длинного имени по словам: ≤ max_chars в строке, ≤ max_lines строк."""
    words = str(name).split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            # слово длиннее строки — режем по символам
            while len(w) > max_chars:
                lines.append(w[:max_chars])
                w = w[max_chars:]
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = (last[:max_chars - 1] + "…") if len(last) >= max_chars else last + "…"
    return lines


def fit_chars(text, max_chars):
    """Одна строка с обрезкой по ширине и многоточием (для плотных мест)."""
    text = str(text)
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def wrap_text(text, max_chars):
    """Перенос длинной подписи по словам без потери содержимого."""
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            while len(w) > max_chars:
                lines.append(w[:max_chars])
                w = w[max_chars:]
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


class Svg:
    """Минимальный сборщик SVG-строк."""

    def __init__(self):
        self.parts = []

    def rect(self, x, y, w, h, fill, stroke=LINE, sw=1, rx=0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        r = f' rx="{rx}"' if rx else ""
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"'
            f' fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{r}{d}/>')

    def line(self, x1, y1, x2, y2, stroke=LINE, sw=1, dash=None, marker=True):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        m = ' marker-end="url(#arrow)"' if marker else ""
        self.parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"'
            f' stroke="{stroke}" stroke-width="{sw}"{d}{m}/>')

    def poly(self, pts, fill, stroke=LINE, sw=1):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.parts.append(
            f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=11, fill=INK, family=FONT_SERIF,
             anchor="start", weight="normal", style="normal"):
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}"'
            f' fill="{fill}" text-anchor="{anchor}" font-weight="{weight}"'
            f' font-style="{style}">{esc(s)}</text>')

    def render(self, w, h):
        defs = (
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"'
            ' markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{LINE}"/></marker>'
            '<marker id="arrowT" viewBox="0 0 10 10" refX="9" refY="5"'
            ' markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{TERRA}"/></marker>'
            '</defs>')
        # width/height — нативный размер (100 %), viewBox — масштабирование,
        # max-width:100% + height:auto — inline-режим без горизонтального скролла.
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"'
            f' viewBox="0 0 {w} {h}"'
            ' style="max-width:100%;height:auto;display:block"'
            f' font-family="{FONT_SERIF}">'
            f'<rect width="{w}" height="{h}" fill="{CREAM}"/>'
            + defs + "".join(self.parts) + "</svg>")


def databox_rows(op):
    """Строки data-box из того, что есть во входе (честный пропуск отсутствующего)."""
    rows = []
    if op.get("тц_мин") is not None:
        sec = op["тц_мин"] * 60
        rows.append(f"Тц: {fmt(sec)} сек")
    if op.get("впп_сек") is not None:
        rows.append(f"ВПП: {fmt(op['впп_сек'])} сек")
    if op.get("производительность_т_ч") is not None:
        rows.append(f"Пр: {fmt(op['производительность_т_ч'])} т/ч")
    if op.get("возврат_пкт") is not None:
        rows.append(f"Возврат: {fmt(op['возврат_пкт'], 0)} %")
    if op.get("персонал") is not None:
        rows.append(f"Персонал: {op['персонал']} чел.")
    if not rows:
        rows.append("нет замеров")
    return rows[:DATABOX_MAX_ROWS]


def строить_svg(d, glavnoe=None, today=None):
    today = today or datetime.date.today().isoformat()
    ops = d.get("операции") or []
    if not ops:
        raise ValueError("во входе нет операций — карту строить не из чего")
    for i, o in enumerate(ops):
        if not o.get("имя"):
            raise ValueError(f"операция № {i + 1}: нет имени (отказ по спеке)")
        if o.get("тц_мин") is not None and o["тц_мин"] <= 0:
            raise ValueError(f"операция «{o['имя']}»: Тц ≤ 0 (отказ по спеке)")

    glavnoe = glavnoe or d.get("главное_узкое_место")
    potok = d.get("поток", "поток без названия")

    # пробелы в данных → статус
    probely = []
    if not any(o.get("запас_перед_шт") for o in ops):
        probely.append("запасы перед операциями")
    if not all(o.get("впп_сек") for o in ops):
        probely.append("ВПП не по всем операциям")
    if not d.get("спрос_шт_в_период") or not d.get("доступное_время_мин"):
        probely.append("спрос/время → такт не вычисляется")
    status = ("С ПРОБЕЛАМИ: " + "; ".join(probely)) if probely else "ПОЛНЫЕ ДАННЫЕ"

    n = len(ops)
    w = M * 2 + n * BOX_W + (n - 1) * GAP
    proc_bottom = PROC_Y + NAME_AREA + DATABOX_H
    tl_y = proc_bottom + TL_GAP            # линия времени (нижний уровень VA)
    text_w = w - 2 * M                     # рабочая ширина для подписей

    s = Svg()
    cx = [M + i * (BOX_W + GAP) for i in range(n)]  # левые X боксов

    # ---------- Шапка (строки не пересекаются: у каждой свой y) ----------
    s.text(M, HDR_TITLE_Y, fit_chars(f"Карта потока создания ценности (КПСЦ) · {potok}",
                                     int(text_w / (17 * CHAR_RATIO))),
           size=17, weight="bold")
    s.text(M, HDR_LINE2_Y, f"Дата: {today} · операций: {n}", size=11, fill=MUTED,
           family=FONT_SANS)
    if d.get("впп_итого_сек"):
        s.text(w - M, HDR_LINE2_Y, f"ВПП итого (вход): {fmt(d['впп_итого_сек'])} сек",
               size=11, fill=MUTED, anchor="end", family=FONT_SANS)
    if glavnoe:
        s.text(M, HDR_LINE3_Y,
               fit_chars(f"Главное узкое место: «{glavnoe}»",
                         int(text_w / (11.5 * CHAR_RATIO))),
               size=11.5, fill=TERRA, weight="bold")
    s.text(M, HDR_STATUS_Y, fit_chars(f"СТАТУС: {status}",
                                      int(text_w / (11 * CHAR_RATIO))),
           size=11, fill=(WARN if probely else "#5a7250"),
           weight="bold", family=FONT_SANS)

    # ---------- Инфопоток (классика: поставщик → планирование → клиент) ----------
    info_boxes = [("ПОСТАВЩИК", M), ("ПЛАНИРОВАНИЕ", w / 2 - 55), ("КЛИЕНТ", w - M - 110)]
    for label, bx in info_boxes:
        s.rect(bx, INFO_Y, 110, 30, BOX_FILL, stroke=LINE)
        s.text(bx + 55, INFO_Y + 19, label, size=10.5, anchor="middle",
               family=FONT_SANS, weight="bold", fill=MUTED)
    s.line(M + 110, INFO_Y + 15, w / 2 - 55, INFO_Y + 15)
    s.line(w / 2 + 55, INFO_Y + 15, w - M - 110, INFO_Y + 15)
    # пунктир «программа на период» от планирования к первому боксу
    s.line(w / 2, INFO_Y + 30, cx[0] + BOX_W / 2, PROC_Y - 6,
           stroke=LINE, dash="4 3")
    s.text(M, INFO_Y + 46, "инфопоток: программа производства (пунктир — к потоку)",
           size=10.5, fill=MUTED, family=FONT_SANS, style="italic")

    # ---------- Поток материала: стрелки + треугольники запасов ----------
    for i in range(n - 1):
        x1 = cx[i] + BOX_W
        x2 = cx[i + 1]
        ym = PROC_Y + NAME_AREA / 2 + 6
        s.line(x1 + 4, ym, x2 - 4, ym, sw=1.6)  # push-стрелка
        z = ops[i + 1].get("запас_перед_шт")
        if z:  # треугольник запаса только при честных данных
            tx = (x1 + x2) / 2
            s.poly([(tx - TRI_R, ym + TRI_R + 4), (tx + TRI_R, ym + TRI_R + 4),
                    (tx, ym - TRI_R + 4)], TRI_FILL, stroke=WARN)
            s.text(tx, ym + TRI_R + 2, "I", size=10.5, anchor="middle",
                   weight="bold", fill=WARN)
            s.text(tx, ym + TRI_R + 19, f"{fmt(z, 0)} шт", size=10.5,
                   anchor="middle", fill=INK, family=FONT_SANS)

    # ---------- Процесс-боксы + data-box ----------
    for i, op in enumerate(ops):
        x = cx[i]
        is_g = glavnoe and op["имя"] == glavnoe
        stroke = TERRA if is_g else LINE
        sw = 3 if is_g else 1.2
        # имя (перенос по словам)
        s.rect(x, PROC_Y, BOX_W, NAME_AREA, BOX_FILL, stroke=stroke, sw=sw)
        lines = wrap_name(op["имя"])
        ty = PROC_Y + 18
        for ln in lines:
            s.text(x + BOX_W / 2, ty, ln, size=11.5, anchor="middle")
            ty += NAME_LINE_H
        if is_g:
            s.text(x + BOX_W / 2, PROC_Y - 8, "★ УЗКОЕ МЕСТО", size=11.5,
                   anchor="middle", fill=TERRA, weight="bold")
        # data-box
        dy = PROC_Y + NAME_AREA
        s.rect(x, dy, BOX_W, DATABOX_H, DATA_FILL, stroke=stroke, sw=sw)
        rows = databox_rows(op)
        ry = dy + 20
        for row in rows:
            s.text(x + 10, ry, fit_chars(row, int((BOX_W - 20) / (11 * CHAR_RATIO))),
                   size=11, family=FONT_SANS)
            ry += DATABOX_ROW_H
        # подпись возврата-петли
        if op.get("возврат_пкт"):
            s.text(x + BOX_W - 6, dy - 6, "↺ брак", size=10.5, anchor="end",
                   fill=TERRA, family=FONT_SANS)

    # ---------- Линия времени (зубцы VA / NVA) ----------
    # VA_i = Тц_i (сек); NVA_i = ВПП_i − Тц_i (ожидание внутри блока), если ВПП есть
    va, nva = [], []
    for op in ops:
        t = (op.get("тц_мин") or 0) * 60
        v = op.get("впп_сек")
        va.append(t)
        nva.append((v - t) if (v is not None and v >= t) else None)
    sum_va = sum(va)
    known_nva = [x for x in nva if x is not None]
    sum_nva = sum(known_nva)
    vpp_total = d.get("впп_итого_сек") or (sum_va + sum_nva if known_nva else None)
    va_pct = (sum_va / vpp_total * 100) if vpp_total else None

    # подпись «время →» — внутри viewBox, над левым концом линии
    s.text(M, tl_y - TL_STEP - 8, "время →", size=10.5, fill=MUTED,
           family=FONT_SANS)
    x = M
    for i in range(n):
        seg = BOX_W + (GAP if i < n - 1 else 0)
        # нижний (VA) горизонталь
        s.line(x, tl_y, x + BOX_W, tl_y, marker=False, stroke=VA_FILL, sw=2.6)
        s.text(x + BOX_W / 2, tl_y + 17, f"{fmt(va[i])}", size=11,
               anchor="middle", fill=VA_FILL, family=FONT_SANS, weight="bold")
        if i < n - 1:
            # зубец вверх: NVA между боксами
            s.line(x + BOX_W, tl_y, x + BOX_W, tl_y - TL_STEP,
                   marker=False, stroke=NVA_FILL, sw=1.8)
            s.line(x + BOX_W, tl_y - TL_STEP, x + seg, tl_y - TL_STEP,
                   marker=False, stroke=NVA_FILL, sw=2.6)
            if nva[i + 1] is not None:
                s.text(x + BOX_W + GAP / 2, tl_y - TL_STEP - 6,
                       f"{fmt(nva[i + 1])}", size=10.5, anchor="middle",
                       fill=MUTED, family=FONT_SANS)
            else:
                s.text(x + BOX_W + GAP / 2, tl_y - TL_STEP - 6, "?",
                       size=10.5, anchor="middle", fill=MUTED, family=FONT_SANS)
            s.line(x + seg, tl_y - TL_STEP, x + seg, tl_y,
                   marker=False, stroke=NVA_FILL, sw=1.8)
        x += seg
    # стрелка на правом конце линии (внутри viewBox: w - M + 16 < w)
    s.line(x, tl_y, x + 16, tl_y, marker=True, stroke=INK, sw=1.6)

    # ---------- Легенда / итоги (с переносом длинных строк) ----------
    ly = tl_y + FOOTER_GAP
    footer = []  # (текст, size, fill, weight, style)

    footer.append(("Линия времени: нижние отрезки (терракота) — VA = ΣТц; "
                   "верхние (беж) — NVA = ВПП − Тц по блоку (ожидание).",
                   10.5, MUTED, "normal", "normal"))
    itog = f"ΣVA (ΣТц) = {fmt(sum_va)} сек"
    if known_nva:
        itog += f" · ΣNVA = {fmt(sum_nva)} сек"
    if vpp_total:
        itog += f" · ВПП = {fmt(vpp_total)} сек"
    if va_pct is not None:
        itog += (f" · Доля ценности = ΣТц / ВПП = {fmt(sum_va)} / "
                 f"{fmt(vpp_total)} = {va_pct:.1f} %")
    footer.append((itog, 11.5, INK, "bold", "normal"))
    footer.append(("Data-box: Тц — время цикла; ВПП — время протекания блока; "
                   "Пр — производительность; Возврат — доля переделки. "
                   "Треугольник I — запас перед операцией (только при данных).",
                   10.5, MUTED, "normal", "normal"))
    footer.append(("Показано только то, что есть во входе; «?» — домерить. "
                   "Методика: «Learning to See» / МУ-66-2024 (Тц, ВПП, доля ценности).",
                   10.5, MUTED, "normal", "italic"))

    y = ly
    for txt, size, fill, weight, style in footer:
        max_chars = max(20, int(text_w / (size * CHAR_RATIO)))
        for ln in wrap_text(txt, max_chars):
            s.text(M, y, ln, size=size, fill=fill, family=FONT_SANS,
                   weight=weight, style=style)
            y += FOOTER_LINE_H
        y += 4  # интервал между абзацами

    h = y + FOOTER_PAD

    итоги = {
        "поток": potok,
        "дата": today,
        "операций": n,
        "сум_тц_сек": round(sum_va, 1),
        "сум_nva_сек": round(sum_nva, 1) if known_nva else None,
        "впп_сек": vpp_total,
        "доля_ценности_пкт": round(va_pct, 1) if va_pct is not None else None,
        "главное_узкое_место": glavnoe,
        "пробелы": probely,
    }
    return s.render(w, h), итоги


def main(argv=None):
    ap = argparse.ArgumentParser(description="Генератор КПСЦ (VSM) → SVG")
    ap.add_argument("вход", help="JSON по спеке № 1")
    ap.add_argument("-o", "--out", help="куда писать SVG (по умолчанию <вход>_кпсц.svg)")
    ap.add_argument("--html", help="дополнительно записать HTML-превью")
    ap.add_argument("--glavnoe", help="имя главного узкого места (подсветка)")
    args = ap.parse_args(argv)

    inp = Path(args.вход)
    d = json.loads(inp.read_text(encoding="utf-8"))
    svg, итоги = строить_svg(d, glavnoe=args.glavnoe)

    out = Path(args.out) if args.out else inp.with_name(inp.stem + "_кпсц.svg")
    out.write_text(svg, encoding="utf-8")
    if args.html:
        html = (f"<!doctype html><html lang=ru><head><meta charset=utf-8>"
                f"<title>КПСЦ · {esc(итоги['поток'])}</title>"
                f"<style>body{{margin:0;background:{CREAM};padding:24px;"
                f"font-family:{FONT_SANS}}}svg{{max-width:100%;height:auto}}</style>"
                f"</head><body>{svg}</body></html>")
        Path(args.html).write_text(html, encoding="utf-8")
    print(json.dumps(итоги, ensure_ascii=False, indent=1))
    print(f"SVG: {out}")
    if args.html:
        print(f"HTML: {args.html}")


if __name__ == "__main__":
    main()
