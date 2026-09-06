# -*- coding: utf-8 -*-
"""ekstraktor_pa.py — извлечение данных из листа производственного анализа (ПА).

Одна функция: izvlech(file_bytes, filename) -> dict.
Поддерживаемые форматы (см. ИИ-направление/разведка_па/ФОРМАТ_ПА.md):
  A — КПСЦ-транспонированный (эталон: ОЗМК, ОКЗ): операции по столбцам.
  B — Свод ПА (операция = строка): план/факт время, простои.
  C — Почасовой лист ППА (Гайфа, ОКЗ): шапка + почасовые строки.
  D — Хронометраж: замеры времени цикла по участкам.
Прочее — «нераспознано», без падения. Без LLM, чистые функции, без Flask.
"""

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import io
import re
import statistics

MAX_OPERACII = 500


# ---------- общие хелперы ----------

def _txt(v):
    """Ячейка -> строка без переводов строк; None -> ''."""
    if v is None:
        return ""
    return " ".join(str(v).split())


def _num(v):
    """Ячейка -> float или None. Терпимо к «1 234,5», %, прочеркам."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("\xa0", "").replace(" ", "")
    if t in ("", "-", "—", "–", "н/д", "н/а"):
        return None
    if t.endswith("%"):
        t = t[:-1]
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _merged_fill(ws):
    """Карта (r,c) -> значение главной ячейки для покрытых объединением.

    Используется ТОЛЬКО для поиска меток/шапок, не для извлечения данных
    (развёртка данных ломает метрики блоков — зафиксировано в прошлом прогоне).
    """
    fill = {}
    for rng in ws.merged_cells.ranges:
        main = ws.cell(rng.min_row, rng.min_col).value
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    fill[(r, c)] = main
    return fill


def _cell(ws, fill, r, c):
    v = ws.cell(r, c).value
    if v is None and fill is not None:
        return fill.get((r, c))
    return v


def _low(v):
    return _txt(v).lower()


def _vremya_v_min(x, edinica, warn, pole):
    """Привести время к минутам по единице из заголовка."""
    if x is None:
        return None
    if edinica == "ч":
        return round(x * 60, 2)
    if edinica == "сек":
        return round(x / 60, 4)
    return x  # уже мин


def _edinica_iz_zagolovka(zag):
    """«…, ч.» / «, сек» / «мин» -> 'ч' | 'сек' | 'мин' | None."""
    z = zag.lower()
    if re.search(r"[,\(]\s*сек", z) or "секунд" in z:
        return "сек"
    if re.search(r"[,\(]\s*ч\b", z) or re.search(r"[,\(]\s*ч\.", z) or ", час" in z:
        return "ч"
    if "мин" in z:
        return "мин"
    return None


# ---------- формат A: КПСЦ-транспонированный (эталон) ----------

_METKI_A = {
    "uchastok": ("участок/пролет", "участок /пролет"),
    "nazvanie": ("описание действий", "наименование операции", "операция"),
    "takt": ("время такта",),
    "vpp": ("время протекания процесса", "впп"),
    "tc": ("время цикла операции", "т цикла", "тц"),
    "ozhidanie": ("время ожидания", "т ож"),
    "nzp": ("нзп", "запас"),
    "personal": ("персонал",),
    "partiya": ("партия",),
}


def _probovat_format_A(ws, fill, warn):
    """Операции по столбцам, показатели по строкам. Вернуть dict или None."""
    max_r, max_c = ws.max_row or 1, ws.max_column or 1
    if max_r < 3 or max_c < 3:
        return None
    # найти строку-метку «описание действий» в первых 2 колонках
    stroki = {}
    for r in range(1, min(max_r, 60) + 1):
        for c in range(1, min(max_c, 3) + 1):
            t = _low(_cell(ws, fill, r, c))
            if not t:
                continue
            for key, metki in _METKI_A.items():
                if key not in stroki and any(t.startswith(m) for m in metki):
                    stroki[key] = (r, c, t)
    if "nazvanie" not in stroki or "tc" not in stroki:
        return None
    r_name = stroki["nazvanie"][0]
    c_start = stroki["nazvanie"][1] + 1
    ed_tc = _edinica_iz_zagolovka(stroki["tc"][2])
    if ed_tc is None:
        warn.append("Формат A: единица Тц не распознана из заголовка «%s» — "
                    "приняты часы, проверьте глазами" % stroki["nazvanie"][2])
        ed_tc = "ч"
    operacii = []
    for c in range(c_start, min(max_c, c_start + MAX_OPERACII) + 1):
        nazv = _txt(ws.cell(r_name, c).value)
        if not nazv:
            continue
        if nazv.upper().startswith("ИТОГО"):
            break
        op = {"nazvanie": nazv}
        if "uchastok" in stroki:
            u = _txt(ws.cell(stroki["uchastok"][0], c).value)
            if u:
                op["uchastok"] = u
        tc = _num(ws.cell(stroki["tc"][0], c).value)
        if tc is not None:
            op["tc_min"] = _vremya_v_min(tc, ed_tc, warn, "Тц")
        if "vpp" in stroki:
            vpp = _num(ws.cell(stroki["vpp"][0], c).value)
            if vpp is not None:
                op["vpp_ch"] = vpp
        if "nzp" in stroki:
            nzp = _num(ws.cell(stroki["nzp"][0], c).value)
            if nzp is not None:
                op["zapas"] = nzp
        if "personal" in stroki:
            p = _num(ws.cell(stroki["personal"][0], c).value)
            if p is not None:
                op["personal"] = p
        if "ozhidanie" in stroki:
            o = _num(ws.cell(stroki["ozhidanie"][0], c).value)
            if o is not None:
                op["ozhidanie_ch"] = o
        if tc is None:
            op["_transport"] = True  # перемещение/ожидание без Тц
        operacii.append(op)
    if not operacii:
        return None
    meta = {}
    if "takt" in stroki:
        r_t, _, zag = stroki["takt"]
        ed_t = _edinica_iz_zagolovka(zag) or "ч"
        for c in range(c_start, max_c + 1):
            t = _num(ws.cell(r_t, c).value)
            if t is not None:
                meta["takt_min"] = _vremya_v_min(t, ed_t, warn, "такт")
                break
        else:
            warn.append("Формат A: строка «Время такта» найдена, но значения нет")
    n_transp = sum(1 for op in operacii if op.pop("_transport", False))
    if n_transp:
        warn.append("Формат A: %d столбцов без Тц (транспорт/ожидание) — "
                    "оставлены с пустым Тц" % n_transp)
    return {"format": "A_kpsc_transponirovanny", "operacii": operacii, "meta": meta,
            "edinica_tc": ed_tc}


# ---------- формат B: Свод ПА (операция = строка) ----------

def _probovat_format_B(ws, fill, warn):
    """Шапка с «Наименование операции» и «время выполнения»; строки = операции."""
    max_r, max_c = ws.max_row or 1, ws.max_column or 1
    hdr = None
    for r in range(1, min(max_r, 15) + 1):
        row = [_low(_cell(ws, fill, r, c)) for c in range(1, min(max_c, 30) + 1)]
        if any("наименование операции" in t for t in row) and \
           any("время выполнения" in t for t in row):
            hdr = (r, row)
            break
    if not hdr:
        return None
    r0, row = hdr

    def col(sub):
        for i, t in enumerate(row):
            if sub in t:
                return i + 1
        return None

    c_data, c_uch, c_isp = col("дата"), col("участок"), col("исполнитель")
    c_izd, c_op = col("изделие"), col("наименование операции")
    c_plan = None
    c_fakt = None
    for i, t in enumerate(row):
        if "плановое время" in t:
            c_plan = i + 1
        if "фактическое время" in t:
            c_fakt = i + 1
    prostoi_cols = [(i + 1, row[i]) for i in range(len(row))
                    if any(w in row[i] for w in ("простой", "ожидание", "ремонт",
                                                 "уборка", "перемещение"))]
    operacii = []
    meta = {}
    for r in range(r0 + 1, min(max_r, r0 + MAX_OPERACII) + 1):
        nazv = _txt(ws.cell(r, c_op).value) if c_op else ""
        if not nazv:
            continue  # строки-продолжения (только изделие) пропускаем
        op = {"nazvanie": nazv}
        if c_uch:
            u = _txt(ws.cell(r, c_uch).value)
            if u:
                op["uchastok"] = u
                meta.setdefault("uchastok", u)
        if c_isp:
            i_ = _txt(ws.cell(r, c_isp).value)
            if i_:
                op["ispolnitel"] = i_
                meta.setdefault("ispolnitel", i_)
        if c_izd:
            izd = _txt(ws.cell(r, c_izd).value)
            if izd:
                op["izdelie"] = izd
        if c_data:
            d = ws.cell(r, c_data).value
            if d is not None and hasattr(d, "strftime"):
                meta.setdefault("data", d.strftime("%d.%m.%Y"))
        ed_p = _edinica_iz_zagolovka(row[(c_plan or 1) - 1]) or "ч"
        ed_f = _edinica_iz_zagolovka(row[(c_fakt or 1) - 1]) or "ч"
        if c_plan:
            p = _num(ws.cell(r, c_plan).value)
            if p is not None:
                op["plan_min"] = _vremya_v_min(p, ed_p, warn, "план")
        if c_fakt:
            f = _num(ws.cell(r, c_fakt).value)
            if f is not None:
                op["tc_min"] = _vremya_v_min(f, ed_f, warn, "факт")
                op["fakt_min"] = op["tc_min"]
        prost = {}
        for cc, zag in prostoi_cols:
            v = _num(ws.cell(r, cc).value)
            if v:
                ed = _edinica_iz_zagolovka(zag) or "ч"
                prost[_txt(zag)[:60]] = _vremya_v_min(v, ed, warn, "простой")
        if prost:
            op["prostoi_min"] = prost
        operacii.append(op)
    if not operacii:
        return None
    return {"format": "B_svod_pa", "operacii": operacii, "meta": meta}


# ---------- формат C: почасовой лист ППА ----------

def _probovat_format_C(ws, fill, warn):
    """«Лист производственного анализа» + почасовые строки."""
    max_r, max_c = ws.max_row or 1, ws.max_column or 1
    est_titul = any("лист производственного анализа" in _low(_cell(ws, fill, r, c))
                    or "производственный анализ на участке" in _low(_cell(ws, fill, r, c))
                    for r in range(1, min(max_r, 10) + 1)
                    for c in range(1, min(max_c, 8) + 1))
    # почасовая таблица: строка-шапка со «время» + «план»/«факт»
    hdr = None
    for r in range(1, min(max_r, 15) + 1):
        row = [_low(_cell(ws, fill, r, c)) for c in range(1, min(max_c, 16) + 1)]
        if any(t.startswith("время") for t in row) and \
           any("план" in t for t in row) and any("факт" in t for t in row):
            hdr = (r, row)
            break
    if not est_titul and not hdr:
        return None
    meta = {}
    # мета-поля шапки: «Метка:» + значение правее в той же строке
    metki_meta = {"дата": "data", "смена": "smena", "рабочий": "rabochiy",
                  "бригадир": "brigadir", "участок": "uchastok",
                  "ответственный": "otvetstvenny",
                  "т см. задания": "t_zadaniya_min", "т такта": "takt_min",
                  "т цикла": "tc_min_meta"}
    for r in range(1, min(max_r, 10) + 1):
        for c in range(1, min(max_c, 16) + 1):
            t = _low(_cell(ws, fill, r, c)).rstrip(":")
            if t in metki_meta:
                for cc in range(c + 1, min(max_c, 16) + 1):
                    v = ws.cell(r, cc).value
                    if v is None or not _txt(v):
                        continue
                    if _txt(v).endswith(":") or _low(v).rstrip(":") in metki_meta:
                        break  # дошли до следующей метки — значение не заполнено
                    key = metki_meta[t]
                    if hasattr(v, "strftime"):
                        meta[key] = v.strftime("%d.%m.%Y")
                    elif _num(v) is not None:
                        meta[key] = _num(v)
                    else:
                        meta[key] = _txt(v)
                    break
    # участок — из заголовка «Производственный анализ на участке …»
    for r in range(1, min(max_r, 10) + 1):
        for c in range(1, min(max_c, 16) + 1):
            t = _low(_cell(ws, fill, r, c))
            if t.startswith("производственный анализ на участке"):
                hvost = _txt(_cell(ws, fill, r, c)).split("на участке", 1)[-1]
                hvost = hvost.strip(" .:»\"")
                if hvost:
                    meta.setdefault("uchastok", hvost[:80])
    operacii = []
    if hdr:
        r0, row = hdr

        def col(sub, excl=()):
            for i in range(len(row)):
                if sub in row[i] and not any(x in row[i] for x in excl):
                    return i + 1
            return None

        c_vr = col("время")
        c_plan = col("план", excl=("время", "рабочее"))
        c_fakt = col("факт", excl=("время", "рабочее"))
        c_prost = col("простоя") or col("простой")
        c_prich = col("причин")
        c_sotr = col("сотрудников") or col("численность")
        for r in range(r0 + 1, min(max_r, r0 + 40) + 1):
            vr = _txt(_cell(ws, fill, r, c_vr)) if c_vr else ""
            if not vr or vr.lower().startswith("итого"):
                continue
            if vr.lower().startswith("пример"):
                continue  # образцовая строка шаблона
            op = {"nazvanie": "Интервал " + vr}
            if c_plan:
                p = _num(_cell(ws, fill, r, c_plan))
                if p is not None:
                    op["plan_sht"] = p
            if c_fakt:
                f = _num(_cell(ws, fill, r, c_fakt))
                if f is not None:
                    op["fakt_sht"] = f
            if c_prost:
                s = _num(_cell(ws, fill, r, c_prost))
                if s:
                    op["prostoy_min"] = s
            if c_prich:
                pr = _txt(_cell(ws, fill, r, c_prich))
                if pr:
                    op["prichina_prostoya"] = pr
            if c_sotr:
                n = _num(_cell(ws, fill, r, c_sotr))
                if n is not None:
                    op["personal"] = n
            if "plan_sht" not in op and "fakt_sht" not in op:
                continue
            operacii.append(op)
    if not operacii and not meta:
        return None
    warn.append("Формат C (почасовой лист ППА): Тц по операциям в формате нет — "
                "извлечены почасовые план/факт и простои; для диагностики "
                "узкого места нужен лист КПСЦ (формат A) или ручной ввод Тц")
    return {"format": "C_pochasovoy_ppa", "operacii": operacii, "meta": meta}


# ---------- формат D: хронометраж ----------

def _probovat_format_D(ws, fill, warn):
    """«Время цикла по участкам»: столбцы = участки, строки = замеры."""
    max_r, max_c = ws.max_row or 1, ws.max_column or 1
    hdr = None
    for r in range(1, min(max_r, 10) + 1):
        row = [_low(_cell(ws, fill, r, c)) for c in range(1, min(max_c, 20) + 1)]
        if any("замер" in t for t in row) or \
           (any("время цикла" in t for t in row)):
            hdr = r
            break
    if hdr is None:
        return None
    # шапка участков — строка с «замер» или соседняя; колонки с «, сек»/«, мин»
    operacii = []
    for r_head in range(hdr, min(hdr + 3, max_r) + 1):
        for c in range(1, min(max_c, 20) + 1):
            zag = _txt(ws.cell(r_head, c).value)
            if not zag or "замер" in zag.lower() or "время цикла" in zag.lower():
                continue
            ed = _edinica_iz_zagolovka(zag)
            if ed is None:
                continue
            zamery = []
            for r in range(r_head + 1, min(max_r, r_head + 60) + 1):
                v = _num(ws.cell(r, c).value)
                if v is not None:
                    zamery.append(v)
            if len(zamery) >= 2:
                nazv = re.sub(r"[,\s]*(сек|мин|ч)\.?$", "", zag, flags=re.I).strip()
                operacii.append({
                    "nazvanie": nazv,
                    "tc_min": round(_vremya_v_min(statistics.mean(zamery), ed, warn, "Тц"), 4),
                    "zamerov": len(zamery),
                    "tc_min_median": round(_vremya_v_min(
                        statistics.median(zamery), ed, warn, "Тц"), 4),
                })
        if operacii:
            break
    if not operacii:
        return None
    warn.append("Формат D (хронометраж): Тц = среднее по замерам "
                "(медиана в поле tc_min_median) — сверьте с картой потока")
    return {"format": "D_hronometrazh", "operacii": operacii, "meta": {}}


# ---------- главная функция ----------

def izvlech(file_bytes, filename=""):
    """Извлечь данные ПА из xlsx/xlsm. Возвращает dict; не бросает исключений."""
    rez = {
        "ok": False,
        "file": filename,
        "format": None,
        "predpriyatie": None,
        "uchastok": None,
        "data": None,
        "operacii": [],
        "chislennost": None,
        "takt_min": None,
        "vpp_itogo": None,
        "listy": [],
        "preduprezhdeniya": [],
    }
    warn = rez["preduprezhdeniya"]
    low_name = (filename or "").lower()
    if low_name.endswith(".xls"):
        warn.append("Старый формат .xls не поддерживается — пересохраните "
                    "файл в Excel как .xlsx или .xlsm")
        return rez
    try:
        wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        warn.append("Файл не читается как .xlsx/.xlsm (%s)" % type(e).__name__)
        return rez

    listy = [{"nazvanie": ws.title, "skryt": ws.sheet_state != "visible",
              "strok": ws.max_row, "kolonok": ws.max_column}
             for ws in wb.worksheets]
    rez["listy"] = listy
    if any(l["skryt"] for l in listy):
        warn.append("В файле есть скрытые листы — прочитаны наравне с видимыми: "
                    + ", ".join(l["nazvanie"] for l in listy if l["skryt"]))

    kandidaty = []
    for ws in wb.worksheets:
        fill = _merged_fill(ws)
        for prober in (_probovat_format_A, _probovat_format_B,
                       _probovat_format_C, _probovat_format_D):
            try:
                r = prober(ws, fill, warn)
            except Exception as e:
                warn.append("Лист «%s»: проба %s упала (%s) — пропущена"
                            % (ws.title, prober.__name__, type(e).__name__))
                continue
            if r and (r["operacii"] or r["meta"]):
                r["list"] = ws.title
                r["skryt"] = ws.sheet_state != "visible"
                kandidaty.append(r)
                break  # на листе — один формат

    # приоритет: сначала кандидаты с операциями; внутри — по приоритету формата
    # (эталон A > B > C > D), затем по числу строк
    poryadok = {"A_kpsc_transponirovanny": 0, "B_svod_pa": 1,
                "C_pochasovoy_ppa": 2, "D_hronometrazh": 3}
    kandidaty.sort(key=lambda k: (poryadok.get(k["format"], 9),
                                  -len(k["operacii"])))
    naideno = None
    for k in kandidaty:
        if k["operacii"]:
            naideno = k
            break
    if naideno is None and kandidaty:
        naideno = kandidaty[0]
    if naideno and naideno.get("skryt"):
        warn.append("Формат распознан на скрытом листе «%s»" % naideno["list"])
    if len(kandidaty) > 1:
        warn.append("Формат распознан на нескольких листах (%s) — взят «%s»"
                    % (", ".join(k["list"] for k in kandidaty), naideno["list"]))

    if not naideno:
        rez["format"] = "neraspoznano"
        warn.append("Формат ПА не распознан (поддерживаются: КПСЦ-транспонированный, "
                    "Свод ПА, почасовой лист ППА, хронометраж). "
                    "Заполните таблицу вручную или через ассистент разметки.")
        rez["preduprezhdeniya"] = list(dict.fromkeys(warn))
        return rez

    rez["format"] = naideno["format"]
    rez["format_list"] = naideno.get("list")
    meta = naideno["meta"]
    operacii = naideno["operacii"][:MAX_OPERACII]
    rez["operacii"] = operacii
    rez["uchastok"] = meta.get("uchastok")
    rez["data"] = meta.get("data")
    rez["takt_min"] = meta.get("takt_min")
    rez["meta"] = meta

    # численность: сумма по операциям формата A/D либо макс. по почасовым
    pers = [op.get("personal") for op in operacii if op.get("personal") is not None]
    if pers:
        if naideno["format"] == "C_pochasovoy_ppa":
            rez["chislennost"] = max(pers)
        else:
            rez["chislennost"] = sum(pers)
    else:
        warn.append("Численность персонала не найдена")

    # ВПП итого (формат A)
    vpp = [op.get("vpp_ch") for op in operacii if op.get("vpp_ch") is not None]
    if vpp:
        rez["vpp_itogo"] = {"ch": round(sum(vpp), 4),
                            "sek": round(sum(vpp) * 3600, 1)}

    # предупреждения по обязательным полям
    if not any(op.get("tc_min") is not None for op in operacii):
        warn.append("Тц (время цикла) не найдено ни в одной операции — "
                    "автозаполнение таблицы будет без Тц")
    if not rez["uchastok"] and naideno["format"] not in ("D_hronometrazh",
                                                         "A_kpsc_transponirovanny"):
        warn.append("Поле «Участок» не найдено")
    rez["ok"] = bool(operacii)
    if not operacii:
        warn.append("Операции не извлечены — формат распознан, но строк данных нет")
    rez["preduprezhdeniya"] = list(dict.fromkeys(warn))
    return rez
