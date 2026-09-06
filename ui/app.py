#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
«Ведение проектов · РЦК» — локальный web-интерфейс, Прогон 3.
Экран: линейка этапов методологии (МУ-65) + два инструмента:
«Поиск узкого места» (таблица / вставка из Excel / файл JSON, живой пересчёт)
и «ЭЭ-калькулятор» v0.1 (спека № 2, концевой серийный поток, живой пересчёт).
Ядра узкие_места.py и ээ_калькулятор.py импортируются как модули;
логика детекторов и формул не меняется.
Запуск: python3 app.py → http://localhost:8000 (или следующий свободный порт).
"""

import html
import importlib.util
import json
import math
import re
import secrets
import socket
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except ImportError:  # без openpyxl вкладка Excel честно отключена
    openpyxl = None

# --- Импорт ядра как модуля (логика не меняется) ---
CORE_PATH = Path(__file__).resolve().parent.parent / "узкие_места.py"
spec = importlib.util.spec_from_file_location("uzkie_mesta", CORE_PATH)
uzkie_mesta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uzkie_mesta)

# --- Импорт второго ядра: ЭЭ-калькулятор v0.1 ---
EE_PATH = Path(__file__).resolve().parent.parent / "ээ_калькулятор.py"
spec_ee = importlib.util.spec_from_file_location("ee_kalk", EE_PATH)
ee_kalk = importlib.util.module_from_spec(spec_ee)
spec_ee.loader.exec_module(ee_kalk)

# --- Импорт ядер волны 2: протокол закрытия (этап 5) и ОРД/SMART (этап 1) ---
PROT_PATH = Path(__file__).resolve().parent.parent / "protokol_zakrytiya.py"
spec_pz = importlib.util.spec_from_file_location("protokol_zakrytiya", PROT_PATH)
protokol_zakrytiya = importlib.util.module_from_spec(spec_pz)
spec_pz.loader.exec_module(protokol_zakrytiya)

ORD_PATH = Path(__file__).resolve().parent.parent / "ord_smart.py"
spec_os = importlib.util.spec_from_file_location("ord_smart", ORD_PATH)
ord_smart = importlib.util.module_from_spec(spec_os)
spec_os.loader.exec_module(ord_smart)

# --- Импорт ядра пакета документов ФЦК v01 (акт начала + соглашение) ---
DOK_PATH = Path(__file__).resolve().parent.parent / "dokumenty_fck.py"
spec_dok = importlib.util.spec_from_file_location("dokumenty_fck", DOK_PATH)
dokumenty_fck = importlib.util.module_from_spec(spec_dok)
spec_dok.loader.exec_module(dokumenty_fck)

# --- Импорт ядра КПСЦ: карта потока создания ценности (этап 2, волна 6) ---
VSM_PATH = Path(__file__).resolve().parent.parent / "vsm_karta.py"
spec_vsm = importlib.util.spec_from_file_location("vsm_karta", VSM_PATH)
vsm_karta = importlib.util.module_from_spec(spec_vsm)
spec_vsm.loader.exec_module(vsm_karta)

# --- Импорт экспортёра справки ФЦК (ЭЭ → их форма 1.4, xlsm) ---
EEX_PATH = Path(__file__).resolve().parent.parent / "ээ_экспорт_фцк.py"
spec_eex = importlib.util.spec_from_file_location("ee_export_fck", EEX_PATH)
ee_export = importlib.util.module_from_spec(spec_eex)
spec_eex.loader.exec_module(ee_export)

# --- Импорт ядра этапа 0 «Предстарт»: отбор предприятий (МР-15-2026 ред.5) ---
OTBOR_PATH = Path(__file__).resolve().parent.parent / "otbor.py"
spec_ob = importlib.util.spec_from_file_location("otbor", OTBOR_PATH)
otbor = importlib.util.module_from_spec(spec_ob)
spec_ob.loader.exec_module(otbor)

# --- Импорт ядра этапа 0 «Предстарт»: выбор пилотного потока (МР-15-2026) ---
POTOK_PATH = Path(__file__).resolve().parent.parent / "otbor_potok.py"
spec_pk = importlib.util.spec_from_file_location("otbor_potok", POTOK_PATH)
otbor_potok = importlib.util.module_from_spec(spec_pk)
spec_pk.loader.exec_module(otbor_potok)

# --- Импорт ядра этапа 2 «Диагностика»: калькулятор показателей потока ---
PP_PATH = Path(__file__).resolve().parent.parent / "pokazateli_potoka.py"
spec_pp = importlib.util.spec_from_file_location("pokazateli_potoka", PP_PATH)
pokazateli_potoka = importlib.util.module_from_spec(spec_pp)
spec_pp.loader.exec_module(pokazateli_potoka)

# --- Импорт ядра этапа 2 «Диагностика»: OEE-калькулятор (OEE-75) ---
OEE_PATH = Path(__file__).resolve().parent.parent / "oee_kalkulator.py"
spec_oee = importlib.util.spec_from_file_location("oee_kalkulator", OEE_PATH)
oee_kalkulator = importlib.util.module_from_spec(spec_oee)
spec_oee.loader.exec_module(oee_kalkulator)

# --- Импорт ядра этапа «Разработка»: генератор мероприятий (спека № 3) ---
# meropriyatiya.py импортирует otbor_potok и biblioteka_instrumentov как
# обычные модули — каталог Прототипа должен быть в sys.path.
_PROT_DIR = Path(__file__).resolve().parent.parent
if str(_PROT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROT_DIR))
MER_PATH = _PROT_DIR / "meropriyatiya.py"
spec_mp = importlib.util.spec_from_file_location("meropriyatiya", MER_PATH)
meropriyatiya = importlib.util.module_from_spec(spec_mp)
spec_mp.loader.exec_module(meropriyatiya)

# --- Импорт ядра симулятора потока (ДСС «что если», ломтик С1) ---
SIM_PATH = Path(__file__).resolve().parent / "simulyator.py"
spec_sim = importlib.util.spec_from_file_location("simulyator", SIM_PATH)
simulyator = importlib.util.module_from_spec(spec_sim)
spec_sim.loader.exec_module(simulyator)

# --- Импорт сборщика данных фаст-презентации (Спека П1, ломтик П2) ---
PREZA_PATH = Path(__file__).resolve().parent / "preza_data.py"
spec_prz = importlib.util.spec_from_file_location("preza_data", PREZA_PATH)
preza_data = importlib.util.module_from_spec(spec_prz)
spec_prz.loader.exec_module(preza_data)

# --- Импорт PPTX-движка фаст-презентации (Спека П1, ломтик П3) ---
PREZA_PPTX_PATH = Path(__file__).resolve().parent / "preza_pptx.py"
spec_pptx = importlib.util.spec_from_file_location("preza_pptx", PREZA_PPTX_PATH)
preza_pptx = importlib.util.module_from_spec(spec_pptx)
spec_pptx.loader.exec_module(preza_pptx)

# --- LLM-слой (Спека № 4, ломтик Л4.1) ---
# Инфраструктура вызова LLM + QC-гейты 1–3 + откат на детерминированный
# генератор. Маршрутов пока нет (Л4.4); модуль импортируется, чтобы
# глубокий режим был готов и таблицы llm_* создались миграцией при старте.
# Без LLM_API_KEY glubokiy_ili_bystriy() честно откатывается на быстрый
# режим с пометкой rezhim="bystriy_otkat".
LLM_PATH = _PROT_DIR / "llm_sloy.py"
spec_llm = importlib.util.spec_from_file_location("llm_sloy", LLM_PATH)
llm_sloy = importlib.util.module_from_spec(spec_llm)
spec_llm.loader.exec_module(llm_sloy)

# --- Импорт экстрактора листов производственного анализа (ПА-73) ---
EKSTR_PATH = _PROT_DIR / "ekstraktor_pa.py"
spec_ep = importlib.util.spec_from_file_location("ekstraktor_pa", EKSTR_PATH)
ekstraktor_pa = importlib.util.module_from_spec(spec_ep)
spec_ep.loader.exec_module(ekstraktor_pa)

# --- Импорт ядра «Цифровой замер» (Протокол № 43, п. 2) ---
ZAMER_PATH = _PROT_DIR / "cifrovoy_zamer.py"
spec_cz = importlib.util.spec_from_file_location("cifrovoy_zamer", ZAMER_PATH)
cifrovoy_zamer = importlib.util.module_from_spec(spec_cz)
spec_cz.loader.exec_module(cifrovoy_zamer)

# --- Импорт экспортёра в шаблон «Вскрытие резервов» V4.7.2 (ВР-76) ---
VR_PATH = _PROT_DIR / "vr_export.py"
spec_vr = importlib.util.spec_from_file_location("vr_export", VR_PATH)
vr_export = importlib.util.module_from_spec(spec_vr)
spec_vr.loader.exec_module(vr_export)

# Каталог файлов прогонов (docx-пакеты ОРД и протоколы) — рядом с БД
ФАЙЛЫ_DIR = Path(__file__).resolve().parent / "файлы"
ФАЙЛЫ_DIR.mkdir(exist_ok=True)

DEMO_PATH = Path(__file__).resolve().parent.parent / "данные_окз_слепой.json"
EE_DEMO = {
    "новохром": Path(__file__).resolve().parent.parent / "данные_ээ_новохром.json",
    "оренбив": Path(__file__).resolve().parent.parent / "данные_ээ_оренбив.json",
    # Э1-Б: демо-вход ред. 4 (модель v5.23, «Пример расчета») для прогонов приёмки
    "пример": Path(__file__).resolve().parent.parent / "данные_ээ_пример_v523.json",
}

app = Flask(__name__)

# === Базовая авторизация (внешний доступ, путь Б/туннель) ===
# Включается только если задан AGENT_CEH_PASSWORD (локальный запуск без пароля — как раньше).
import os
from functools import wraps

_AUTH_PASSWORD = os.environ.get("AGENT_CEH_PASSWORD", "")
_AUTH_USER = os.environ.get("AGENT_CEH_USER", "рцк")


@app.before_request
def _basic_auth():
    if not _AUTH_PASSWORD:
        return None  # защита выключена (локальный режим)
    auth = request.authorization
    if auth and auth.username == _AUTH_USER and auth.password == _AUTH_PASSWORD:
        return None
    return Response(
        "Требуется вход в «Ведение проектов · РЦК».",
        401,
        {"WWW-Authenticate": 'Basic realm="Ведение проектов РЦК", charset="UTF-8"'},
    )

# === Строгий JSON и конечность чисел (фикс У-1/У-3) ===
# Python json принимает NaN/Infinity; 1e999 молча становится inf. Оба пути закрыты:
# 1) parse_constant отклоняет литералы NaN/Infinity/-Infinity в теле запроса;
# 2) рекурсивная проверка math.isfinite ловит inf от переполнения (1e999).
def _не_конечное(с):
    raise ValueError(f"значение «{с}» — не конечное число "
                     "(NaN/Infinity в JSON недопустимы)")


def прочитать_json_тело(спека):
    """Строгий разбор тела запроса. Возвращает (данные, None) или (None, (ответ, код))."""
    raw = request.get_data(cache=True)
    try:
        return json.loads(raw, parse_constant=_не_конечное), None
    except ValueError as e:
        return None, ({"ok": False, "errors": [
            f"тело запроса не разобрано ({e}) — {спека}"]}, 400)


def найти_нечисла(x, путь=""):
    """Рекурсивная проверка входа: каждое float обязано быть конечным."""
    out = []
    if isinstance(x, float) and not math.isfinite(x):
        out.append(f"поле «{путь or 'корень'}»: не конечное число "
                   "(inf от переполнения, напр. 1e999) — проверьте вход")
    elif isinstance(x, dict):
        for k, v in x.items():
            out += найти_нечисла(v, f"{путь}.{k}" if путь else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            out += найти_нечисла(v, f"{путь}[{i + 1}]")
    return out


def _конечное(v):
    """Число (не bool), конечное — единый предикат валидаторов."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# Потолки снапшота прогона (фикс У-11): один клиент не должен раздувать БД.
MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
MAX_ОПЕРАЦИЙ = 500
MAX_ИМЯ_ОПЕРАЦИИ = 300

# --- Вкладка «Файл Excel (.xlsx)»: ассистент разметки ---
# Лимит 20 МБ; загруженные книги кешируются в памяти по токену (не на диске).
MAX_EXCEL_BYTES = 20 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_EXCEL_BYTES
EXCEL_CACHE = {}          # token -> {"bytes": ..., "name": ..., "ts": ...}
EXCEL_CACHE_TTL = 3600    # сек
PREVIEW_ROWS = 30
PREVIEW_COLS = 20
EXTRACT_MAX_ROWS = 500    # страховка от разметки «до конца листа» на гигантских листах


def _excel_cache_gc():
    now = time.time()
    for tok in [t for t, v in EXCEL_CACHE.items() if now - v["ts"] > EXCEL_CACHE_TTL]:
        del EXCEL_CACHE[tok]
    while len(EXCEL_CACHE) > 5:  # не более 5 книг одновременно
        oldest = min(EXCEL_CACHE, key=lambda t: EXCEL_CACHE[t]["ts"])
        del EXCEL_CACHE[oldest]


def _load_wb(raw, имя_файла):
    """Открыть книгу из байтов; вернуть (wb, ошибка)."""
    if openpyxl is None:
        return None, ("модуль openpyxl не установлен в окружении сервера — "
                      "вкладка Excel недоступна")
    import io
    try:
        return openpyxl.load_workbook(io.BytesIO(raw), data_only=True), None
    except Exception as e:
        return None, (f"файл «{имя_файла}» не читается как .xlsx "
                      f"({type(e).__name__}). Если это старый .xls — "
                      f"пересохраните его в Excel как .xlsx")


def _cell_str(v):
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return str(v)


def parse_num_ru(s):
    """«1 234,5» / «30%» / «38,7 %» → float; «—», «», мусор → None/undefined."""
    if s is None:
        return None, False
    if isinstance(s, (int, float)):
        return float(s), True
    t = str(s).strip()
    if t == "" or t in ("-", "—", "–", "н/д", "н/а"):
        return None, False
    t = t.replace("\xa0", "").replace(" ", "")
    percent = t.endswith("%")
    if percent:
        t = t[:-1].strip()
    t = t.replace(",", ".")
    try:
        return float(t), True
    except ValueError:
        return None, False  # мусор — не число


def sheet_preview(ws):
    """Превью листа: сетка PREVIEW_ROWS×PREVIEW_COLS с координатами;
    объединённые ячейки разворачиваются значением главной (merged=True)."""
    merged_map = {}
    for rng in ws.merged_cells.ranges:
        main = ws.cell(rng.min_row, rng.min_col).value
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    merged_map[(r, c)] = main
    rows = []
    max_r = min(ws.max_row or 1, PREVIEW_ROWS)
    max_c = min(ws.max_column or 1, PREVIEW_COLS)
    for r in range(1, max_r + 1):
        row = []
        for c in range(1, max_c + 1):
            coord = f"{get_column_letter(c)}{r}"
            v = ws.cell(r, c).value
            if v is None and (r, c) in merged_map:
                row.append({"coord": coord, "value": _cell_str(merged_map[(r, c)]),
                            "merged": True})
            else:
                row.append({"coord": coord, "value": _cell_str(v)})
        rows.append(row)
    return {"name": ws.title, "max_row": ws.max_row, "max_col": ws.max_column,
            "rows": rows,
            "truncated": (ws.max_row or 0) > PREVIEW_ROWS or (ws.max_column or 0) > PREVIEW_COLS}


@app.route("/api/excel_preview", methods=["POST"])
def api_excel_preview():
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"ok": False, "errors": ["файл не выбран"]}), 400
    имя = f.filename
    raw = f.read()
    if len(raw) > MAX_EXCEL_BYTES:
        return jsonify({"ok": False, "errors": [
            f"файл «{имя}» больше 20 МБ ({len(raw) / 1048576:.1f} МБ) — "
            f"сохраните копию без лишних листов/фото и загрузите снова"]}), 400
    if имя.lower().endswith(".xls"):
        return jsonify({"ok": False, "errors": [
            f"«{имя}» — старый формат .xls; он не поддерживается "
            f"(библиотека xlrd в окружении отсутствует). "
            f"Откройте файл в Excel и пересохраните как .xlsx"]}), 400
    wb, err = _load_wb(raw, имя)
    if err:
        return jsonify({"ok": False, "errors": [err]}), 400
    _excel_cache_gc()
    token = secrets.token_hex(8)
    EXCEL_CACHE[token] = {"bytes": raw, "name": имя, "ts": time.time()}
    try:
        sheets = [sheet_preview(ws) for ws in wb.worksheets]
    finally:
        wb.close()
    return jsonify({"ok": True, "token": token, "file_name": имя, "sheets": sheets})


