# -*- coding: utf-8 -*-
"""Сборка МЕТОДИЧКА_пользователя.pdf из markdown-исходника (reportlab)."""
import os, re, sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, PageBreak, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

SRC = "/Users/aleksandr/Desktop/Методички/ИИ-направление/Прототип/МЕТОДИЧКА_пользователя.md"
OUT = "/Users/aleksandr/Desktop/Методички/ИИ-направление/Прототип/МЕТОДИЧКА_пользователя_ред3.1.pdf"

reg = os.environ.get("DAIMON_CJK_FONT_REGULAR")
bold = os.environ.get("DAIMON_CJK_FONT_BOLD")
if not reg or not bold:
    sys.exit("нет CJK-шрифтов в env")
pdfmetrics.registerFont(TTFont("F", reg))
pdfmetrics.registerFont(TTFont("FB", bold))
pdfmetrics.registerFontFamily("F", normal="F", bold="FB", italic="F", boldItalic="FB")

TERRA = HexColor("#a4572f")
TERRA_LIGHT = HexColor("#c98a5f")
INK = HexColor("#333333")
MUTED = HexColor("#7a6f66")
RULE = HexColor("#d8c9bd")

S = {
    "h1": ParagraphStyle("h1", fontName="FB", fontSize=17, leading=22,
                         textColor=TERRA, spaceBefore=18, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="FB", fontSize=13, leading=17,
                         textColor=TERRA, spaceBefore=14, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName="FB", fontSize=11.5, leading=15,
                         textColor=INK, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="F", fontSize=10, leading=14.6,
                           textColor=INK, alignment=TA_JUSTIFY, spaceAfter=6),
    "li": ParagraphStyle("li", fontName="F", fontSize=10, leading=14.4,
                         textColor=INK, leftIndent=16, bulletIndent=4, spaceAfter=3),
    "li2": ParagraphStyle("li2", fontName="F", fontSize=10, leading=14.4,
                          textColor=INK, leftIndent=30, bulletIndent=18, spaceAfter=2),
    "code": ParagraphStyle("code", fontName="F", fontSize=9.5, leading=13,
                           textColor=INK, backColor=HexColor("#f6f1ec"),
                           leftIndent=10, rightIndent=10, spaceBefore=4, spaceAfter=6,
                           borderPadding=6),
    "cell": ParagraphStyle("cell", fontName="F", fontSize=8.8, leading=11.6,
                           textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName="FB", fontSize=8.8, leading=11.6,
                            textColor=TERRA),
    "toc1": ParagraphStyle("toc1", fontName="FB", fontSize=10.5, leading=17,
                           textColor=INK),
    "toc2": ParagraphStyle("toc2", fontName="F", fontSize=9.5, leading=15,
                           textColor=MUTED, leftIndent=14),
    "note": ParagraphStyle("note", fontName="F", fontSize=9, leading=13,
                           textColor=MUTED, spaceAfter=6),
}

def esc(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r'<font name="FB">\1</font>', t)
    t = re.sub(r"`(.+?)`", r'<font backColor="#f6f1ec">\1</font>', t)
    return t

def link(t):
    # [text](#anchor) -> clickable internal link
    return re.sub(r"\[([^\]]+)\]\(#([\w-]+)\)",
                  r'<link href="#\2"><font color="#a4572f"><u>\1</u></font></link>', t)

def table_style(ncols):
    return TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 1.1, TERRA),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, TERRA_LIGHT),
        ("LINEBELOW", (0, -1), (-1, -1), 1.1, TERRA),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])

AVAIL = A4[0] - 5.4 * cm

def build_table(rows):
    parsed = []
    for i, r in enumerate(rows):
        cells = re.split(r"(?<!\\)\|", r.strip().strip("|"))
        style = S["cellh"] if i == 0 else S["cell"]
        parsed.append([Paragraph(link(esc(c.strip())), style) for c in cells])
    ncol = len(parsed[0])
    # ширины: первая колонка шире
    if ncol == 2:
        widths = [AVAIL * 0.42, AVAIL * 0.58]
    elif ncol == 3:
        widths = [AVAIL * 0.27, AVAIL * 0.33, AVAIL * 0.40]
    else:
        widths = [AVAIL / ncol] * ncol
    t = Table(parsed, colWidths=widths, repeatRows=1)
    t.setStyle(table_style(ncol))
    return t

story = []
lines = open(SRC, encoding="utf-8").read().splitlines()
i = 0
in_code = False
code_buf = []
first_h1_skipped = False