@app.route("/api/excel_extract", methods=["POST"])
def api_excel_extract():
    """Извлечение операций по разметке пользователя.
    orientation=rows: строка = операция, колонки name/tc/prod/vpp/ret (буквы).
    orientation=cols: столбец = операция, строки name/tc/... (номера) — карты КПСЦ."""
    d, err = прочитать_json_тело("тело: {token, sheet, orientation, marks, data_start…}")
    if err:
        return jsonify(err[0]), err[1]
    d = d or {}
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    token = d.get("token")
    entry = EXCEL_CACHE.get(token)
    if entry is None:
        return jsonify({"ok": False, "errors": [
            "сессия файла истекла — загрузите .xlsx заново"]}), 400
    wb, err = _load_wb(entry["bytes"], entry["name"])
    if err:
        return jsonify({"ok": False, "errors": [err]}), 400
    try:
        лист = d.get("sheet")
        ws = next((w for w in wb.worksheets if w.title == лист), None)
        if ws is None:
            return jsonify({"ok": False, "errors": [f"лист «{лист}» не найден"]}), 400
        orient = d.get("orientation", "rows")
        tc_seconds = d.get("tc_unit") == "sec"
        ПОЛЯ = [("name", "имя"), ("tc", "тц_мин"), ("prod", "производительность_т_ч"),
                ("vpp", "впп_сек"), ("ret", "возврат_пкт")]
        marks = d.get("marks") or {}
        if not marks.get("name"):
            return jsonify({"ok": False, "errors": [
                "разметка неполная: укажите, где лежит название операции"]}), 400

        def col_idx(letter):
            letter = str(letter).strip().upper()
            if not re.fullmatch(r"[A-Z]{1,3}", letter):
                return None
            n = 0
            for ch in letter:
                n = n * 26 + (ord(ch) - 64)
            return n

        def cell(r, c):
            return ws.cell(r, c).value

        # Объединённые ячейки НЕ разворачиваем при извлечении: значение читается
        # только из главной ячейки диапазона. Иначе объединённая метрика блока
        # (карта ОКЗ: ВПП C21:J21) размножается на подоперации и ломает ранжирование.
        # В превью объединённые ячейки подсвечены — пользователь видит, где главная.

        def val(r, c):
            return cell(r, c)

        ops, warnings = [], []
        # Фикс У-10: мусорный/отрицательный data_start — честный JSON 400, не 500-HTML
        try:
            start = int(d.get("data_start") or 1)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "errors": [
                f"data_start «{d.get('data_start')}» — должна быть целым числом ≥ 1"]}), 400
        if start < 1:
            return jsonify({"ok": False, "errors": [
                f"data_start {start} < 1 — нумерация строк/столбцов Excel начинается с 1"]}), 400
        try:
            end = int(d.get("data_end")) if d.get("data_end") not in (None, "") else None
        except (TypeError, ValueError):
            end = None

        def take(r, c):
            """Прочитать одну ячейку по разметке поля."""
            return val(r, c)

        if orient == "cols":
            rows_map = {}
            for key, _ in ПОЛЯ:
                if marks.get(key):
                    try:
                        rows_map[key] = int(marks[key])
                    except (TypeError, ValueError):
                        return jsonify({"ok": False, "errors": [
                            f"строка для поля «{key}» должна быть числом"]}), 400
            max_c = min(ws.max_column or 1, start + EXTRACT_MAX_ROWS)
            if end:
                max_c = min(max_c, end)
            for c in range(start, max_c + 1):
                имя_v = take(rows_map["name"], c)
                имя = str(имя_v).strip() if имя_v is not None else ""
                op_vals, мусор = {}, []
                for key, json_key in ПОЛЯ[1:]:
                    if key not in rows_map:
                        continue
                    raw_v = take(rows_map[key], c)
                    n, isnum = parse_num_ru(raw_v)
                    if isnum:
                        if key == "tc" and tc_seconds:
                            n = round(n / 60, 4)
                        op_vals[json_key] = n
                    elif raw_v is not None and str(raw_v).strip() not in ("", "-", "—"):
                        мусор.append(f"{имя or get_column_letter(c)}: «{raw_v}» — не число")
                if not имя and not op_vals and not мусор:
                    continue  # пустой столбец
                if not op_vals:
                    # столбец без единого числа (подоперация под объединённой шапкой
                    # или строка-комментарий) — пропускаем с честным предупреждением
                    if имя:
                        warnings.append(f"«{имя}» ({get_column_letter(c)}): нет чисел — пропущено")
                    warnings.extend(мусор)
                    continue
                op = {"имя": имя or f"столбец {get_column_letter(c)}"}
                op.update(op_vals)
                ops.append(op)
                warnings.extend(мусор)
        else:  # rows
            cols_map = {}
            for key, _ in ПОЛЯ:
                if marks.get(key):
                    ci = col_idx(marks[key])
                    if ci is None:
                        return jsonify({"ok": False, "errors": [
                            f"колонка «{marks[key]}» для поля «{key}» — не буква Excel"]}), 400
                    cols_map[key] = ci
            max_r = min(ws.max_row or 1, start + EXTRACT_MAX_ROWS)
            if end:
                max_r = min(max_r, end)
            for r in range(start, max_r + 1):
                имя_v = take(r, cols_map["name"])
                имя = str(имя_v).strip() if имя_v is not None else ""
                op_vals, мусор = {}, []
                for key, json_key in ПОЛЯ[1:]:
                    if key not in cols_map:
                        continue
                    raw_v = take(r, cols_map[key])
                    n, isnum = parse_num_ru(raw_v)
                    if isnum:
                        if key == "tc" and tc_seconds:
                            n = round(n / 60, 4)
                        op_vals[json_key] = n
                    elif raw_v is not None and str(raw_v).strip() not in ("", "-", "—"):
                        мусор.append(f"строка {r}: «{raw_v}» — не число")
                if not имя and not op_vals and not мусор:
                    continue  # пустая строка
                if not op_vals:
                    # строка без единого числа — пропускаем с предупреждением
                    if имя:
                        warnings.append(f"«{имя}» (строка {r}): нет чисел — пропущено")
                    warnings.extend(мусор)
                    continue
                op = {"имя": имя or f"строка {r}"}
                op.update(op_vals)
                ops.append(op)
                warnings.extend(мусор)
        if not ops:
            return jsonify({"ok": False, "errors": [
                "по заданной разметке не извлечено ни одной операции — "
                "проверьте лист, ориентацию и стартовую строку/столбец"]}), 400
        return jsonify({"ok": True, "операции": ops, "warnings": warnings,
                        "file_name": entry["name"], "sheet": лист})
    finally:
        wb.close()


# --- Загрузка листа производственного анализа (ПА-73): авто-извлечение ---
@app.route("/api/ekstraktor_pa", methods=["POST"])
def api_ekstraktor_pa():
    """multipart file (.xlsx/.xlsm) → izvlech → JSON с операциями и мета.
    Ответ всегда 200 при читаемом запросе; rez['ok']=False — формат не
    распознан/пуст (подробности в preduprezhdeniya) — человек решает глазами."""
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"ok": False, "errors": ["файл не выбран"]}), 400
    имя = f.filename
    raw = f.read()
    if len(raw) > MAX_EXCEL_BYTES:
        return jsonify({"ok": False, "errors": [
            f"файл «{имя}» больше 20 МБ ({len(raw) / 1048576:.1f} МБ) — "
            f"сохраните копию без лишних листов/фото и загрузите снова"]}), 400
    rez = ekstraktor_pa.izvlech(raw, имя)
    return jsonify(rez)


@app.errorhandler(413)
def too_large(_e):
    # Фикс У-14: текст по эндпоинту — не все 413 связаны с загрузкой Excel
    if request.endpoint in ("api_excel_preview", "api_ekstraktor_pa"):
        текст = ("файл больше 20 МБ — сохраните копию без лишних листов/фото "
                 "и загрузите снова")
    else:
        текст = ("запрос больше 20 МБ — уменьшите объём данных "
                 "(снимок прогона дополнительно ограничен 5 МБ)")
    return jsonify({"ok": False, "errors": [текст]}), 413


@app.errorhandler(sqlite3.Error)
def db_error(e):
    """Фикс У-4: ошибки БД — всегда JSON 503, никогда голый 500-HTML."""
    app.logger.error("БД: %s", e)
    return jsonify({"ok": False, "errors": [
        f"База данных недоступна: {e}. Проверьте целостность файла agent_ceh.db "
        "и перезапустите сервис"]}), 503


@app.errorhandler(Exception)
def any_error(e):
    """Страховочная сетка: любой непредвиденный сбой — JSON, не HTML-страница Flask."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    app.logger.exception("необработанная ошибка")
    return jsonify({"ok": False, "errors": [
        f"Внутренняя ошибка сервера ({type(e).__name__}): {e}"]}), 500



def validirovat(d):
    """Проверка входа по схеме спеки. Ошибки привязаны к строке и полю таблицы.
    Числа проверяются на конечность (фикс У-1: NaN проходит сравнения молча)."""
    oshibki = []
    if not isinstance(d, dict):
        return ["корневой элемент данных должен быть объектом"]
    ops = d.get("операции")
    if not ops:
        oshibki.append("таблица операций пуста: добавьте хотя бы одну строку")
    elif not isinstance(ops, list):
        oshibki.append("поле «операции» должно быть массивом")
    else:
        for i, op in enumerate(ops, 1):
            if not isinstance(op, dict):
                oshibki.append(f"строка {i}: операция должна быть объектом")
                continue
            имя = op.get("имя") or f"строка {i}"
            if not op.get("имя"):
                oshibki.append(f"строка {i}: не заполнено поле «операция» (имя)")
            if "тц_мин" not in op or op.get("тц_мин") is None:
                oshibki.append(f"строка {i} «{имя}»: не заполнено поле «Тц, мин»")
            elif not _конечное(op.get("тц_мин")) or op["тц_мин"] <= 0:
                oshibki.append(f"строка {i} «{имя}»: поле «Тц, мин» должно быть "
                               f"конечным числом > 0")
            for поле, подпись in (("производительность_т_ч", "Произв., т/ч"),
                                  ("впп_сек", "ВПП, сек"), ("возврат_пкт", "Возврат, %")):
                v = op.get(поле)
                if v is not None and (not _конечное(v) or v < 0):
                    oshibki.append(f"строка {i} «{имя}»: поле «{подпись}» должно быть "
                                   f"конечным неотрицательным числом")
    v = d.get("впп_итого_сек")
    if v is not None and (not _конечное(v) or v <= 0):
        oshibki.append("поле «ВПП итого, сек» должно быть конечным числом > 0")
    v = d.get("персонал_итого")
    if v is not None and (not _конечное(v) or v <= 0):
        oshibki.append("поле «Персонал, чел.» должно быть конечным числом > 0")
    for поле, подпись in (("спрос_шт_в_период", "Спрос, шт/период"),
                          ("доступное_время_мин", "Доступное время, мин"),
                          ("такт_линии_мин", "Такт, мин")):
        v = d.get(поле)
        if v is not None and (not _конечное(v) or v <= 0):
            oshibki.append(f"поле «{подпись}» должно быть конечным числом > 0")
    return oshibki


# --- Минимальный markdown→HTML рендер (без внешних зависимостей) ---
def md_inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def md_to_html(md):
    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h1>{md_inline(ln[2:])}</h1>")
        elif ln.startswith("## "):
            out.append(f"<h2>{md_inline(ln[3:])}</h2>")
        elif ln.startswith("> "):
            out.append(f"<blockquote>{md_inline(ln[2:])}</blockquote>")
        elif re.match(r"^\d+\. ", ln):
            items = []
            while i < len(lines) and (re.match(r"^\d+\. ", lines[i]) or lines[i].startswith("   - ")):
                if re.match(r"^\d+\. ", lines[i]):
                    items.append([md_inline(re.sub(r"^\d+\. ", "", lines[i])), []])
                elif items:
                    items[-1][1].append(md_inline(lines[i][5:]))
                i += 1
            i -= 1
            ol = ["<ol>"]
            for main, subs in items:
                ol.append(f"<li>{main}")
                if subs:
                    ol.append("<ul>" + "".join(f"<li>{s}</li>" for s in subs) + "</ul>")
                ol.append("</li>")
            ol.append("</ol>")
            out.append("".join(ol))
        elif ln.lstrip().startswith("- "):
            items = []
            while i < len(lines) and lines[i].lstrip().startswith("- "):
                indent = len(lines[i]) - len(lines[i].lstrip())
                items.append((indent, md_inline(lines[i].lstrip()[2:])))
                i += 1
            i -= 1
            ul, depth = ["<ul>"], 0
            for indent, txt in items:
                lvl = indent // 2
                if lvl > depth:
                    ul.append("<ul>")
                elif lvl < depth:
                    ul.append("</ul>")
                depth = lvl
                ul.append(f"<li>{txt}</li>")
            while depth > 0:
                ul.append("</ul>")
                depth -= 1
            ul.append("</ul>")
            out.append("".join(ul))
        elif ln.strip():
            out.append(f"<p>{md_inline(ln)}</p>")
        i += 1
    return "\n".join(out)


def raschet(d):
    """Полный прогон ядра. Возвращает dict-ответ для /api/raschet."""
    errs = validirovat(d)
    if errs:
        return {"ok": False, "errors": errs}
    errs = uzkie_mesta.proverit_vhod(d)
    if errs:
        return {"ok": False, "errors": errs}
    try:
        r = uzkie_mesta.razbor(d)
        report = uzkie_mesta.otchyot(d, r)
    except Exception as e:  # неожиданная структура, прошедшая валидацию
        return {"ok": False, "errors": [f"Ядро не смогло обработать данные: {e}"]}
    glavnoe = r.get("главное")
    # Масштаб главного УМ — берём из результата ядра (доли_впп), логику не дублируем
    masshtab = None
    if glavnoe:
        for имя, сек, доля in r.get("доли_впп", []):
            if имя == glavnoe["имя"]:
                masshtab = {"сек": сек, "ч": round(сек / 3600, 1),
                            "доля_пкт": round(доля, 1)}
                break
    return {"ok": True, "report_md": report, "result_html": md_to_html(report),
            "flow_name": d.get("поток") or "поток",
            "glavnoe": glavnoe["имя"] if glavnoe else None,
            "glavnoe_podtverzhdeno": bool(glavnoe and glavnoe["сошлось"]),
            "glavnoe_masshtab": masshtab,
            "domerit_top3": (r.get("домерить") or [])[:3]}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/raschet", methods=["POST"])
def api_raschet():
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке № 1")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом по спеке № 1"]}), 400
    return jsonify(raschet(d))


@app.route("/api/vsm", methods=["POST"])
def api_vsm():
    """Карта потока (КПСЦ): тот же вход, что у «Поиска узкого места» (спека № 1),
    + опционально поле glavnoe — имя главного УМ из последнего расчёта (подсветка).
    Ответ: SVG inline + компактные итоги; SVG в БД не хранится (перестраивается)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке № 1 "
                                 "(+ опционально glavnoe)")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом по спеке № 1"]}), 400
    errs = validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        svg, итоги = vsm_karta.строить_svg(d, glavnoe=d.get("glavnoe"))
    except ValueError as e:
        return jsonify({"ok": False, "errors": [str(e)]}), 400
    except Exception as e:
        return jsonify({"ok": False,
                        "errors": [f"Ядро КПСЦ не смогло построить карту: {e}"]})
    return jsonify({"ok": True, "svg": svg, "итоги_json": итоги})


@app.route("/api/demo")
def api_demo():
    """Демо-набор «ОКЗ» — читается с диска при каждом запросе."""
    try:
        return jsonify(json.loads(DEMO_PATH.read_text(encoding="utf-8")))
    except OSError as e:
        return jsonify({"ok": False,
                        "errors": [f"Не удалось прочитать демо-файл: {e}"]}), 500


@app.route("/api/otbor/skelet")
def api_otbor_skelet():
    """Структура чек-листов обоих треков (Прил. № 5 — РЦК, Прил. № 4 — ФЦК)
    и формальных критериев (п. 3.4) — фронт строит форму без дублирования
    формулировок МР. Поля верхнего уровня (разделы/максимум/трек) оставлены
    для обратной совместимости и описывают трек РЦК."""
    спеки = {трек: {"название": с["название"], "приложение": с["приложение"],
                    "разделы": с["чеклист"], "максимум": с["максимум"]}
             for трек, с in otbor.СПЕКИ_ТРЕКОВ.items()}
    return jsonify({"ok": True,
                    "формальные": [{"ключ": k, "название": н}
                                   for k, н in otbor.ФОРМАЛЬНЫЕ_КРИТЕРИИ],
                    "разделы": otbor.ЧЕКЛИСТ_РЦК,
                    "порог": otbor.ПОРОГ, "максимум": otbor.МАКСИМУМ,
                    "трек": "рцк",
                    "треки": ["рцк", "фцк"], "спеки": спеки})


@app.route("/api/otbor/potok/skelet")
def api_otbor_potok_skelet():
    """Структура критериев потока и карты признаков потерь (разделы 5–6
    чек-листов МР) — фронт строит форму помощника выбора пилотного потока."""
    return jsonify({"ok": True,
                    "критерии": [{"ключ": k, "название": н, "обязательный": об}
                                 for k, н, об in otbor_potok.КРИТЕРИИ],
                    "признаки": [{"ключ": k, "название": н}
                                 for k, н in otbor_potok.ПРИЗНАКИ_ПОТЕРЬ],
                    "макс_кандидатов": otbor_potok.МАКС_КАНДИДАТОВ,
                    "максимум": otbor_potok.МАКСИМУМ})