while i < len(lines):
    ln = lines[i]
    if ln.strip().startswith("```"):
        if not in_code:
            in_code = True; code_buf = []
        else:
            in_code = False
            story.append(Paragraph("<br/>".join(esc(x) or "&nbsp;" for x in code_buf), S["code"]))
        i += 1; continue
    if in_code:
        code_buf.append(ln); i += 1; continue
    if not ln.strip():
        i += 1; continue
    if ln.strip() == "---":
        story.append(Spacer(1, 4)); i += 1; continue
    # таблица
    if ln.lstrip().startswith("|"):
        rows = []
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            if not re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i]):
                rows.append(lines[i])
            i += 1
        story.append(build_table(rows))
        story.append(Spacer(1, 6))
        continue
    # заголовки
    m = re.match(r"^(#{1,3})\s+(.*?)(?:\s*\{#([\w-]+)\})?\s*$", ln)
    if m:
        level, text, anchor = len(m.group(1)), m.group(2), m.group(3)
        if level == 1 and not first_h1_skipped:
            first_h1_skipped = True  # титул берём из метаданных обложки
            i += 1; continue
        if anchor:
            story.append(Paragraph(f'<a name="{anchor}"/>' + esc(text), S[f"h{min(level,3)}"]))
        else:
            story.append(Paragraph(esc(text), S[f"h{min(level,3)}"]))
        i += 1; continue
    # оглавление-ссылки (список из ссылок до ch1)
    # списки
    m = re.match(r"^(\s*)(-|\d+\.)\s+(.*)$", ln)
    if m:
        indent, bullet, text = len(m.group(1)), m.group(2), m.group(3)
        content = link(esc(text))
        if "#ch" in m.group(3):  # пункт оглавления
            style = S["toc2"] if indent else S["toc1"]
            story.append(Paragraph(content, style))
        else:
            style = S["li2"] if indent >= 2 else S["li"]
            mark = "&bull;" if bullet == "-" else bullet
            story.append(Paragraph(f"{mark}&nbsp;&nbsp;{content}", style))
        i += 1; continue
    # подзаголовок на титуле / обычный абзац
    story.append(Paragraph(link(esc(ln.strip())), S["body"]))
    i += 1

# --- обложка и колонтитулы ---
W, H = A4
COVER_META = story[:0]

def on_cover(cv, doc):
    cv.saveState()
    cv.setFillColor(TERRA)
    cv.rect(0, H - 3.2 * cm, W, 3.2 * cm, stroke=0, fill=1)
    cv.setFillColor(HexColor("#ffffff"))
    cv.setFont("FB", 13)
    cv.drawString(2.8 * cm, H - 2.1 * cm, "АГЕНТ-ЦЕХ")
    cv.setFont("F", 9)
    cv.drawString(2.8 * cm, H - 2.6 * cm, "Рабочий инструмент РЦК-консультанта · маршрут МУ-65-2024")
    cv.setFillColor(INK)
    cv.setFont("FB", 27)
    cv.drawString(2.8 * cm, H - 9.2 * cm, "Методичка пользователя")
    cv.setStrokeColor(TERRA); cv.setLineWidth(1.4)
    cv.line(2.8 * cm, H - 9.8 * cm, 9.5 * cm, H - 9.8 * cm)
    cv.setFont("F", 11)
    cv.setFillColor(MUTED)
    cv.drawString(2.8 * cm, H - 10.8 * cm, "Настоящий документ определяет порядок работы пользователя в сервисе:")
    cv.drawString(2.8 * cm, H - 11.4 * cm, "от открытия проекта до протокола выполнения мероприятий")
    cv.setFont("F", 10)
    cv.drawString(2.8 * cm, 3.0 * cm, "Редакция 3.1 · интерфейс v2.2 · 7 августа 2026 г. · Для внутреннего использования")
    cv.setFillColor(TERRA)
    cv.rect(0, 0, W, 1.2 * cm, stroke=0, fill=1)
    cv.restoreState()

def on_page(cv, doc):
    cv.saveState()
    cv.setFont("F", 8); cv.setFillColor(MUTED)
    cv.drawString(2.8 * cm, H - 1.4 * cm, "Агент-цех · Методичка пользователя")
    cv.setStrokeColor(RULE); cv.setLineWidth(0.5)
    cv.line(2.8 * cm, H - 1.6 * cm, W - 2.6 * cm, H - 1.6 * cm)
    cv.drawCentredString(W / 2, 1.1 * cm, str(doc.page))
    cv.restoreState()

doc = BaseDocTemplate(OUT, pagesize=A4,
                      leftMargin=2.8 * cm, rightMargin=2.6 * cm,
                      topMargin=2.3 * cm, bottomMargin=2.0 * cm,
                      title="Агент-цех · Методичка пользователя",
                      author="РЦК")
frame_cover = Frame(2.8 * cm, 2.0 * cm, W - 5.4 * cm, H - 4.3 * cm, id="c")
frame_page = Frame(2.8 * cm, 2.0 * cm, W - 5.4 * cm, H - 4.3 * cm, id="p")
doc.addPageTemplates([PageTemplate(id="cover", frames=[frame_cover], onPage=on_cover),
                      PageTemplate(id="page", frames=[frame_page], onPage=on_page)])

final = [Spacer(1, 1)]
from reportlab.platypus import NextPageTemplate
final.append(NextPageTemplate("page"))
final.append(PageBreak())
final.extend(story)
doc.build(final)
print("OK", OUT)