@app.route("/api/otbor/potok", methods=["POST"])
def api_otbor_potok():
    """Расчёт выбора пилотного потока (скоринг кандидатов + рекомендация).
    Ответ: результат ядра + скоринг-карта md/html; в БД здесь ничего не
    пишется — снапшот создаётся через POST /api/progony (otbor_potok)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке "
                                 "инструмента «Выбор пилотного потока»")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом "
                                   "по спеке инструмента «Выбор пилотного "
                                   "потока»"]}), 400
    errs = otbor_potok.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        r = otbor_potok.raschet(d)
    except Exception as e:
        return jsonify({"ok": False,
                        "errors": [f"Ядро выбора потока не смогло обработать "
                                   f"данные: {e}"]})
    return jsonify({"ok": True, "результат": r,
                    "скоринг_карта_md": r["скоринг_карта_md"],
                    "скоринг_карта_html": md_to_html(r["скоринг_карта_md"])})


@app.route("/api/otbor", methods=["POST"])
def api_otbor():
    """Расчёт отбора предприятия (пре-скоринг + чек-лист РЦК + скоринг-карта).
    Ответ: результат ядра + скоринг-карта md/html; в БД здесь ничего не
    пишется — снапшот создаётся через POST /api/progony (инструмент otbor)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке "
                                 "инструмента «Отбор»")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом "
                                   "по спеке инструмента «Отбор»"]}), 400
    errs = otbor.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        r = otbor.raschet(d)
    except Exception as e:
        return jsonify({"ok": False,
                        "errors": [f"Ядро отбора не смогло обработать данные: {e}"]})
    return jsonify({"ok": True, "результат": r,
                    "скоринг_карта_md": r["скоринг_карта_md"],
                    "скоринг_карта_html": md_to_html(r["скоринг_карта_md"])})


# --- Калькулятор показателей потока (этап 2 «Диагностика», живой пересчёт) ---
@app.route("/api/potok_calc", methods=["POST"])
def api_potok_calc():
    """Расчёт показателей потока (такт, ВПП, выработка, загрузка, узкое место).
    Ответ: результат ядра + отчёт md/html; в БД здесь ничего не пишется —
    снапшот создаётся через POST /api/progony (инструмент potok_calc)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке "
                                 "инструмента «Калькулятор показателей потока»")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом по спеке "
                                   "инструмента «Калькулятор показателей потока»"]}), 400
    errs = pokazateli_potoka.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        r = pokazateli_potoka.raschet(d)
        отчёт = pokazateli_potoka.otchyot(d, r)
        итоги = pokazateli_potoka.itogi(d, r)
    except Exception as e:
        return jsonify({"ok": False,
                        "errors": [f"Ядро показателей потока не смогло обработать "
                                   f"данные: {e}"]}), 500
    return jsonify({"ok": True, "результат": r, "итоги": итоги,
                    "report_md": отчёт, "result_html": md_to_html(отчёт),
                    "flow_name": d.get("поток") or "поток"})


# --- OEE-калькулятор (этап 2 «Диагностика», живой пересчёт; OEE-75) ---
@app.route("/api/oee", methods=["POST"])
def api_oee():
    """Расчёт OEE (A × P × Q, шесть больших потерь, мировой класс, узкая
    составляющая, потенциал). Ответ: результат ядра + отчёт md/html; в БД
    здесь ничего не пишется — снапшот создаётся через POST /api/progony
    (инструмент oee)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке "
                                 "инструмента «OEE-калькулятор»")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом по спеке "
                                   "инструмента «OEE-калькулятор»"]}), 400
    errs = oee_kalkulator.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        r = oee_kalkulator.raschet(d)
        отчёт = oee_kalkulator.otchyot(d, r)
        итоги = oee_kalkulator.itogi(d, r)
    except Exception as e:
        return jsonify({"ok": False,
                        "errors": [f"Ядро OEE-калькулятора не смогло обработать "
                                   f"данные: {e}"]}), 500
    return jsonify({"ok": True, "результат": r, "итоги": итоги,
                    "report_md": отчёт, "result_html": md_to_html(отчёт),
                    "flow_name": d.get("поток") or "участок"})


# --- Симулятор потока (ДСС «что если», ломтик С1; ШТУРМ_симулятор.md) ---
@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    """Дискретно-событийная симуляция потока: вход — таблица операций в формате
    «Поиска узкого места»/калькулятора потока + блок «симуляция» (seed,
    вариативность, ёмкость буферов, кран, число прогонов). Выход: базовый
    прогон (такт, Тц, ВПП, выпуск, НЗП, загрузка, узкое место) + оценка
    медиана ± разброс по n прогонам. Если передан id_proekta — прогон пишется
    в agent_ceh.db как инструмент simulation (immutable-снапшот)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке "
                                 "симулятора потока (формат potok_calc + блок "
                                 "«симуляция»)")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False, "errors": [
            "тело запроса должно быть JSON-объектом"]}), 400
    errs = simulyator.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        r = simulyator.оценка(d)
        отчёт = simulyator.отчёт(d, r)
        итоги = simulyator.итоги(d, r)
    except Exception as e:
        return jsonify({"ok": False,
                        "errors": [f"Ядро симулятора не смогло обработать "
                                   f"данные: {e}"]}), 500
    ответ = {"ok": True, "результат": r, "итоги": итоги,
             "report_md": отчёт, "result_html": md_to_html(отчёт),
             "flow_name": d.get("поток") or "поток"}
    pid = d.get("id_proekta")
    if pid is not None:
        if type(pid) is not int or pid <= 0:
            return jsonify({"ok": False, "errors": [
                "поле «id_proekta» должно быть целым числом > 0"]}), 400
        with db() as con:
            pj = con.execute("SELECT id FROM proekty WHERE id = ?",
                             (pid,)).fetchone()
            if pj is None:
                return jsonify({"ok": False,
                                "errors": [f"проект № {pid} не найден"]}), 404
            вход = {k: v for k, v in d.items() if k != "id_proekta"}
            cur = con.execute(
                "INSERT INTO progony (id_proekta, этап, инструмент, вход_json, "
                "отчёт_md, итоги_json, автор, дата, комментарий, метка) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pid, ИНСТРУМЕНТЫ["simulation"]["этап"], "simulation",
                 json.dumps(вход, ensure_ascii=False), отчёт,
                 json.dumps(итоги, ensure_ascii=False), "РЦК",
                 datetime.now().isoformat(timespec="seconds"), "", ""))
            ответ["id_прогона"] = cur.lastrowid
    return jsonify(ответ)


def _ээ_результат_конечен(r):
    """Фикс У-3: nan/inf в итоговых суммах (переполнение входа, напр. 1e308×1e308)
    не должен попадать в отчёт и снапшот. Возвращает имя плохого ключа или None."""
    for k in ("ээ", "ээ_пот", "высвоб", "налоги", "ээ_запг"):
        v = r.get(k)
        if v is not None and not (isinstance(v, (int, float)) and math.isfinite(v)):
            return k
    return None


def _ээ_ошибка_нечисла(k):
    return [f"результат расчёта («{k}») — не конечное число (nan/inf): "
            "проверьте масштаб входных данных (цена, объём, фонд времени)"]


# --- ЭЭ-калькулятор (спека № 2, контур: концевой серийный поток) ---
@app.route("/api/ee_raschet", methods=["POST"])
def api_ee_raschet():
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке № 2")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом по спеке № 2"]}), 400
    errs = ee_kalk.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs})
    try:
        r = ee_kalk.raschet(d)
        report = ee_kalk.otchyot(d, r)
    except Exception as e:
        return jsonify({"ok": False, "errors": [f"Ядро ЭЭ не смогло обработать данные: {e}"]})
    плохое = _ээ_результат_конечен(r)
    if плохое:
        return jsonify({"ok": False, "errors": _ээ_ошибка_нечисла(плохое)}), 400
    out = {"ok": True, "report_md": report, "result_html": md_to_html(report),
           "flow_name": d.get("предприятие") or "предприятие",
           "domerit_top3": (r.get("домерить") or [])[:3],
           "предупр": r.get("предупр") or []}
    if "ээ" in r:
        out["эе"] = {"реальный": ee_kalk.rub(r["ээ"]),
                     "потенциальный": ee_kalk.rub(r["ээ_пот"]),
                     "высвобождение": ee_kalk.rub(r["высвоб"]),
                     "отложенный_запасы": ee_kalk.rub(r.get("ээ_запг") or 0),
                     "налоги": ee_kalk.rub(r["налоги"])}
        # Э1-Б: сырые числа для слоёв экрана (дельта итога, водопад) —
        # клиент не парсит отформатированные строки
        out["эе_raw"] = {"реальный": r["ээ"], "потенциальный": r["ээ_пот"],
                         "высвобождение": r["высвоб"],
                         "отложенный_запасы": r.get("ээ_запг") or 0,
                         "налоги": r["налоги"]}
        if r.get("факторы"):
            out["факторы"] = [{"имя": и, "зн": round(з, 2)} for и, з in r["факторы"]]
            out["сверка"] = {"сумма": round(r["сверка"]["сумма"], 2),
                             "расх": round(r["сверка"]["расх"], 2),
                             "сходится": abs(r["сверка"]["расх"]) <= 0.01}
    return jsonify(out)


@app.route("/api/ee_demo/<case>")
def api_ee_demo(case):
    """Демо-наборы ЭЭ (экзаменационные JSON) — читаются с диска при каждом запросе."""
    path = EE_DEMO.get(case)
    if path is None:
        return jsonify({"ok": False, "errors": [f"неизвестный демо-кейс «{case}»"]}), 404
    try:
        return jsonify(json.loads(path.read_text(encoding="utf-8")))
    except OSError as e:
        return jsonify({"ok": False,
                        "errors": [f"Не удалось прочитать демо-файл: {e}"]}), 500


@app.route("/api/ee_export_fck", methods=["POST"])
def api_ee_export_fck():
    """Экспорт справки ФЦК (форма 1.4, xlsm) из данных ЭЭ-калькулятора.
    Файл генерируется на лету и отдаётся на скачивание; в историю/БД
    прогонов НЕ пишется (скачивание — не снапшот)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом по спеке № 2")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False,
                        "errors": ["тело запроса должно быть JSON-объектом по спеке № 2"]}), 400
    errs = ee_kalk.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        байты, предупр = ee_export.экспортировать_в_bytes(d)
        имя = ee_export.имя_файла(d)
    except ValueError as e:  # ошибки метаданных (напр. формат даты)
        return jsonify({"ok": False, "errors": [str(e)]}), 400
    except Exception as e:
        return jsonify({"ok": False,
                        "errors": [f"Не удалось сформировать справку ФЦК: {e}"]}), 500
    from urllib.parse import quote
    return Response(
        байты,
        mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(имя)})


@app.route("/download", methods=["POST"])
def download():
    report = request.form.get("report_md", "")
    name = request.form.get("flow_name", "поток")
    safe = re.sub(r"[^\wа-яА-ЯёЁ -]", "", name).strip().replace(" ", "_") or "отчёт"
    return Response(
        report.encode("utf-8"),
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''"
                                        f"{__import__('urllib.parse', fromlist=['quote']).quote('отчёт_' + safe + '.md')}"},
    )


# === Слой данных (Прогон 4): проекты и прогоны, SQLite stdlib, без ORM ===
# Доктрина: прогон = immutable snapshot (вход + отчёт + итоги + автор + дата).
# Перезаписи нет: API не содержит UPDATE/DELETE для прогонов.
DB_PATH = Path(__file__).resolve().parent / "agent_ceh.db"

СХЕМА_SQL = """
CREATE TABLE IF NOT EXISTS proekty (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  название TEXT NOT NULL,
  предприятие TEXT NOT NULL DEFAULT '',
  поток TEXT NOT NULL DEFAULT '',
  создан TEXT NOT NULL,
  комментарий TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS progony (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  id_proekta INTEGER NOT NULL REFERENCES proekty(id),
  этап INTEGER NOT NULL,
  инструмент TEXT NOT NULL,
  вход_json TEXT NOT NULL,
  отчёт_md TEXT NOT NULL DEFAULT '',
  итоги_json TEXT NOT NULL,
  автор TEXT NOT NULL DEFAULT 'РЦК',
  дата TEXT NOT NULL,
  комментарий TEXT NOT NULL DEFAULT '',
  метка TEXT NOT NULL DEFAULT ''
);
-- LLM-слой (Спека № 4, Л4.1): кэш ответов и учёт расхода. Дублирует
-- llm_sloy._СХЕМА_LLM; держать синхронно. Создание — миграция при старте,
-- локальная БД на прод не копируется (volume + seed, см. entrypoint.sh).
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

# Реестр инструментов слоя данных. Новый инструмент волн 2–3 регистрируется
# добавлением записи сюда + ветки в sчитать_itogi() и sravnit().
ИНСТРУМЕНТЫ = {
    "otbor": {"этап": 0, "название": "Отбор предприятия (МР-15-2026)"},
    "otbor_potok": {"этап": 0, "название": "Выбор пилотного потока (МР-15-2026)"},
    "akt": {"этап": 0, "название": "Акт начала мероприятий"},
    "ord": {"этап": 1, "название": "Пакет ОРД"},
    "soglashenie": {"этап": 1, "название": "Соглашение о сотрудничестве"},
    "smart": {"этап": 1, "название": "Цели SMART"},
    "uzkie_mesta": {"этап": 2, "название": "Поиск узкого места"},
    "vsm": {"этап": 2, "название": "Карта потока (КПСЦ)"},
    "potok_calc": {"этап": 2, "название": "Калькулятор показателей потока"},
    "oee": {"этап": 2, "название": "OEE-калькулятор"},
    "ee": {"этап": 3, "название": "ЭЭ-калькулятор"},
    "meropriyatiya": {"этап": 3, "название": "План мероприятий (генератор)"},
    "simulation": {"этап": 3, "название": "Симулятор потока (ДСС)"},
    "zamer": {"этап": 3, "название": "Цифровой замер (готовность к цифре)"},
    "protokol": {"этап": 5, "название": "Протокол закрытия"},
    "preza": {"этап": 7, "название": "Презентация (защита проекта)"},
}


def db():
    # Фикс У-4: sqlite3.connect на несуществующем пути молча создаёт пустую БД —
    # сервис «работал» на пустышке после удаления файла. Теперь — честный отказ,
    # который верхний хендлер sqlite3.Error отдаёт как JSON 503.
    if not DB_PATH.exists():
        raise sqlite3.OperationalError(
            f"файл базы данных «{DB_PATH.name}» не найден по пути {DB_PATH} — "
            "сервис НЕ создаёт пустую базу на месте удалённой; восстановите файл "
            "из резервной копии и перезапустите сервис")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    """Миграция схемы при старте: CREATE IF NOT EXISTS.
    Фикс У-4: при старте — integrity_check существующей БД; битая БД = понятный
    отказ запуска с диагнозом в лог, а не молчаливая работа на обломках."""
    if DB_PATH.exists():
        con = sqlite3.connect(DB_PATH)
        try:
            verdict = con.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.Error as e:
            con.close()
            sys.exit(f"СТОП: файл БД {DB_PATH} не читается ({e}).\n"
                     "Восстановите agent_ceh.db из резервной копии — "
                     "сервис на битой базе не поднимается.")
        if verdict != "ok":
            con.close()
            sys.exit(f"СТОП: integrity_check БД {DB_PATH}: {verdict}.\n"
                     "База повреждена — восстановите agent_ceh.db из резервной "
                     "копии; сервис на битой базе не поднимается.")
        con.close()
    with db() as con:
        con.executescript(СХЕМА_SQL)


init_db()


def sчитать_itogi(инструмент, вход):
    """Пересчитать вход штатным ядром и вернуть (ошибки, отчёт_md, итоги).
    Итоги — компактные ключевые числа прогона (см. КОНТРАКТ_данных.md)."""
    if инструмент == "uzkie_mesta":
        errs = validirovat(вход) or uzkie_mesta.proverit_vhod(вход)
        if errs:
            return errs, None, None
        try:
            r = uzkie_mesta.razbor(вход)
            отчёт = uzkie_mesta.otchyot(вход, r)
        except Exception as e:
            return [f"Ядро не смогло обработать данные: {e}"], None, None
        glavnoe = r.get("главное")
        итоги = {
            "главное_ум": glavnoe["имя"] if glavnoe else None,
            "подтверждено": bool(glavnoe and glavnoe["сошлось"]),
            "доли_впп": [[имя, round(сек, 2), round(доля, 2)]
                         for имя, сек, доля in r.get("доли_впп", [])],
            "ранжирование": [имя for имя, _ in r.get("ранжирование", [])],
            "производительность_т_ч": {
                op["имя"]: op["производительность_т_ч"]
                for op in вход.get("операции", [])
                if op.get("имя") and isinstance(op.get("производительность_т_ч"), (int, float))},
            "операции": [op["имя"] for op in вход.get("операции", []) if op.get("имя")],
            # расширение v1.1 (фикс Н4/Н5): контекст потока и детекторы кандидатов
            "поток": вход.get("поток") or None,
            "детекторы": {имя: list(к["детекторы"])
                          for имя, к in (r.get("кандидаты") or {}).items()},
        }
        return [], отчёт, итоги
    if инструмент == "ee":
        errs = ee_kalk.validirovat(вход)
        if errs:
            return errs, None, None
        try:
            r = ee_kalk.raschet(вход)
            отчёт = ee_kalk.otchyot(вход, r)
        except Exception as e:
            return [f"Ядро ЭЭ не смогло обработать данные: {e}"], None, None
        плохое = _ээ_результат_конечен(r)
        if плохое:
            return _ээ_ошибка_нечисла(плохое), None, None
        итоги = {"предприятие": вход.get("предприятие") or None,
                 "поток": вход.get("поток") or None}
        for k in ("ээ", "ээ_пот", "высвоб", "налоги", "ээ_запг"):
            итоги[k] = round(r[k], 2) if k in r else None
        return [], отчёт, итоги
    if инструмент == "ord":
        errs = ord_smart.validirovat_ord(вход)
        if errs:
            return errs, None, None
        tmp = ФАЙЛЫ_DIR / f"progon_tmp_{secrets.token_hex(6)}_орд.docx"
        try:
            недомеры = ord_smart.gen_ord_docx(вход, str(tmp))
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return [f"Ядро ОРД не смогло обработать данные: {e}"], None, None
        отчёт = ord_smart.отчёт_ord(вход, недомеры, "файлы/…")
        итоги = ord_smart.итоги_ord(вход, недомеры)
        итоги["файл_tmp"] = tmp.name  # переименуется в progon_<id>_орд.docx при вставке
        return [], отчёт, итоги
    if инструмент == "smart":
        errs = ord_smart.validirovat_smart(вход)
        if errs:
            return errs, None, None
        try:
            md, итоги, _ = ord_smart.gen_smart_md(вход)
        except Exception as e:
            return [f"Ядро SMART не смогло обработать данные: {e}"], None, None
        return [], md, итоги
    if инструмент == "protokol":
        if not isinstance(вход, dict):
            return ["вход должен быть JSON-объектом"], None, None
        tmp = ФАЙЛЫ_DIR / f"progon_tmp_{secrets.token_hex(6)}_протокол.docx"
        try:
            итог = protokol_zakrytiya.сгенерировать(вход, str(tmp))
        except ValueError as e:
            tmp.unlink(missing_ok=True)
            return [str(e)], None, None
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return [f"Ядро протокола не смогло обработать данные: {e}"], None, None
        итоги = {"итого_баллов": итог["итого_баллов"], "порог": итог["порог"],
                 "порог_пройден": итог["порог_пройден"],
                 "незаполненных_полей": итог["незаполненных_полей"],
                 "ээ_руб_год": вход.get("ээ_руб_год"),
                 "файл_tmp": tmp.name}
        отчёт = отчёт_protokol_md(вход, итог)
        return [], отчёт, итоги
    if инструмент == "meropriyatiya":
        if not isinstance(вход, dict):
            return ["вход должен быть JSON-объектом"], None, None
        tmp = ФАЙЛЫ_DIR / f"progon_tmp_{secrets.token_hex(6)}_план.docx"
        try:
            прогон = meropriyatiya.сгенерировать(вход)
            tmp.write_bytes(meropriyatiya.build_plan_docx(вход, прогон))
        except ValueError as e:
            tmp.unlink(missing_ok=True)
            return [str(e)], None, None
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return [f"Ядро генератора мероприятий не смогло обработать данные: {e}"], None, None
        итоги = meropriyatiya.итоги_мероприятия(прогон)
        итоги["предприятие"] = вход.get("predpriyatie") or None
        итоги["файл_tmp"] = tmp.name
        отчёт = meropriyatiya.отчёт_meropriyatiya_md(прогон)
        return [], отчёт, итоги
    if инструмент == "akt":
        if not isinstance(вход, dict):
            return ["вход должен быть JSON-объектом"], None, None
        tmp = ФАЙЛЫ_DIR / f"progon_tmp_{secrets.token_hex(6)}_акт.docx"
        try:
            итог = dokumenty_fck.build_akt(вход, str(tmp))
        except ValueError as e:
            tmp.unlink(missing_ok=True)
            return [str(e)], None, None
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return [f"Ядро акта не смогло обработать данные: {e}"], None, None
        итоги = dokumenty_fck.итоги_akt(вход, итог)
        итоги["файл_tmp"] = tmp.name
        отчёт = dokumenty_fck.отчёт_akt_md(вход, итог)
        return [], отчёт, итоги
    if инструмент == "soglashenie":
        if not isinstance(вход, dict):
            return ["вход должен быть JSON-объектом"], None, None
        tmp = ФАЙЛЫ_DIR / f"progon_tmp_{secrets.token_hex(6)}_соглашение.docx"
        try:
            итог = dokumenty_fck.build_soglashenie(вход, str(tmp))
        except ValueError as e:
            tmp.unlink(missing_ok=True)
            return [str(e)], None, None
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return [f"Ядро соглашения не смогло обработать данные: {e}"], None, None
        итоги = dokumenty_fck.итоги_soglashenie(вход, итог)
        итоги["файл_tmp"] = tmp.name
        отчёт = dokumenty_fck.отчёт_soglashenie_md(вход, итог)
        return [], отчёт, итоги
    if инструмент == "vsm":
        errs = validirovat(вход)
        if errs:
            return errs, None, None
        try:
            _svg, итоги = vsm_karta.строить_svg(вход, glavnoe=вход.get("glavnoe"))
        except ValueError as e:
            return [str(e)], None, None
        except Exception as e:
            return [f"Ядро КПСЦ не смогло построить карту: {e}"], None, None
        # SVG в БД не храним (КПСЦ_интеграция.md §3): карта идемпотентно
        # перестраивается из вход_json; в итогах — только компактные числа.
        отчёт = отчёт_vsm_md(вход, итоги)
        return [], отчёт, итоги
    if инструмент == "otbor":
        errs = otbor.validirovat(вход)
        if errs:
            return errs, None, None
        try:
            r = otbor.raschet(вход)
        except Exception as e:
            return [f"Ядро отбора не смогло обработать данные: {e}"], None, None
        ч = r["чеклист"]
        итоги = {"предприятие": r["предприятие"], "трек": r["трек"],
                 "баллы": ч["баллы"], "максимум": ч["максимум"],
                 "порог": r["порог"], "порог_пройден": r["порог_пройден"],
                 "отсекающие_сработавшие": r["отсекающие_сработавшие"],
                 "формальная_пройдена": r["формальная"]["прошла"],
                 "вердикт": r["вердикт"], "вердикт_код": r["вердикт_код"],
                 "по_разделам": {x["раздел"]: x["баллы"]
                                 for x in ч["по_разделам"]}}
        return [], r["скоринг_карта_md"], итоги
    if инструмент == "otbor_potok":
        errs = otbor_potok.validirovat(вход)
        if errs:
            return errs, None, None
        try:
            r = otbor_potok.raschet(вход)
        except Exception as e:
            return [f"Ядро выбора потока не смогло обработать данные: {e}"], None, None
        итоги = {"предприятие": r["предприятие"],
                 "кандидатов": r["кандидатов"], "допущено": r["допущено"],
                 "рекомендованный": r["рекомендованный"],
                 "вердикт": r["вердикт"],
                 "кандидаты": {к["название"]: {"итог": к["итог"],
                                               "критерии": к["баллы_критерии"],
                                               "признаки": к["баллы_признаки"],
                                               "дисквалифицирован": к["дисквалифицирован"]}
                               for к in r["кандидаты"]}}
        return [], r["скоринг_карта_md"], итоги
    if инструмент == "potok_calc":
        errs = pokazateli_potoka.validirovat(вход)
        if errs:
            return errs, None, None
        try:
            r = pokazateli_potoka.raschet(вход)
            отчёт = pokazateli_potoka.otchyot(вход, r)
        except Exception as e:
            return [f"Ядро показателей потока не смогло обработать данные: {e}"], None, None
        return [], отчёт, pokazateli_potoka.itogi(вход, r)
    if инструмент == "oee":
        errs = oee_kalkulator.validirovat(вход)
        if errs:
            return errs, None, None
        try:
            r = oee_kalkulator.raschet(вход)
            отчёт = oee_kalkulator.otchyot(вход, r)
        except Exception as e:
            return [f"Ядро OEE-калькулятора не смогло обработать данные: {e}"], None, None
        return [], отчёт, oee_kalkulator.itogi(вход, r)
    if инструмент == "zamer":
        errs = cifrovoy_zamer.validirovat(вход)
        if errs:
            return errs, None, None
        try:
            r = cifrovoy_zamer.raschet(вход)
            отчёт = cifrovoy_zamer.отчёт_zamer_md(вход, r)
            итоги = cifrovoy_zamer.итоги_zamer(вход, r)
        except Exception as e:
            return [f"Ядро «Цифрового замера» не смогло обработать данные: {e}"], None, None
        return [], отчёт, итоги
    if инструмент == "simulation":
        errs = simulyator.validirovat(вход)
        if errs:
            return errs, None, None
        try:
            r = simulyator.оценка(вход)
            отчёт = simulyator.отчёт(вход, r)
        except Exception as e:
            return [f"Ядро симулятора потока не смогло обработать данные: {e}"], None, None
        return [], отчёт, simulyator.итоги(вход, r)
    if инструмент == "preza":
        # Снапшот сборки защиты (Спека П1, п. 3.1): вход — параметры сборки
        # (слайды/тема/титул/лог), принимается как есть — чисел для пересчёта
        # ядром здесь нет, источник чисел — прогоны, на которые ссылается сборка.
        if not isinstance(вход, dict):
            return ["вход должен быть JSON-объектом"], None, None
        слайды = вход.get("слайды")
        лог = вход.get("лог_сборки") or []
        итоги = {"слайдов": len(слайды) if isinstance(слайды, list) else 0,
                 "тема": вход.get("тема") or "бумага",
                 "пропущено": len(лог)}
        L = ["# Презентация (защита проекта)", ""]
        титул = вход.get("титул") or {}
        строка = " · ".join(str(x) for x in
                            (титул.get("предприятие"), титул.get("поток"),
                             титул.get("автор")) if x)
        if строка:
            L.append(f"**{строка}**")
            L.append("")
        L.append(f"Слайдов: {итоги['слайдов']} · тема «{итоги['тема']}» · "
                 f"пропущено: {итоги['пропущено']}")
        for строка_лога in лог:
            L.append(f"- {строка_лога}")
        return [], "\n".join(L), итоги
    return [f"неизвестный инструмент «{инструмент}»"], None, None


def отчёт_vsm_md(вход, итоги):
    """Короткая сводка прогона КПСЦ (для progony.отчёт_md; SVG файлом не пишем)."""
    L = [f"# Карта потока создания ценности (КПСЦ) · {итоги['поток']}", ""]
    L.append(f"**Дата:** {итоги['дата']} · **операций:** {итоги['операций']}")
    L.append("")
    L.append(f"- ΣVA (ΣТц) = {итоги['сум_тц_сек']} сек")
    if итоги.get("сум_nva_сек") is not None:
        L.append(f"- ΣNVA = {итоги['сум_nva_сек']} сек")
    if итоги.get("впп_сек") is not None:
        L.append(f"- ВПП = {итоги['впп_сек']} сек")
    if итоги.get("доля_ценности_пкт") is not None:
        L.append(f"- Доля ценности = {str(итоги['доля_ценности_пкт']).replace('.', ',')} %")
    г = итоги.get("главное_узкое_место")
    L.append(f"- Главное узкое место: «{г}» (подсвечено на карте)" if г
             else "- Подсветка узкого места не задана (расчёт УМ не выполнялся "
                  "или главное УМ не выявлено)")
    пробелы = итоги.get("пробелы") or []
    L.append("")
    if пробелы:
        L.append("> СТАТУС: С ПРОБЕЛАМИ — домерить: " + "; ".join(пробелы) + ".")
    else:
        L.append("> СТАТУС: ПОЛНЫЕ ДАННЫЕ.")
    L.append("")
    L.append("SVG-карта в снапшот не входит: перестраивается из входа кнопкой "
             "«Построить карту» (идемпотентно).")
    return "\n".join(L)


def отчёт_protokol_md(вход, итог):
    """Короткая сводка прогона протокола (для progony.отчёт_md)."""
    L = ["# Протокол выполнения мероприятий (протокол закрытия)", ""]
    L.append(f"**Предприятие:** {вход.get('предприятие') or '___'}  ")
    согл = вход.get("соглашение") or {}
    L.append(f"**Соглашение:** № {согл.get('номер') or '___'} от {согл.get('дата') or '___'}  ")
    L.append(f"**Поток:** {вход.get('поток_ключевого_продукта') or '___'}")
    L.append("")
    if итог["итого_баллов"] is None:
        L.append("Итоговая оценка не сформирована — заполнены не все направления чек-листа.")
    else:
        вердикт = ("порог пройден — целевой уровень развития производственной "
                   "системы достигнут" if итог["порог_пройден"]
                   else "порог НЕ пройден — целевой уровень не достигнут")
        L.append(f"Итог чек-листа: **{итог['итого_баллов']} / {итог['порог']}** баллов — {вердикт}.")
    ээ = вход.get("ээ_руб_год")
    if ээ is not None:
        L.append(f"Экономический эффект: **{protokol_zakrytiya.fmt_ээ(ээ)}**")
        if _конечное(ээ) and ээ <= 0:
            L.append("> ⚠ ЭЭ ≤ 0 — проверьте входные данные: эффект отсутствует "
                     "или отрицателен (фикс У-9).")
    L.append("")
    L.append(f"Полей «домерить»: {итог['незаполненных_полей']}.")
    L.append("> Формулировка нацпроекта в шапке — редакция 2022 г.; для проектов "
             "2025+ правится вручную в docx.")
    return "\n".join(L)


@app.route("/api/proekty", methods=["GET", "POST"])
def api_proekty():
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        название = (d.get("название") or "").strip()
        if not название:
            return jsonify({"ok": False, "errors": ["укажите название проекта"]}), 400
        with db() as con:
            cur = con.execute(
                "INSERT INTO proekty (название, предприятие, поток, создан, комментарий) "
                "VALUES (?,?,?,?,?)",
                (название, (d.get("предприятие") or "").strip(),
                 (d.get("поток") or "").strip(),
                 datetime.now().isoformat(timespec="seconds"),
                 (d.get("комментарий") or "").strip()))
            pid = cur.lastrowid
        return jsonify({"ok": True, "id": pid})
    with db() as con:
        rows = con.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM progony g WHERE g.id_proekta = p.id) "
            "AS прогонов FROM proekty p ORDER BY p.id DESC").fetchall()
    return jsonify({"ok": True, "proekty": [dict(r) for r in rows]})


@app.route("/api/proekty/<int:pid>")
def api_proekt(pid):
    with db() as con:
        p = con.execute("SELECT * FROM proekty WHERE id = ?", (pid,)).fetchone()
        if p is None:
            return jsonify({"ok": False, "errors": [f"проект № {pid} не найден"]}), 404
        rows = con.execute(
            "SELECT id, этап, инструмент, итоги_json, автор, дата, комментарий, метка "
            "FROM progony WHERE id_proekta = ? ORDER BY id", (pid,)).fetchall()
    progony = []
    for r in rows:
        d = dict(r)
        d["итоги"] = json.loads(d.pop("итоги_json"))
        progony.append(d)
    return jsonify({"ok": True, "proekt": dict(p), "progony": progony})


def _развернуть(значение):
    """dict вида {"название": ...} разворачивается в строку; прочее — как есть."""
    if isinstance(значение, dict):
        return значение.get("название") or значение.get("name")
    return значение


def _контекст_входа(инструмент, вход):
    """(предприятие, поток) из входа прогона — для сверки с карточкой проекта
    в точке записи (фикс У-6). Фикс Д3.1-А1: предприятие/поток dict (smart)
    разворачиваются всегда, иначе _несовпадает зовёт .strip() на dict → 500."""
    if инструмент == "ord":
        return _развернуть(вход.get("предприятие")), _развернуть(вход.get("поток"))
    if инструмент == "protokol":
        return _развернуть(вход.get("предприятие")), _развернуть(вход.get("поток_ключевого_продукта"))
    if инструмент == "meropriyatiya":
        # Д3.2-Б9: «участок» генератора — название участка/операции УМ,
        # а не пилотный поток карточки проекта; сверять его как поток —
        # ложная пометка «контекст_расходится» на нормальных прогонах.
        return _развернуть(вход.get("predpriyatie")), None
    return _развернуть(вход.get("предприятие")), _развернуть(вход.get("поток"))


def _несовпадает(а, б):
    """Конфликт контекста: оба значения непустые и разные (без регистра/пробелов).
    Нестроковые значения безопасно приводятся (фикс Д3.1-А1)."""
    а = "" if а is None else (а if isinstance(а, str) else str(а))
    б = "" if б is None else (б if isinstance(б, str) else str(б))
    а, б = а.strip().lower(), б.strip().lower()
    return bool(а and б and а != б)


@app.route("/api/progony", methods=["POST"])
def api_progon_save():
    """Сохранить прогон: сервер пересчитывает вход ядром (единая точка истины),
    складывает immutable snapshot. Отчёт и итоги от клиента не принимаются."""
    d, err = прочитать_json_тело("тело: {id_proekta, инструмент, вход, метка?, автор?, комментарий?}")
    if err:
        return jsonify(err[0]), err[1]
    d = d or {}
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    pid = d.get("id_proekta")
    инструмент = d.get("инструмент")
    вход = d.get("вход")
    # Фикс У-5: type() is int, не isinstance — bool не должен проходить как id
    if type(pid) is not int or pid <= 0:
        return jsonify({"ok": False, "errors": [
            "поле «id_proekta» должно быть целым числом > 0 (bool недопустим)"]}), 400
    if инструмент not in ИНСТРУМЕНТЫ:
        return jsonify({"ok": False, "errors": [
            f"неизвестный инструмент «{инструмент}»; зарегистрированы: "
            + ", ".join(ИНСТРУМЕНТЫ)]}), 400
    if not isinstance(вход, dict):
        return jsonify({"ok": False, "errors": ["поле «вход» должно быть JSON-объектом "
                                                "по спеке инструмента"]}), 400
    # Фикс У-11: потолок снапшота и таблицы операций — один клиент не раздувает БД
    размер_входа = len(json.dumps(вход, ensure_ascii=False).encode("utf-8"))
    if размер_входа > MAX_SNAPSHOT_BYTES:
        return jsonify({"ok": False, "errors": [
            f"снимок прогона {размер_входа / 1048576:.1f} МБ больше потолка "
            f"{MAX_SNAPSHOT_BYTES // 1048576} МБ — сократите вход (число операций, "
            "длину имён и комментариев)"]}), 400
    if инструмент == "uzkie_mesta" and isinstance(вход.get("операции"), list):
        ops = вход["операции"]
        if len(ops) > MAX_ОПЕРАЦИЙ:
            return jsonify({"ok": False, "errors": [
                f"операций {len(ops)} больше потолка {MAX_ОПЕРАЦИЙ} — "
                "агрегируйте блоки потока"]}), 400
        for i, op in enumerate(ops, 1):
            if isinstance(op, dict) and len(str(op.get("имя") or "")) > MAX_ИМЯ_ОПЕРАЦИИ:
                return jsonify({"ok": False, "errors": [
                    f"строка {i}: имя операции длиннее {MAX_ИМЯ_ОПЕРАЦИИ} символов"]}), 400
    with db() as con:
        pj = con.execute("SELECT предприятие, поток FROM proekty WHERE id = ?",
                         (pid,)).fetchone()
        if pj is None:
            return jsonify({"ok": False, "errors": [f"проект № {pid} не найден"]}), 404
    # Фикс У-6: мягкая серверная сверка контекста в точке записи.
    # Не отказ: снапшот честно помечается «контекст_расходится: true» + предупреждение.
    предупр_контекст = []
    в_пред, в_поток = _контекст_входа(инструмент, вход)
    расх = []
    if _несовпадает(в_пред, pj["предприятие"]):
        расх.append(f"предприятие входа «{в_пред}» ≠ карточки проекта «{pj['предприятие']}»")
    if _несовпадает(в_поток, pj["поток"]):
        расх.append(f"поток входа «{в_поток}» ≠ карточки проекта «{pj['поток']}»")
    if расх:
        предупр_контекст.append(
            "Контекст входа расходится с карточкой проекта: " + "; ".join(расх) +
            ". Прогон сохранён с пометкой «контекст_расходится» — в сравнениях "
            "и подтяжках учитывайте, что данные, возможно, относятся к другому потоку.")
    подтяжка_инфо = None
    if инструмент == "protokol":
        # Фикс Н3: путь immutable-снапшота использует ТУ ЖЕ единую подтяжку,
        # что и путь скачивания /api/protokol (с контекстной сверкой Н4).
        вход = dict(вход)
        ошибки_чек, предупр_чек = применить_чеклист(вход)
        if ошибки_чек:
            return jsonify({"ok": False, "errors": ошибки_чек}), 400
        подт = подтяжка_проекта(pid)
        if вход.get("ээ_руб_год") is None and подт["поля"]["ээ_руб_год"] is not None:
            вход["ээ_руб_год"] = подт["поля"]["ээ_руб_год"]
        # Фикс У-9: неположительный ЭЭ в подписном документе — явное предупреждение
        ээ = вход.get("ээ_руб_год")
        if _конечное(ээ) and ээ <= 0:
            предупр_чек.append(
                f"ЭЭ ≤ 0 ({ээ:,.0f} руб/год) — проверьте входные данные: эффект "
                "отсутствует или отрицателен; документ будет сформирован с пометкой.")
        подтяжка_инфо = {"источники": подт["источники"],
                         "предупреждения": подт["предупреждения"] + предупр_чек}
    errs, отчёт, итоги = sчитать_itogi(инструмент, вход)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    if расх:
        итоги["контекст_расходится"] = True
    метка = d.get("метка") if d.get("метка") in ("до", "после") else ""
    автор = (d.get("автор") or "").strip() or "РЦК"
    with db() as con:
        cur = con.execute(
            "INSERT INTO progony (id_proekta, этап, инструмент, вход_json, отчёт_md, "
            "итоги_json, автор, дата, комментарий, метка) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, ИНСТРУМЕНТЫ[инструмент]["этап"], инструмент,
             json.dumps(вход, ensure_ascii=False), отчёт,
             json.dumps(итоги, ensure_ascii=False), автор,
             datetime.now().isoformat(timespec="seconds"),
             (d.get("комментарий") or "").strip(), метка))
        gid = cur.lastrowid
        # docx-прогоны (ord, protokol): временный файл → progon_<id>_*.docx,
        # имя файла фиксируется в итоги_json (снапшот immutable дальше)
        tmp_name = итоги.pop("файл_tmp", None)
        if tmp_name:
            суффикс = {"ord": "орд", "protokol": "протокол",
                       "akt": "акт", "soglashenie": "соглашение",
                       "meropriyatiya": "план"}[инструмент]
            целевое_имя = f"progon_{gid}_{суффикс}.docx"
            (ФАЙЛЫ_DIR / tmp_name).rename(ФАЙЛЫ_DIR / целевое_имя)
            итоги["файл"] = f"файлы/{целевое_имя}"
            con.execute("UPDATE progony SET итоги_json = ? WHERE id = ?",
                        (json.dumps(итоги, ensure_ascii=False), gid))
    return jsonify({"ok": True, "id": gid, "итоги": итоги, "отчёт_md": отчёт,
                    **({"предупреждения": предупр_контекст} if предупр_контекст else {}),
                    **({"подтяжка": подтяжка_инфо} if подтяжка_инфо else {})})


@app.route("/api/progony/<int:gid>")
def api_progon(gid):
    """Полный снапшот прогона: вход + отчёт + итоги (для загрузки формы в UI)."""
    with db() as con:
        r = con.execute("SELECT * FROM progony WHERE id = ?", (gid,)).fetchone()
    if r is None:
        return jsonify({"ok": False, "errors": [f"прогон № {gid} не найден"]}), 404
    d = dict(r)
    d["вход"] = json.loads(d.pop("вход_json"))
    d["итоги"] = json.loads(d.pop("итоги_json"))
    return jsonify({"ok": True, "progon": d})


# --- Сравнение прогонов «до/после» ---
def _pct_delta(a, b):
    """Относительная дельта в %, честно None при нулевой базе."""
    if a in (None, 0) or b is None:
        return None
    return round((b - a) / abs(a) * 100, 1)


def _экземпляры(имена):
    """Разметить дубли имён порядковым индексом: «фасовка», «перемещение»×2 →
    [('фасовка', 1), ('перемещение', 1), ('перемещение', 2)] (фикс Н5)."""
    счёт, out = {}, []
    for имя in имена:
        счёт[имя] = счёт.get(имя, 0) + 1
        out.append((имя, счёт[имя]))
    return out


def _ключ(имя, экз):
    return имя if экз == 1 else f"{имя} #{экз}"


def _группа_экз(пары):
    """dict имя -> {экз: значение} для списка пар (имя, значение)."""
    счёт, out = {}, {}
    for имя, зн in пары:
        счёт[имя] = счёт.get(имя, 0) + 1
        out.setdefault(имя, {})[счёт[имя]] = зн
    return out


def sravnit_uzkie(a, b):
    """Дельта двух итогов «Поиска узкого места». a=до, b=после.
    Сопоставление операций — по паре (имя, порядковый № экземпляра), чтобы
    дубли имён не схлопывались (фикс Н5); расхождение состава → частичное."""
    экз_a = _экземпляры(a["операции"])
    экз_b = _экземпляры(b["операции"])
    ключи_a = {_ключ(и, e): (и, e) for и, e in экз_a}
    ключи_b = {_ключ(и, e): (и, e) for и, e in экз_b}
    общие = [к for к in ключи_a if к in ключи_b]
    только_до = [к for к in ключи_a if к not in ключи_b]
    только_после = [к for к in ключи_b if к not in ключи_a]
    дубли = sorted({и for и, e in экз_a + экз_b if e > 1})

    доли_a = _группа_экз([(имя, доля) for имя, _, доля in a["доли_впп"]])
    доли_b = _группа_экз([(имя, доля) for имя, _, доля in b["доли_впп"]])
    доли = {}
    for к in общие:
        имя, экз = ключи_a[к]
        va, vb = доли_a.get(имя, {}).get(экз), доли_b.get(имя, {}).get(экз)
        if va is not None and vb is not None:
            доли[к] = {"до": va, "после": vb, "дельта_пп": round(vb - va, 2)}

    произв = {}
    for к in общие:
        имя, экз = ключи_a[к]
        pa, pb = a["производительность_т_ч"].get(имя), b["производительность_т_ч"].get(имя)
        if pa is not None and pb is not None:
            произв[к] = {"до": pa, "после": pb, "дельта": round(pb - pa, 4),
                         "дельта_пкт": _pct_delta(pa, pb)}

    поз_a = _группа_экз([(имя, i + 1) for i, имя in enumerate(a["ранжирование"])])
    поз_b = _группа_экз([(имя, i + 1) for i, имя in enumerate(b["ранжирование"])])
    ранж = {}
    for к in общие:
        имя, экз = ключи_a[к]
        va, vb = поз_a.get(имя, {}).get(экз), поз_b.get(имя, {}).get(экз)
        if va is not None and vb is not None:
            ранж[к] = {"до": va, "после": vb,
                       "сдвиг": va - vb}  # >0 = поднялось в рейтинге УМ

    # Блок «почему УМ переехал/не переехал» (фикс Н5): детекторы главного УМ
    # в обоих прогонах. Поле «детекторы» появилось в итогах с ред. v1.1 —
    # у старых прогонов его нет, об этом честно говорим.
    дет_a, дет_b = a.get("детекторы") or {}, b.get("детекторы") or {}
    ум_a, ум_b = a["главное_ум"], b["главное_ум"]
    почему = {"переехало": ум_a != ум_b, "детекторы_доступны": bool(дет_a or дет_b)}
    if дет_a or дет_b:
        почему["главное_до"] = {"имя": ум_a,
                                "детекторы_до": дет_a.get(ум_a, []),
                                "детекторы_после": дет_b.get(ум_a, [])}
        почему["главное_после"] = {"имя": ум_b,
                                   "детекторы_до": дет_a.get(ум_b, []),
                                   "детекторы_после": дет_b.get(ум_b, [])}
    пояснение = None
    if дубли:
        пояснение = ("В составе потока есть операции с одинаковыми именами ("
                     + ", ".join(f"«{и}»" for и in дубли)
                     + ") — они сопоставлены по имени и порядковому номеру "
                       "экземпляра (#1, #2, …) в таблице.")
    return {"инструмент": "uzkie_mesta",
            "частичное": bool(только_до or только_после or дубли),
            "дубли_имён": дубли, "пояснение": пояснение,
            "только_в_до": только_до, "только_в_после": только_после,
            "главное_ум": {"до": ум_a, "после": ум_b,
                           "изменилось": ум_a != ум_b},
            "почему_ум": почему,
            "доли_впп": доли, "производительность_т_ч": произв, "ранжирование": ранж}


def sravnit_ee(a, b):
    """Дельта двух итогов ЭЭ-калькулятора по ключевым суммам."""
    числа = {}
    for k, подпись in (("ээ", "Реальный ЭЭ, руб/год"),
                       ("ээ_пот", "Потенциальный ЭЭ, руб/год"),
                       ("высвоб", "Высвобождение ДС, руб"),
                       ("ээ_запг", "Отложенный эффект запасов, руб/год"),
                       ("налоги", "Налоги за 3 года, руб")):
        va, vb = a.get(k), b.get(k)
        if va is not None and vb is not None:
            числа[k] = {"подпись": подпись, "до": va, "после": vb,
                        "дельта": round(vb - va, 2), "дельта_пкт": _pct_delta(va, vb)}
    контекст_разный = (a.get("предприятие") != b.get("предприятие")
                       or a.get("поток") != b.get("поток"))
    return {"инструмент": "ee", "частичное": контекст_разный,
            "контекст_разный": контекст_разный,
            "предприятие": {"до": a.get("предприятие"), "после": b.get("предприятие")},
            "поток": {"до": a.get("поток"), "после": b.get("поток")},
            "числа": числа}


def sravnit_smart(a, b):
    """Дельта двух прогонов «Цели SMART»: уточнение целей (МУ-65 п. 4.2.4).
    Сопоставление целей — по наименованию; расхождение состава → частичное."""
    цели_a = {ц.get("наименование"): ц for ц in a.get("цели", []) if ц.get("наименование")}
    цели_b = {ц.get("наименование"): ц for ц in b.get("цели", []) if ц.get("наименование")}
    общие = [н for н in цели_a if н in цели_b]
    только_до = [н for н in цели_a if н not in цели_b]
    только_после = [н for н in цели_b if н not in цели_a]
    цели = {}
    for н in общие:
        цa, цb = цели_a[н], цели_b[н]
        зап = {}
        for k in ("текущий", "целевой", "идеальный", "дельта_пкт"):
            va, vb = цa.get(k), цb.get(k)
            if va is not None or vb is not None:
                зап[k] = {"до": va, "после": vb,
                          "дельта": (round(vb - va, 4)
                                    if isinstance(va, (int, float)) and isinstance(vb, (int, float))
                                    else None)}
        зап["измеримо"] = {"до": цa.get("измеримо"), "после": цb.get("измеримо")}
        цели[н] = зап
    return {"инструмент": "smart", "частичное": bool(только_до or только_после),
            "только_в_до": только_до, "только_в_после": только_после,
            "рамка": {"до": a.get("рамка"), "после": b.get("рамка")},
            "целей": {"до": a.get("целей"), "после": b.get("целей")},
            "цели": цели}


def sravnit_otbor(a, b):
    """Дельта двух прогонов отбора: вердикт, баллы (в т.ч. по разделам),
    сработавшие отсекающие. Сопоставимы прогоны одного трека одного
    предприятия; расхождение контекста → частичное."""
    контекст_разный = (a.get("предприятие") != b.get("предприятие")
                       or a.get("трек") != b.get("трек"))
    разделы = {}
    for код in sorted(set(a.get("по_разделам") or {}) | set(b.get("по_разделам") or {})):
        va, vb = (a.get("по_разделам") or {}).get(код), (b.get("по_разделам") or {}).get(код)
        if va is not None and vb is not None:
            разделы[код] = {"до": va, "после": vb, "дельта": vb - va}
    return {"инструмент": "otbor", "частичное": контекст_разный,
            "контекст_разный": контекст_разный,
            "предприятие": {"до": a.get("предприятие"), "после": b.get("предприятие")},
            "трек": {"до": a.get("трек"), "после": b.get("трек")},
            "вердикт": {"до": a.get("вердикт"), "после": b.get("вердикт"),
                        "изменился": a.get("вердикт_код") != b.get("вердикт_код")},
            "баллы": {"до": a.get("баллы"), "после": b.get("баллы"),
                      "дельта": ((b.get("баллы") - a.get("баллы"))
                                 if isinstance(a.get("баллы"), int)
                                 and isinstance(b.get("баллы"), int) else None),
                      "порог": a.get("порог")},
            "отсекающие": {"до": a.get("отсекающие_сработавшие") or [],
                           "после": b.get("отсекающие_сработавшие") or []},
            "по_разделам": разделы}


def sravnit_potok(a, b):
    """Дельта двух прогонов выбора пилотного потока: рекомендация и итоги
    кандидатов (сопоставление по названию потока; расхождение состава или
    предприятия → частичное)."""
    ка = a.get("кандидаты") or {}
    кб = b.get("кандидаты") or {}
    общие = [н for н in ка if н in кб]
    только_до = [н for н in ка if н not in кб]
    только_после = [н for н in кб if н not in ка]
    контекст_разный = a.get("предприятие") != b.get("предприятие")
    итоги = {}
    for н in общие:
        va, vb = ка[н].get("итог"), кб[н].get("итог")
        итоги[н] = {"до": va, "после": vb,
                    "дельта": (vb - va) if isinstance(va, int)
                              and isinstance(vb, int) else None}
    return {"инструмент": "otbor_potok",
            "частичное": bool(только_до or только_после or контекст_разный),
            "контекст_разный": контекст_разный,
            "предприятие": {"до": a.get("предприятие"),
                            "после": b.get("предприятие")},
            "рекомендованный": {"до": a.get("рекомендованный"),
                                "после": b.get("рекомендованный"),
                                "изменился": a.get("рекомендованный")
                                != b.get("рекомендованный")},
            "итоги": итоги,
            "только_в_до": только_до, "только_в_после": только_после}


def sravnit_simulation(a, b):
    """Дельта двух прогонов симулятора «что если» по сохранённым итогам:
    выпуск, ВПП, НЗП, такт — до/после; баннер «УМ переехало», если было.
    Ничего не пересчитывает: только арифметика над итоги_json."""
    числа = {}
    for k, подпись in (("выпуск_шт", "Выпуск за горизонт, шт"),
                       ("впп_мин", "ВПП, мин"),
                       ("нзп_среднее_шт", "НЗП среднее, шт"),
                       ("нзп_макс_шт", "НЗП макс, шт"),
                       ("такт_мин", "Такт, мин/шт")):
        va, vb = a.get(k), b.get(k)
        if va is not None and vb is not None:
            числа[k] = {"подпись": подпись, "до": va, "после": vb,
                        "дельта": round(vb - va, 4), "дельта_пкт": _pct_delta(va, vb)}
    ум_a, ум_b = a.get("узкое_место"), b.get("узкое_место")
    контекст_разный = bool(a.get("поток") and b.get("поток")
                           and a.get("поток") != b.get("поток"))
    return {"инструмент": "simulation", "частичное": контекст_разный,
            "контекст_разный": контекст_разный,
            "поток": {"до": a.get("поток"), "после": b.get("поток")},
            "узкое_место": {"до": ум_a, "после": ум_b,
                            "переехало": ум_a is not None and ум_a != ум_b},
            "числа": числа}


def sravnit(инструмент, a, b):
    if инструмент == "uzkie_mesta":
        return sravnit_uzkie(a, b)
    if инструмент == "ee":
        return sravnit_ee(a, b)
    if инструмент == "smart":
        return sravnit_smart(a, b)
    if инструмент == "otbor":
        return sravnit_otbor(a, b)
    if инструмент == "otbor_potok":
        return sravnit_potok(a, b)
    if инструмент == "simulation":
        return sravnit_simulation(a, b)
    return None  # ord, protokol — сравнение прогонов бессмысленно


def delta_md(инструмент, dlt, g_a, g_b):
    """Человекочитаемый дельта-отчёт (markdown) для UI и выгрузки."""
    ин = ИНСТРУМЕНТЫ[инструмент]["название"]
    L = [f"# Сравнение прогонов «до/после» — {ин}",
         f"- «до»: прогон № {g_a['id']} от {g_a['дата']} "
         f"({g_a['метка'] or 'без метки'}, {g_a['автор']})"
         + (f" — {g_a['комментарий']}" if g_a["комментарий"] else ""),
         f"- «после»: прогон № {g_b['id']} от {g_b['дата']} "
         f"({g_b['метка'] or 'без метки'}, {g_b['автор']})"
         + (f" — {g_b['комментарий']}" if g_b["комментарий"] else "")]
    if dlt["частичное"]:
        L.append("> Сравнение частичное: состав операций/контекст прогонов различается, "
                 "сопоставлены только общие позиции.")
    if dlt.get("пояснение"):
        L.append("> " + dlt["пояснение"])
    if инструмент == "uzkie_mesta":
        g = dlt["главное_ум"]
        стр = f"«{g['до']}» → «{g['после']}»"
        L.append(f"\n## Главное узкое место\n- {стр}" +
                 (" — **переехало**" if g["изменилось"] else " — без изменений"))
        пч = dlt.get("почему_ум") or {}
        if пч:
            L.append("\n## Почему главное УМ " +
                     ("переехало" if пч.get("переехало") else "НЕ переехало"))
            if not пч.get("детекторы_доступны"):
                L.append("- в сохранённых итогах прогонов нет списка сработавших "
                         "детекторов (прогоны записаны до ред. v1.1) — доступна "
                         "только арифметика дельт; для интерпретации пересохраните "
                         "прогоны заново.")
            else:
                for ключ, подпись in (("главное_до", "Главное УМ «до»"),
                                      ("главное_после", "Главное УМ «после»")):
                    бл = пч.get(ключ)
                    if not бл or not бл.get("имя"):
                        continue
                    д_до = ", ".join(бл["детекторы_до"]) or "нет"
                    д_после = ", ".join(бл["детекторы_после"]) or "нет"
                    L.append(f"- {подпись} «{бл['имя']}»: детекторы в прогоне «до» — "
                             f"{д_до}; в прогоне «после» — {д_после}.")
                L.append("- УМ удерживается/теряется кросс-детектором (ранжирование по "
                         "числу сработавших детекторов), а не одной долей ВПП: если доля "
                         "ВПП ушла ниже порога, но детектор темпа (производительность) "
                         "по-прежнему минимален в потоке, операция остаётся главным УМ.")
        if dlt["доли_впп"]:
            L.append("\n## Доли ВПП, п.п.")
            for имя, v in sorted(dlt["доли_впп"].items(),
                                 key=lambda kv: -abs(kv[1]["дельта_пп"])):
                L.append(f"- «{имя}»: {v['до']} % → {v['после']} % "
                         f"(Δ {v['дельта_пп']:+} п.п.)")
        if dlt["производительность_т_ч"]:
            L.append("\n## Производительность, т/ч")
            for имя, v in sorted(dlt["производительность_т_ч"].items(),
                                 key=lambda kv: -abs(kv[1]["дельта"])):
                пкт = f", {v['дельта_пкт']:+} %" if v["дельта_пкт"] is not None else ""
                L.append(f"- «{имя}»: {v['до']} → {v['после']} (Δ {v['дельта']:+}{пкт})")
        if dlt["ранжирование"]:
            L.append("\n## Ранжирование узких мест")
            for имя, v in sorted(dlt["ранжирование"].items(),
                                 key=lambda kv: kv[1]["после"]):
                if v["сдвиг"]:
                    стр = f"{'↑' if v['сдвиг'] > 0 else '↓'}{abs(v['сдвиг'])}"
                else:
                    стр = "без изменений"
                L.append(f"- «{имя}»: {v['до']} → {v['после']} ({стр})")
        if dlt["только_в_до"]:
            L.append("\nОперации только в «до»: " + ", ".join(f"«{x}»" for x in dlt["только_в_до"]))
        if dlt["только_в_после"]:
            L.append("Операции только в «после»: "
                     + ", ".join(f"«{x}»" for x in dlt["только_в_после"]))
    elif инструмент == "smart":
        L.append(f"\n## Состав целей: {dlt['целей']['до']} → {dlt['целей']['после']}")
        if dlt["рамка"]["до"] != dlt["рамка"]["после"]:
            L.append(f"- рамка ПТ изменилась: «{dlt['рамка']['до']}» → «{dlt['рамка']['после']}»")
        if dlt["цели"]:
            L.append("\n## Уточнение целей (МУ-65, п. 4.2.4)")
            for н, v in dlt["цели"].items():
                parts = []
                for k, подпись in (("текущий", "текущий"), ("целевой", "целевой"),
                                   ("дельта_пкт", "Δ, %")):
                    z = v.get(k)
                    if z and z["до"] != z["после"]:
                        parts.append(f"{подпись}: {z['до']} → {z['после']}")
                L.append(f"- «{н}»: " + ("; ".join(parts) if parts else "без изменений"))
        if dlt["только_в_до"]:
            L.append("\nЦели только в «до»: " + ", ".join(f"«{x}»" for x in dlt["только_в_до"]))
        if dlt["только_в_после"]:
            L.append("Цели только в «после»: "
                     + ", ".join(f"«{x}»" for x in dlt["только_в_после"]))
    elif инструмент == "otbor":
        в = dlt["вердикт"]
        L.append(f"\n## Вердикт: «{в['до']}» → «{в['после']}»"
                 + (" — **изменился**" if в["изменился"] else " — без изменений"))
        б = dlt["баллы"]
        if б["дельта"] is not None:
            L.append(f"\n## Сумма баллов: {б['до']} → {б['после']} "
                     f"(Δ {б['дельта']:+}, порог {б['порог']})")
        if dlt["по_разделам"]:
            L.append("\n## Баллы по разделам чек-листа")
            for код, v in dlt["по_разделам"].items():
                if v["дельта"]:
                    L.append(f"- раздел {код}: {v['до']} → {v['после']} "
                             f"(Δ {v['дельта']:+})")
            if not any(v["дельта"] for v in dlt["по_разделам"].values()):
                L.append("- по всем разделам без изменений")
        отс = dlt["отсекающие"]
        if отс["до"] or отс["после"]:
            L.append("\n## Сработавшие отсекающие критерии")
            L.append(f"- «до»: {', '.join(отс['до']) or 'нет'}; "
                     f"«после»: {', '.join(отс['после']) or 'нет'}")
        if dlt["контекст_разный"]:
            L.append("\n> Внимание: предприятие/трек прогонов различаются "
                     f"(«{dlt['предприятие']['до']}/{dlt['трек']['до']}» vs "
                     f"«{dlt['предприятие']['после']}/{dlt['трек']['после']}») — "
                     "дельты считайте ориентировочными.")
    elif инструмент == "otbor_potok":
        р = dlt["рекомендованный"]
        L.append(f"\n## Рекомендованный поток: «{р['до'] or '—'}» → "
                 f"«{р['после'] or '—'}»"
                 + (" — **изменился**" if р["изменился"] else " — без изменений"))
        if dlt["итоги"]:
            L.append("\n## Итоги кандидатов (баллы из 20)")
            for н, v in dlt["итоги"].items():
                if v["дельта"]:
                    L.append(f"- «{н}»: {v['до']} → {v['после']} "
                             f"(Δ {v['дельта']:+})")
            if not any(v["дельта"] for v in dlt["итоги"].values()):
                L.append("- по всем кандидатам без изменений")
        if dlt["только_в_до"]:
            L.append("\nКандидаты только в «до»: "
                     + ", ".join(f"«{x}»" for x in dlt["только_в_до"]))
        if dlt["только_в_после"]:
            L.append("Кандидаты только в «после»: "
                     + ", ".join(f"«{x}»" for x in dlt["только_в_после"]))
        if dlt["контекст_разный"]:
            L.append("\n> Внимание: предприятие прогонов различается "
                     f"(«{dlt['предприятие']['до']}» vs "
                     f"«{dlt['предприятие']['после']}») — дельты считайте "
                     "ориентировочными.")
    elif инструмент == "simulation":
        ум = dlt["узкое_место"]
        if ум.get("переехало"):
            L.append(f"\n## Узкое место переехало: «{ум['до']}» → «{ум['после']}»")
        elif ум.get("до"):
            L.append(f"\n## Узкое место: «{ум['до']}» — без изменений")
        L.append("\n## Ключевые показатели (модельный прогноз, не замер)")
        for k in ("выпуск_шт", "впп_мин", "нзп_среднее_шт", "нзп_макс_шт", "такт_мин"):
            v = dlt["числа"].get(k)
            if not v:
                continue
            пкт = f", {v['дельта_пкт']:+} %" if v["дельта_пкт"] is not None else ""
            L.append(f"- {v['подпись']}: {v['до']} → {v['после']} "
                     f"(Δ {v['дельта']:+}{пкт})")
        if dlt["контекст_разный"]:
            L.append("\n> Внимание: потоки прогонов различаются "
                     f"(«{dlt['поток']['до']}» vs «{dlt['поток']['после']}») — "
                     "дельты считайте ориентировочными.")
    else:  # ee
        L.append("\n## Ключевые суммы")
        for k in ("ээ", "ээ_пот", "высвоб", "налоги"):
            v = dlt["числа"].get(k)
            if not v:
                continue
            пкт = f", {v['дельта_пкт']:+} %" if v["дельта_пкт"] is not None else ""
            L.append(f"- {v['подпись']}: {v['до']} → {v['после']} (Δ {v['дельта']:+}{пкт})")
        if dlt["контекст_разный"]:
            L.append("\n> Внимание: предприятие/поток прогонов различаются "
                     f"(«{dlt['предприятие']['до']}/{dlt['поток']['до']}» vs "
                     f"«{dlt['предприятие']['после']}/{dlt['поток']['после']}») — "
                     "дельты считайте ориентировочными.")
    return "\n".join(L)


@app.route("/api/sravnenie", methods=["POST"])
def api_sravnenie():
    """Дельта двух прогонов одного инструмента: id_do, id_posle.
    Порядок задаётся клиентом (до → после), метки — только подсказка."""
    d, err = прочитать_json_тело("тело: {id_do, id_posle}")
    if err:
        return jsonify(err[0]), err[1]
    d = d or {}
    id_do, id_posle = d.get("id_do"), d.get("id_posle")
    # Фикс У-5: type() is int — bool не проходит как id прогона
    if type(id_do) is not int or type(id_posle) is not int or id_do == id_posle:
        return jsonify({"ok": False, "errors": [
            "укажите два разных id прогонов: «id_do» и «id_posle» "
            "(целые числа, bool недопустим)"]}), 400
    with db() as con:
        rows = con.execute(
            "SELECT id, id_proekta, инструмент, итоги_json, автор, дата, комментарий, метка "
            "FROM progony WHERE id IN (?, ?)", (id_do, id_posle)).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    g_a, g_b = by_id.get(id_do), by_id.get(id_posle)
    if g_a is None or g_b is None:
        return jsonify({"ok": False, "errors": [
            f"прогон № {id_do if g_a is None else id_posle} не найден"]}), 404
    if g_a["инструмент"] != g_b["инструмент"]:
        return jsonify({"ok": False, "errors": [
            "прогоны разных инструментов сравнивать нельзя: "
            f"№ {id_do} — «{ИНСТРУМЕНТЫ[g_a['инструмент']]['название']}», "
            f"№ {id_posle} — «{ИНСТРУМЕНТЫ[g_b['инструмент']]['название']}»"]}), 400
    инструмент = g_a["инструмент"]
    dlt = sravnit(инструмент, json.loads(g_a["итоги_json"]), json.loads(g_b["итоги_json"]))
    if dlt is None:
        return jsonify({"ok": False, "errors": [
            f"для инструмента «{ИНСТРУМЕНТЫ[инструмент]['название']}» сравнение "
            "прогонов не предусмотрено (у прогона нет пары «до/после»)"]}), 400
    md = delta_md(инструмент, dlt, g_a, g_b)
    return jsonify({"ok": True, "инструмент": инструмент, "дельта": dlt,
                    "дельта_md": md, "дельта_html": md_to_html(md)})


# === Фаст-презентация (Спека П1, ломтик П2): серверный сборщик данных ===
def sobrat_preza(проект_id, слайды=None, тема="бумага", титул=None):
    """Собрать данные презентации проекта из сохранённых прогонов.
    Возвращает (собрано, None) или (None, (ответ, код)) — как прочитать_json_тело.
    Гейты (Спека П1, п. 7): проект не выбран/не существует, нет ни одного
    прогона → честная ошибка, сборка не стартует."""
    if type(проект_id) is not int or проект_id <= 0:
        return None, ({"ok": False, "errors": [
            "проект не выбран: поле «проект_id» должно быть целым числом > 0 "
            "(bool недопустим)"]}, 400)
    with db() as con:
        p = con.execute("SELECT * FROM proekty WHERE id = ?", (проект_id,)).fetchone()
        if p is None:
            return None, ({"ok": False, "errors": [
                f"проект № {проект_id} не найден"]}, 400)
        rows = con.execute(
            "SELECT id, инструмент, итоги_json, отчёт_md, автор, дата, "
            "комментарий, метка FROM progony WHERE id_proekta = ? ORDER BY id",
            (проект_id,)).fetchall()
    if not rows:
        return None, ({"ok": False, "errors": [
            "в проекте нет ни одного сохранённого прогона — сначала сохраните "
            "хотя бы один прогон (презентация собирается только из прогонов "
            "проекта)"]}, 400)
    прогоны = []
    for r in rows:
        g = dict(r)
        g["итоги"] = json.loads(g.pop("итоги_json"))
        прогоны.append(g)
    собрано = preza_data.собрать(dict(p), прогоны, слайды=слайды, тема=тема,
                                 титул=титул, sravnit=sravnit)
    return собрано, None


@app.route("/api/preza/build", methods=["POST"])
def api_preza_build():
    """POST {проект_id, слайды?, тема?, титул?{предприятие, поток, автор}} →
    {ok, собрано:{слайды, лог_сборки, тема}}. Только сбор данных; PPTX (П3)
    и UI (П4) — отдельные ломтики."""
    d, err = прочитать_json_тело(
        "тело: {проект_id, слайды?, тема?, титул?{предприятие, поток, автор}}")
    if err:
        return jsonify(err[0]), err[1]
    d = d or {}
    тема = d.get("тема") or "бумага"
    if тема not in preza_data.ТЕМЫ:
        return jsonify({"ok": False, "errors": [
            f"неизвестная тема «{тема}»; доступны: "
            + ", ".join(preza_data.ТЕМЫ)]}), 400
    слайды = d.get("слайды")
    if слайды is not None:
        if (not isinstance(слайды, list)
                or any(к not in preza_data.СКЕЛЕТ for к in слайды)):
            return jsonify({"ok": False, "errors": [
                "поле «слайды» должно быть списком кодов из: "
                + ", ".join(preza_data.ПОРЯДОК)]}), 400
    титул = d.get("титул")
    if титул is not None and not isinstance(титул, dict):
        return jsonify({"ok": False, "errors": [
            "поле «титул» должно быть объектом {предприятие, поток, автор}"]}), 400
    собрано, ош = sobrat_preza(d.get("проект_id"), слайды=слайды,
                               тема=тема, титул=титул)
    if ош:
        return jsonify(ош[0]), ош[1]
    return jsonify({"ok": True, "собрано": собрано})


@app.route("/api/preza/pptx", methods=["POST"])
def api_preza_pptx():
    """POST {проект_id, слайды?, тема?, титул?} → PPTX файлом.
    Сбор данных — через сборщик П2 (те же гейты); здесь только вёрстка,
    round-trip валидация и отдача файла. Лог сборки — в заголовке
    X-Preza-Log (urlencoded JSON)."""
    d, err = прочитать_json_тело(
        "тело: {проект_id, слайды?, тема?, титул?{предприятие, поток, автор}}")
    if err:
        return jsonify(err[0]), err[1]
    d = d or {}
    тема = d.get("тема") or "бумага"
    if тема not in preza_data.ТЕМЫ:
        return jsonify({"ok": False, "errors": [
            f"неизвестная тема «{тема}»; доступны: "
            + ", ".join(preza_data.ТЕМЫ)]}), 400
    слайды = d.get("слайды")
    if слайды is not None and (not isinstance(слайды, list)
                               or any(к not in preza_data.СКЕЛЕТ for к in слайды)):
        return jsonify({"ok": False, "errors": [
            "поле «слайды» должно быть списком кодов из: "
            + ", ".join(preza_data.ПОРЯДОК)]}), 400
    титул = d.get("титул")
    if титул is not None and not isinstance(титул, dict):
        return jsonify({"ok": False, "errors": [
            "поле «титул» должно быть объектом {предприятие, поток, автор}"]}), 400
    собрано, ош = sobrat_preza(d.get("проект_id"), слайды=слайды,
                               тема=тема, титул=титул)
    if ош:
        return jsonify(ош[0]), ош[1]
    tmp = ФАЙЛЫ_DIR / f"preza_tmp_{secrets.token_hex(6)}.pptx"
    try:
        preza_pptx.собрать_pptx(собрано, tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "errors": [
            f"PPTX-движок не смог собрать файл: {e}"]}), 500
    ошибки_вал = preza_pptx.проверить_pptx(tmp, len(собрано["слайды"]))
    if ошибки_вал:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "errors": [
            "собранный PPTX не прошёл проверку: " + "; ".join(ошибки_вал)]}), 500
    поток = (собрано["слайды"][0]["данные"].get("поток")
             if собрано["слайды"] and собрано["слайды"][0]["код"] == "титул"
             else "") or "поток"
    safe = re.sub(r"[^\wа-яА-ЯёЁ -]", "", поток).strip().replace(" ", "_")[:60] \
        or "поток"
    from urllib.parse import quote

    @after_this_request
    def _убрать(resp):
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return resp

    return send_file(tmp, as_attachment=True,
                     download_name=f"Защита_{safe}.pptx",
                     mimetype="application/vnd.openxmlformats-officedocument."
                              "presentationml.presentation",
                     max_age=0), 200, {
        "X-Preza-Log": quote(json.dumps(собрано["лог_сборки"],
                                        ensure_ascii=False))}


# === Волна 2: протокол закрытия (этап 5) и ОРД/SMART (этап 1) ===
from flask import after_this_request, send_file  # noqa: E402


def _совпадает(а, б):
    """Контекстная сверка (фикс Н4): пустые значения не конфликтуют,
    сравнение без регистра и лишних пробелов."""
    а, б = (а or "").strip().lower(), (б or "").strip().lower()
    return not а or not б or а == б


def подтяжка_проекта(pid):
    """ЕДИНАЯ автоподтяжка из прогонов проекта (фикс Н3/Н4, ред. v1.1).
    Используется всеми путями протокола: /api/protokol/podtyazhka (UI),
    /api/protokol (скачивание), /api/progony (immutable-снапшот).
    Возвращает:
      поля          — значения для подстановки (только прошедшие сверку контекста);
      источники     — по каждому значению: прогон №, дата, предприятие/поток прогона;
      предупреждения — отказы подстановки при несовпадении предприятия/потока.
    Явное значение из формы всегда перекрывает подтяжку — это решает фронт."""
    out = {"поля": {"ээ_руб_год": None, "главное_ум": None,
                    "цели_smart": [], "показатели": []},
           "источники": {}, "предупреждения": []}
    with db() as con:
        p = con.execute("SELECT предприятие, поток FROM proekty WHERE id = ?",
                        (pid,)).fetchone()
        rows = con.execute(
            "SELECT id, инструмент, итоги_json, метка, дата FROM progony "
            "WHERE id_proekta = ? ORDER BY id", (pid,)).fetchall()
    if p is None:
        return out
    п_пред, п_поток = p["предприятие"], p["поток"]

    def источник(r, itogi):
        return {"прогон": r["id"], "дата": r["дата"], "метка": r["метка"] or None,
                "предприятие": itogi.get("предприятие"),
                "поток": itogi.get("поток")}

    ee_runs = [r for r in rows if r["инструмент"] == "ee"]
    if ee_runs:
        # Фикс У-7: источник — самый СВЕЖИЙ прогон по дате замера; метка «после»
        # служит только тай-брейкером при равных датах (ранее старый «после»
        # молча перекрывал свежий замер — в протокол ехала устаревшая цифра).
        r = max(ee_runs, key=lambda g: (g["дата"] or "", g["метка"] == "после", g["id"]))
        itogi = json.loads(r["итоги_json"])
        if itogi.get("ээ") is not None:
            if (_совпадает(itogi.get("предприятие"), п_пред)
                    and _совпадает(itogi.get("поток"), п_поток)):
                if r["метка"] != "после":
                    out["предупреждения"].append(
                        f"ЭЭ подставлен из замера без метки «после» (прогон № {r['id']} "
                        f"от {(r['дата'] or '')[:10]}) — он свежее всех, но пары "
                        "«до/после» у него нет; проверьте, что это актуальный расчёт.")
                out["поля"]["ээ_руб_год"] = itogi["ээ"]
                out["источники"]["ээ_руб_год"] = источник(r, itogi)
            else:
                out["предупреждения"].append(
                    f"ЭЭ из прогона № {r['id']} НЕ подставлен: предприятие/поток "
                    f"прогона («{itogi.get('предприятие') or '—'} / "
                    f"{itogi.get('поток') or '—'}») не совпадают с карточкой "
                    f"проекта («{п_пред or '—'} / {п_поток or '—'}»). "
                    "Если это осознанный расчёт для проекта — введите ЭЭ вручную.")
    um_runs = [r for r in rows if r["инструмент"] == "uzkie_mesta"]
    if um_runs:
        r = um_runs[-1]
        itogi = json.loads(r["итоги_json"])
        ум = itogi.get("главное_ум")
        if ум:
            if _совпадает(itogi.get("поток"), п_поток):
                out["поля"]["главное_ум"] = ум
                out["источники"]["главное_ум"] = источник(r, itogi)
            else:
                out["предупреждения"].append(
                    f"Главное УМ из прогона № {r['id']} НЕ подставлено: поток "
                    f"прогона («{itogi.get('поток') or '—'}») не совпадает с "
                    f"потоком проекта («{п_поток or '—'}»).")
    smart_runs = [r for r in rows if r["инструмент"] == "smart"]
    if smart_runs:
        r = smart_runs[-1]
        itogi = json.loads(r["итоги_json"])
        цели = itogi.get("цели") or []
        if цели:
            if (_совпадает(itogi.get("предприятие"), п_пред)
                    and _совпадает(itogi.get("поток"), п_поток)):
                out["поля"]["цели_smart"] = цели
                # Мост SMART → протокол: показатели До/Цель (факт — замер «после», вручную)
                out["поля"]["показатели"] = [
                    {"показатель": ц.get("наименование"), "ед_изм": ц.get("ед"),
                     "до": ц.get("текущий"), "цель": ц.get("целевой")}
                    for ц in цели if ц.get("наименование")]
                out["источники"]["показатели"] = источник(r, itogi)
            else:
                out["предупреждения"].append(
                    f"Показатели SMART из прогона № {r['id']} НЕ подставлены: "
                    f"предприятие/поток прогона не совпадают с карточкой проекта.")
    return out


# --- Фикс Н6: по-требовательный ввод чек-листа ---
# Уровни требований извлечены из официальной формы
# «Чек-лист оценки 4.0.xlsx» (архив «проеткы/Чек лист 21 балл»): маркерные
# строки «Уровень "N"» задают уровень последующих требований. Требование 13.6
# есть только в скелете шаблона протокола — отнесено к уровню 3 (последнее
# в направлении 13, как и 13.5).
УРОВНИ_ТРЕБОВАНИЙ = {"1.1": 1, "1.2": 1, "1.3": 2, "1.4": 2, "1.5": 3, "1.6": 3,
    "2.1": 1, "2.2": 2, "2.3": 2, "2.4": 2, "2.5": 3, "2.6": 3,
    "3.1": 1, "3.2": 1, "3.3": 2, "3.4": 2, "3.5": 3,
    "4.1": 1, "4.2": 1, "4.3": 2, "4.4": 2, "4.5": 3, "4.6": 3,
    "5.1": 1, "5.2": 1, "5.3": 2, "5.4": 2, "5.5": 3, "5.6": 3, "5.7": 3,
    "6.1": 1, "6.2": 1, "6.3": 2, "6.4": 2, "6.5": 2, "6.6": 3, "6.7": 3,
    "7.1": 1, "7.2": 1, "7.3": 2, "7.4": 2, "7.5": 3, "7.6": 3,
    "8.1": 1, "8.2": 1, "8.3": 2, "8.4": 2, "8.5": 3,
    "9.1": 1, "9.2": 2, "9.3": 3, "9.4": 3,
    "10.1": 1, "10.2": 1, "10.3": 2, "10.4": 2, "10.5": 3,
    "11.1": 1, "11.2": 1, "11.3": 1, "11.4": 2, "11.5": 2, "11.6": 3,
    "12.1": 1, "12.2": 1, "12.3": 1, "12.4": 2, "12.5": 2, "12.6": 2,
    "12.7": 3, "12.8": 3, "12.9": 3, "12.10": 3,
    "13.1": 1, "13.2": 1, "13.3": 2, "13.4": 2, "13.5": 3, "13.6": 3,
    "14.1": 1, "14.2": 1, "14.3": 2, "14.4": 2, "14.5": 2, "14.6": 3,
    "14.7": 3, "14.8": 3}

ОЦЕНКИ_ТРЕБОВАНИЯ = ("Соответствует", "Не соответствует", "Н/П")


def баллы_из_оценок(оценки):
    """По-требовательный ввод → баллы направлений по методике уровней:
    уровень N засчитан, если ВСЕ его требования «Соответствует» или «Н/П»
    (не применимо — не блокирует, как «Не оценивалось» официальной формы);
    переход к следующему уровню при невыполненном предыдущем не допускается.
    Возвращает (баллы: {напр: int}, полнота: bool, ошибки: list).
    Фикс У-2: значение оценки строго из ОЦЕНКИ_ТРЕБОВАНИЯ — любая иная строка
    это отказ с номером требования, а НЕ молчаливое «соответствие»."""
    ошибки = []
    for n, запись in (оценки or {}).items():
        о = (запись or {}).get("оценка") if isinstance(запись, dict) else None
        if о is not None and о not in ОЦЕНКИ_ТРЕБОВАНИЯ:
            ошибки.append(
                f"чек-лист, требование {n}: недопустимая оценка «{о}» — допустимы "
                "только: " + ", ".join(f"«{x}»" for x in ОЦЕНКИ_ТРЕБОВАНИЯ))
    if ошибки:
        return {}, False, ошибки
    по_напр = {}
    for napr, nomer, _ in protokol_zakrytiya.СКЕЛЕТ["trebovaniya"]:
        ni = protokol_zakrytiya.СКЕЛЕТ["napravleniya"].index(napr) + 1
        по_напр.setdefault(ni, []).append(nomer.rstrip("."))
    баллы, полнота = {}, True
    for ni, номера in по_напр.items():
        ур_группы = {}
        for n in номера:
            ур_группы.setdefault(УРОВНИ_ТРЕБОВАНИЙ.get(n, 3), []).append(n)
        балл, стоп = 0, False
        for ур in sorted(ур_группы):
            if стоп:
                break
            for n in ур_группы[ур]:
                о = (оценки.get(n) or {}).get("оценка")
                if о is None:
                    полнота = False
                    стоп = True
                    break
                if о == "Не соответствует":
                    стоп = True
                    break
            else:
                балл = ур
        if any((оценки.get(n) or {}).get("оценка") is None for n in номера):
            continue  # недооценённое направление — в баллы не включаем
        баллы[str(ni)] = балл
    return баллы, полнота, []


def применить_чеклист(данные):
    """Если во входе протокола есть чеклист.оценки (по-требовательный режим),
    посчитать чеклист.баллы автоматически; явные баллы при отсутствии оценки
    направления сохраняются. Возвращает (ошибки, предупреждения):
    ошибки — недопустимые значения оценок (фикс У-2, отказ 400)."""
    чек = данные.get("чеклист")
    if not isinstance(чек, dict) or not isinstance(чек.get("оценки"), dict):
        return [], []
    баллы, полнота, ошибки = баллы_из_оценок(чек["оценки"])
    if ошибки:
        return ошибки, []
    старые = чек.get("баллы") or {}
    for ni, б in старые.items():
        баллы.setdefault(str(ni), б)
    чек["баллы"] = баллы
    if not полнота:
        return [], ["чек-лист: оценены не все требования — недооценённые направления "
                    "не вошли в итог и отмечены как «домерить»"]
    return [], []


@app.route("/api/protokol/skelet")
def api_protokol_skelet():
    """Скелет чек-листа и мероприятий — чтобы фронт строил селекторы
    без дублирования текстов официального шаблона.
    Ред. v1.1: + trebovaniya, уровни и варианты оценок для по-требовательного
    режима чек-листа (фикс Н6)."""
    return jsonify({"ok": True,
                    "napravleniya": protokol_zakrytiya.СКЕЛЕТ["napravleniya"],
                    "trebovaniya": protokol_zakrytiya.СКЕЛЕТ["trebovaniya"],
                    "urovni": УРОВНИ_ТРЕБОВАНИЙ,
                    "оценки": list(ОЦЕНКИ_ТРЕБОВАНИЯ),
                    "meropriyatiya": protokol_zakrytiya.СКЕЛЕТ["meropriyatiya"],
                    "порог": protokol_zakrytiya.ПОРОГ_БАЛЛОВ})


@app.route("/api/protokol/podtyazhka")
def api_protokol_podtyazhka():
    pid = request.args.get("id_proekta", type=int)
    if not pid:
        return jsonify({"ok": False, "errors": [
            "подтяжка доступна только в рамках выбранного проекта — "
            "укажите id_proekta (выберите проект в шапке)"]}), 400
    with db() as con:
        p = con.execute("SELECT предприятие, поток FROM proekty WHERE id = ?",
                        (pid,)).fetchone()
    if p is None:
        return jsonify({"ok": False, "errors": [f"проект № {pid} не найден"]}), 404
    подт = подтяжка_проекта(pid)
    out = {"ok": True,
           "предприятие": p["предприятие"] or None,
           "поток": p["поток"] or None,
           "источники": подт["источники"],
           "предупреждения": подт["предупреждения"]}
    out.update(подт["поля"])
    return jsonify(out)


@app.route("/api/ee/podtyazhka")
def api_ee_podtyazhka():
    """Мост этап 2→3 (фикс Н1): из последнего прогона «узкие места» проекта
    в карточку ЭЭ подтягивается только то, что реально есть в данных диагностики:
    поток, главное УМ (текстовая подсказка «контекст диагностики») и
    производительности/Тц как комментарий. Экономические поля (цена, с/с,
    объём, такт) в данных диагностики отсутствуют — их вводит пользователь."""
    pid = request.args.get("id_proekta", type=int)
    if not pid:
        return jsonify({"ok": False, "errors": [
            "подтяжка доступна только в рамках выбранного проекта — "
            "укажите id_proekta (выберите проект в шапке)"]}), 400
    with db() as con:
        p = con.execute("SELECT предприятие, поток FROM proekty WHERE id = ?",
                        (pid,)).fetchone()
        rows = con.execute(
            "SELECT id, итоги_json, вход_json, дата FROM progony "
            "WHERE id_proekta = ? AND инструмент = 'uzkie_mesta' ORDER BY id",
            (pid,)).fetchall()
    if p is None:
        return jsonify({"ok": False, "errors": [f"проект № {pid} не найден"]}), 404
    if not rows:
        return jsonify({"ok": True, "предприятие": p["предприятие"] or None,
                        "поток": p["поток"] or None,
                        "контекст_диагностики": None, "комментарий": None,
                        "подсказка": "В проекте пока нет прогонов «Поиск узкого "
                                     "места» — контекст диагностики подтянуть "
                                     "неоткуда. Остальное введите из экономических "
                                     "данных проекта."})
    r = rows[-1]
    itogi = json.loads(r["итоги_json"])
    вход = json.loads(r["вход_json"])
    ум = itogi.get("главное_ум")
    предупр = None
    if not _совпадает(itogi.get("поток"), p["поток"]):
        предупр = (f"Поток прогона № {r['id']} («{itogi.get('поток') or '—'}») "
                   f"не совпадает с потоком проекта («{p['поток'] or '—'}») — "
                   "контекст подтягивать не стал.")
        return jsonify({"ok": True, "предприятие": p["предприятие"] or None,
                        "поток": p["поток"] or None,
                        "контекст_диагностики": None, "комментарий": None,
                        "подсказка": предупр})
    части = []
    for op in вход.get("операции", []):
        куски = []
        if isinstance(op.get("производительность_т_ч"), (int, float)):
            куски.append(f"{op['производительность_т_ч']} т/ч")
        if isinstance(op.get("тц_мин"), (int, float)):
            куски.append(f"Тц {op['тц_мин']} мин")
        if куски and op.get("имя"):
            части.append(f"«{op['имя']}» — " + ", ".join(куски))
    комментарий = None
    if части:
        комментарий = ("Диагностика потока (прогон № {} от {}): ".format(
            r["id"], (r["дата"] or "")[:10]) + "; ".join(части[:8])
            + ("; …" if len(части) > 8 else ""))
    return jsonify({
        "ok": True,
        "предприятие": p["предприятие"] or None,
        "поток": itogi.get("поток") or p["поток"] or None,
        "контекст_диагностики": (
            f"Главное узкое место по прогону № {r['id']} от "
            f"{(r['дата'] or '')[:10]}: «{ум}»" if ум else None),
        "комментарий": комментарий,
        "подсказка": "ЭЭ-калькулятору нужны цена единицы, переменная "
                     "себестоимость, объём реализации и такт — в данных "
                     "диагностики их нет; введите из экономических данных "
                     "проекта."})


@app.route("/api/protokol", methods=["POST"])
def api_protokol():
    """Сформировать протокол закрытия (docx на скачивание).
    Подтяжка ЭЭ/УМ — только при указанном id_proekta, единой функцией
    подтяжка_проекта() с контекстной сверкой (фикс Н3/Н4)."""
    d, err = прочитать_json_тело("тело: {данные, id_proekta?}")
    if err:
        return jsonify(err[0]), err[1]
    d = d or {}
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    данные = d.get("данные")
    if not isinstance(данные, dict):
        return jsonify({"ok": False, "errors": [
            "поле «данные» должно быть JSON-объектом входа ядра протокола"]}), 400
    данные = dict(данные)
    ошибки_чек, _ = применить_чеклист(данные)
    if ошибки_чек:
        return jsonify({"ok": False, "errors": ошибки_чек}), 400
    pid = d.get("id_proekta")
    if type(pid) is int and pid > 0:
        подт = подтяжка_проекта(pid)
        if данные.get("ээ_руб_год") is None and подт["поля"]["ээ_руб_год"] is not None:
            данные["ээ_руб_год"] = подт["поля"]["ээ_руб_год"]
    tmp = Path(tempfile.gettempdir()) / f"агентцех_{secrets.token_hex(6)}.docx"
    try:
        protokol_zakrytiya.сгенерировать(данные, str(tmp))
    except ValueError as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "errors": [str(e)]}), 400
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "errors": [
            f"Ядро протокола не смогло обработать данные: {e}"]}), 400
    resp = send_file(tmp, as_attachment=True,
                     download_name="Протокол закрытия.docx")
    # Фикс У-9: неположительный ЭЭ — пометка в docx (ядро) + заголовок-маркер для API-клиента
    ээ = данные.get("ээ_руб_год")
    if _конечное(ээ) and ээ <= 0:
        # значение заголовка — ASCII (latin-1): кириллица ломает запись сокета
        resp.headers["X-AgentCeh-Warning"] = "ee-nonpositive: proverite vhodnye dannye"
    return resp


# === ВР-76: экспорт в шаблон «Вскрытие резервов» V4.7.2 (мероприятие 2.8) ===

def _vr_данные_проекта(pid):
    """Общая часть /api/vr_check и /api/vr_export: собрать данные проекта."""
    with db() as con:
        return vr_export.sobrat_dannye(pid, con)


@app.route("/api/vr_check", methods=["POST"])
def api_vr_check():
    """Предпроверка правил ФЦК (вебинар) ДО их ИИ-сервиса.
    Тело: {"id_proekta": N} → JSON: нарушения/предупреждения + что заполнено."""
    d, err = прочитать_json_тело("тело: {id_proekta}")
    if err:
        return jsonify(err[0]), err[1]
    pid = (d or {}).get("id_proekta")
    if type(pid) is not int or pid <= 0:
        return jsonify({"ok": False, "errors": [
            "укажите id_proekta — проверка доступна только в рамках выбранного "
            "проекта (выберите проект в шапке)"]}), 400
    try:
        data = _vr_данные_проекта(pid)
    except ValueError as e:
        return jsonify({"ok": False, "errors": [str(e)]}), 404
    проверки = vr_export.proverit_pravila(data)
    return jsonify({
        "ok": True,
        "проверки": проверки,
        "нарушений": sum(1 for п in проверки if п["статус"] == "нарушение"),
        "нет_данных": sum(1 for п in проверки if п["статус"] == "нет_данных"),
        "предупреждения": data["предупреждения"],
        "источники": data["источники"],
    })


@app.route("/api/vr_export", methods=["POST"])
def api_vr_export():
    """Заполненный шаблон «Вскрытие резервов» V4.7.2 (xlsx) на скачивание.
    Тело: {"id_proekta": N}. В историю/БД прогонов НЕ пишется (скачивание —
    не снапшот). Пустых полей не выдумываем: None остаётся пустым."""
    d, err = прочитать_json_тело("тело: {id_proekta}")
    if err:
        return jsonify(err[0]), err[1]
    pid = (d or {}).get("id_proekta")
    if type(pid) is not int or pid <= 0:
        return jsonify({"ok": False, "errors": [
            "укажите id_proekta — выберите проект в шапке"]}), 400
    try:
        data = _vr_данные_проекта(pid)
    except ValueError as e:
        return jsonify({"ok": False, "errors": [str(e)]}), 404
    try:
        байты = vr_export.zapolnit(data)
    except FileNotFoundError as e:
        return jsonify({"ok": False, "errors": [str(e)]}), 503
    except Exception as e:
        return jsonify({"ok": False, "errors": [
            f"Не удалось заполнить шаблон ВР: {e}"]}), 500
    from urllib.parse import quote
    имя = "Вскрытие резервов V4.7.2 — {}.xlsx".format(
        data.get("предприятие") or f"проект {pid}")
    return Response(
        байты,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(имя)})


@app.route("/api/ord", methods=["POST"])
def api_ord():
    """Сформировать пакет ОРД (docx: приказ + карточка проекта) на скачивание."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом входа ядра ОРД")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False, "errors": [
            "тело запроса должно быть JSON-объектом входа ядра ОРД"]}), 400
    errs = ord_smart.validirovat_ord(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    tmp = Path(tempfile.gettempdir()) / f"агентцех_{secrets.token_hex(6)}.docx"
    try:
        ord_smart.gen_ord_docx(d, str(tmp))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "errors": [
            f"Ядро ОРД не смогло обработать данные: {e}"]}), 400
    return send_file(tmp, as_attachment=True, download_name="Пакет ОРД.docx")


@app.route("/api/akt", methods=["POST"])
def api_akt():
    """Сформировать акт начала мероприятий (docx на скачивание)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом входа ядра акта")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False, "errors": [
            "тело запроса должно быть JSON-объектом входа ядра акта"]}), 400
    вариант = d.get("вариант") or "рцк"
    if вариант not in ("рцк", "фцк"):
        return jsonify({"ok": False, "errors": [
            "поле «вариант» — только «рцк» или «фцк»"]}), 400
    tmp = Path(tempfile.gettempdir()) / f"агентцех_{secrets.token_hex(6)}.docx"
    try:
        dokumenty_fck.build_akt(d, str(tmp))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "errors": [
            f"Ядро акта не смогло обработать данные: {e}"]}), 400
    return send_file(tmp, as_attachment=True,
                     download_name="Акт начала мероприятий.docx")


@app.route("/api/soglashenie", methods=["POST"])
def api_soglashenie():
    """Сформировать соглашение о сотрудничестве (docx на скачивание)."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом входа ядра соглашения")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False, "errors": [
            "тело запроса должно быть JSON-объектом входа ядра соглашения"]}), 400
    tmp = Path(tempfile.gettempdir()) / f"агентцех_{secrets.token_hex(6)}.docx"
    try:
        dokumenty_fck.build_soglashenie(d, str(tmp))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "errors": [
            f"Ядро соглашения не смогло обработать данные: {e}"]}), 400
    return send_file(tmp, as_attachment=True,
                     download_name="Соглашение о сотрудничестве.docx")


@app.route("/api/meropriyatiya", methods=["POST"])
def api_meropriyatiya():
    """Генератор мероприятий (спека № 3): JSON-вход → цепочка
    «проблема → ветки → причины → мероприятия → план» + сводка итогов.
    Возвращает полный результат (для режима «покажи рассуждение»),
    итоги и md-отчёт по контракту прогона."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом входа генератора мероприятий")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False, "errors": [
            "тело запроса должно быть JSON-объектом входа генератора "
            "мероприятий (спека № 3, раздел 3)"]}), 400
    try:
        прогон = meropriyatiya.сгенерировать(d)
    except ValueError as e:
        return jsonify({"ok": False, "errors": [str(e)]}), 400
    except Exception as e:
        return jsonify({"ok": False, "errors": [
            f"Ядро генератора мероприятий не смогло обработать данные: {e}"]}), 400
    итоги = meropriyatiya.итоги_мероприятия(прогон)
    итоги["предприятие"] = d.get("predpriyatie") or None
    отчёт = meropriyatiya.отчёт_meropriyatiya_md(прогон)
    return jsonify({"ok": True, "result": прогон, "итоги": итоги,
                    "report_md": отчёт, "result_html": md_to_html(отчёт)})


@app.route("/api/meropriyatiya/docx", methods=["POST"])
def api_meropriyatiya_docx():
    """План мероприятий по шаблону Прил. 4 — .docx на скачивание."""
    return _meropriyatiya_файл("docx")


@app.route("/api/meropriyatiya/xlsx", methods=["POST"])
def api_meropriyatiya_xlsx():
    """План мероприятий по шаблону Прил. 4 — .xlsx на скачивание."""
    return _meropriyatiya_файл("xlsx")


def _meropriyatiya_файл(формат):
    """Общая точка скачивания плана: вход → сгенерировать() →
    build_plan_docx/xlsx (bytes) → файл на скачивание."""
    import io
    d, err = прочитать_json_тело("тело должно быть JSON-объектом входа генератора мероприятий")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False, "errors": [
            "тело запроса должно быть JSON-объектом входа генератора "
            "мероприятий (спека № 3, раздел 3)"]}), 400
    try:
        прогон = meropriyatiya.сгенерировать(d)
        if формат == "docx":
            данные = meropriyatiya.build_plan_docx(d, прогон)
        else:
            данные = meropriyatiya.build_plan_xlsx(d, прогон)
    except ValueError as e:
        return jsonify({"ok": False, "errors": [str(e)]}), 400
    except Exception as e:
        return jsonify({"ok": False, "errors": [
            f"Ядро генератора мероприятий не смогло построить файл: {e}"]}), 400
    if формат == "docx":
        mime = ("application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document")
        имя = "План мероприятий.docx"
    else:
        mime = ("application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet")
        имя = "План мероприятий.xlsx"
    return send_file(io.BytesIO(данные), as_attachment=True,
                     download_name=имя, mimetype=mime)


@app.route("/api/zamer/skelet")
def api_zamer_skelet():
    """Скелет чек-листа «Цифрового замера» для формы (паттерн
    /api/otbor/skelet): блоки, вопросы, варианты с весами, шкала шагов."""
    return jsonify(cifrovoy_zamer.skelet())


@app.route("/api/zamer", methods=["POST"])
def api_zamer():
    """Цифровой замер (Протокол № 43, п. 2): JSON-вход {ответы} → шаг
    готовности (худший блок), узкий блок, рекомендации цифровой ветки +
    итоги и md-отчёт по контракту прогона."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом входа «Цифрового замера»")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    if not isinstance(d, dict):
        return jsonify({"ok": False, "errors": [
            "тело запроса должно быть JSON-объектом входа «Цифрового "
            "замера» {«ответы»: {вопрос: вариант}}"]}), 400
    errs = cifrovoy_zamer.validirovat(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        r = cifrovoy_zamer.raschet(d)
    except Exception as e:
        return jsonify({"ok": False, "errors": [
            f"Ядро «Цифрового замера» не смогло обработать данные: {e}"]}), 400
    итоги = cifrovoy_zamer.итоги_zamer(d, r)
    отчёт = cifrovoy_zamer.отчёт_zamer_md(d, r)
    return jsonify({"ok": True, "result": r, "итоги": итоги,
                    "report_md": отчёт, "result_html": md_to_html(отчёт)})


@app.route("/api/smart/mu66")
def api_smart_mu66():
    """Справочник показателей МУ-66-2024 + рамки ПТ для формы «Цели SMART»."""
    return jsonify({"ok": True,
                    "показатели": ord_smart.МУ66,
                    "рамки": ord_smart.РАМКИ_ПТ,
                    "порог_обоснования_пкт": ord_smart.ПОРОГ_ОБОСНОВАНИЯ_ПКТ})


@app.route("/api/smart", methods=["POST"])
def api_smart():
    """Конструктор целей SMART: разворот S/M/A/R/T с валидаторами → md."""
    d, err = прочитать_json_тело("тело должно быть JSON-объектом входа конструктора SMART")
    if err:
        return jsonify(err[0]), err[1]
    неч = найти_нечисла(d)
    if неч:
        return jsonify({"ok": False, "errors": неч}), 400
    errs = ord_smart.validirovat_smart(d)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        md, итоги, _ = ord_smart.gen_smart_md(d)
    except Exception as e:
        return jsonify({"ok": False, "errors": [
            f"Ядро SMART не смогло обработать данные: {e}"]}), 400
    return jsonify({"ok": True, "report_md": md, "result_html": md_to_html(md),
                    "итоги": итоги})


@app.route("/api/progony/<int:gid>/файл")
def api_progon_file(gid):
    """Скачать docx прогона (ord/protokol) — ре-генерация не нужна:
    файл сложен рядом с БД при сохранении прогона (immutable)."""
    with db() as con:
        r = con.execute("SELECT инструмент, итоги_json FROM progony WHERE id = ?",
                        (gid,)).fetchone()
    if r is None:
        return jsonify({"ok": False, "errors": [f"прогон № {gid} не найден"]}), 404
    итоги = json.loads(r["итоги_json"])
    файл = итоги.get("файл")
    if not файл:
        return jsonify({"ok": False, "errors": [
            f"у прогона № {gid} нет файла (инструмент "
            f"«{ИНСТРУМЕНТЫ[r['инструмент']]['название']}» не формирует docx)"]}), 404
    # Фикс У-8: путь из итоги_json.файл — только внутри каталога файлы/ сервиса
    # и только по шаблону progon_<id>_*.docx; иначе доверие к записи БД
    # превращалось бы в arbitrary file read.
    путь = (Path(__file__).resolve().parent / файл).resolve()
    base = ФАЙЛЫ_DIR.resolve()
    if base not in путь.parents or not re.fullmatch(
            r"progon_\d+_(орд|протокол|акт|соглашение|план)\.docx", путь.name):
        return jsonify({"ok": False, "errors": [
            f"файл прогона № {gid} указывает вне каталога файлов сервиса "
            f"(«{файл}») — запись повреждена, файл не отдан"]}), 404
    if not путь.exists():
        return jsonify({"ok": False, "errors": [
            f"файл прогона № {gid} не найден на диске ({файл})"]}), 404
    имя = {"ord": "Пакет ОРД.docx", "protokol": "Протокол закрытия.docx",
           "akt": "Акт начала мероприятий.docx",
           "soglashenie": "Соглашение о сотрудничестве.docx",
           "meropriyatiya": "План мероприятий.docx"}[r["инструмент"]]
    return send_file(путь, as_attachment=True, download_name=имя)


def svobodny_port(start=8000):
    for p in range(start, start + 100):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    sys.exit("Не найден свободный порт в диапазоне 8000–8099")


if __name__ == "__main__":
    port = svobodny_port()
    print(f"Ведение проектов · РЦК → http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
