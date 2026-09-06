# -*- coding: utf-8 -*-
"""П4: UI-прогон вкладки «Презентации» через CDP (headless Chromium).

Сценарий: поднимается app.py на порту 8003 на ВРЕМЕННОЙ БД (рабочая
agent_ceh.db не трогается, временные docx/pptx — в tempdir), через API
создаётся проект с полным набором прогонов (та же фикстура, что в
_test_preza_p2.py: поток-эталон, ОКЗ «слепой», симуляция до/после,
ЭЭ НОВОХРОМ, OEE-эталон, мероприятия, SMART, протокол Кушкуль).

Проверки:
  1. Пункт меню «Презентации» виден в полном режиме; клик открывает карточку;
  2. Титул подтянулся из карточки проекта (предприятие/поток заполнены);
  3. «Собрать защиту» → 8 карточек .pr-slide, лог пуст и скрыт, первый и
     последний слайды тёмные (.pr-dark);
  4. POST /api/preza/pptx (urllib) → файл > 30 КБ;
  5. «Сохранить прогон в проект» → в /api/proekty/<pid> появился прогон preza;
  6. Простой режим: пункт меню скрыт (display:none);
  7. Без проекта: #pr-empty виден, кнопки disabled.

Скриншоты: _qa_p4_menu.png, _qa_p4_preview.png, _qa_p4_dark.png.
"""
import asyncio
import base64
import copy
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

UI = Path(__file__).resolve().parent
PROT = UI.parent
CHROME = (Path.home() / "Library/Caches/ms-playwright/chromium-1228"
          / "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS"
          / "Google Chrome for Testing")
if not CHROME.exists():
    канд = list((Path.home() / "Library/Caches/ms-playwright/chromium-1228"
                 / "chrome-mac-arm64").glob("*/Contents/MacOS/*"))
    CHROME = канд[0]

PORT_APP = 8003
PORT_CDP = 9223
BASE = f"http://127.0.0.1:{PORT_APP}"

результаты = []


def итог(проверка, статус, детали=""):
    результаты.append((проверка, статус, детали))
    print(f"[{статус}] {проверка} {детали}")


def ждать_порт(url, таймаут=40):
    t0 = time.time()
    while time.time() - t0 < таймаут:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read())


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.mid = 0

    async def cmd(self, method, params=None):
        self.mid += 1
        mid = self.mid
        await self.ws.send(json.dumps(
            {"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def eval(self, expr):
        r = await self.cmd("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS: {r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    async def shot(self, path, sel=None):
        if sel:
            await self.eval(
                "var e=document.querySelector('" + sel + "');"
                "e&&e.scrollIntoView({block:'start'});''")
            await asyncio.sleep(0.4)
        r = await self.cmd("Page.captureScreenshot", {"format": "png"})
        Path(path).write_bytes(base64.b64decode(r["data"]))


# --- Фикстура прогонов (та же, что _test_preza_p2.py) -----------------------
ЭТАЛОН = {"поток": "Тестовый поток", "спрос_шт_в_период": 240,
          "доступное_время_мин": 480, "численность_чел": 5,
          "операции": [
              {"имя": "Оп1", "тц_мин": 1.25, "запас_после_шт": 2000},
              {"имя": "Оп2", "тц_мин": 1.5, "запас_после_шт": 700},
              {"имя": "Оп3", "тц_мин": 1.44, "запас_после_шт": 800}]}
СИМ_ДО = {"поток": "Тестовый поток", "спрос_шт_в_период": 240,
          "доступное_время_мин": 480,
          "операции": [{"имя": "Оп1", "тц_мин": 1.25, "запас_после_шт": 0},
                       {"имя": "Оп2", "тц_мин": 2.4, "запас_после_шт": 0},
                       {"имя": "Оп3", "тц_мин": 2.2, "запас_после_шт": 0}],
          "симуляция": {"seed": 1, "прогонов": 10}}
СИМ_ПОСЛЕ = copy.deepcopy(СИМ_ДО)
СИМ_ПОСЛЕ["операции"][1]["тц_мин"] = round(2.4 * 0.8, 4)
ЭТАЛОН_OEE = {"поток": "Тестовый поток", "плановое_время_мин": 480,
              "простои": {"аварии_мин": 47, "переналадка_мин": 38,
                          "микроостановки_мин": 22},
              "идеальное_тц_мин": 1.0, "выпуск_всего_шт": 350, "брак_шт": 12}
ЭТАЛОН_МЕР = {"predpriyatie": "Тест-завод", "uchastok": "фасовка",
              "vpp_pct": 38.7, "norma_vpp_pct": 15.0,
              "razryv": {"value": 23.7, "unit": "п.п. ВПП", "evidence": "fact"},
              "priznaki": {"простои_оборудования": True,
                           "организация_рабочих_мест": True},
              "vidy_potery": [{"nazvanie": "Ожидание"}],
              "zamery": {}}
ЭТАЛОН_SMART = {"рамка": "федеральная", "предприятие": "Тест-завод",
                "поток": "Тестовый поток",
                "цели": [{"наименование": "Выработка", "ед": "шт/чел",
                          "текущий": 10, "целевой": 12, "срок": "2026-12-31"}]}


def подготовить_проект():
    """Проект с полным набором прогонов через HTTP API. Возвращает pid."""
    _, j = post("/api/proekty", {"название": "QA П4 преза",
                                 "предприятие": "Тест-завод",
                                 "поток": "Тестовый поток"})
    pid = j["id"]

    def сохранить(инструмент, вход, метка=None):
        body = {"id_proekta": pid, "инструмент": инструмент, "вход": вход}
        if метка:
            body["метка"] = метка
        _, j = post("/api/progony", body)
        assert j.get("ok"), f"прогон {инструмент} не сохранился: {j}"

    сохранить("potok_calc", ЭТАЛОН)
    сохранить("uzkie_mesta",
              json.load(open(PROT / "данные_окз_слепой.json", encoding="utf-8")))
    сохранить("simulation", СИМ_ДО, метка="до")
    сохранить("simulation", СИМ_ПОСЛЕ, метка="после")
    сохранить("ee", json.load(open(PROT / "данные_ээ_новохром.json",
                                   encoding="utf-8")))
    сохранить("oee", ЭТАЛОН_OEE)
    сохранить("meropriyatiya", ЭТАЛОН_МЕР)
    сохранить("smart", ЭТАЛОН_SMART)
    сохранить("protokol",
              json.load(open(PROT / "данные_протокол_кушкуль.json",
                             encoding="utf-8")))
    return pid


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="preza_p4_qa_"))
    (tmp / "test.db").touch()
    runner = tmp / "runner.py"
    runner.write_text(
        "import sys; sys.path.insert(0, r'%s')\n"
        "import app\n"
        "app.DB_PATH = __import__('pathlib').Path(r'%s')\n"
        "app.ФАЙЛЫ_DIR = __import__('pathlib').Path(r'%s')\n"
        "app.init_db()\n"
        "app.app.run(host='127.0.0.1', port=%d, debug=False)\n"
        % (UI, tmp / "test.db", tmp / "файлы", PORT_APP),
        encoding="utf-8")
    (tmp / "файлы").mkdir(exist_ok=True)
    app = subprocess.Popen([sys.executable, str(runner)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = None
    try:
        if not ждать_порт(BASE + "/api/proekty"):
            print("FAIL: app.py не поднялся на :8003")
            return 1
        pid = подготовить_проект()
        print("проект №", pid, "создан (9 прогонов)")

        # PPTX напрямую (без браузера): файл > 30 КБ
        req = urllib.request.Request(
            BASE + "/api/preza/pptx",
            data=json.dumps({"проект_id": pid}, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            pptx = r.read()
        итог("PPTX через API: 200, файл > 30 КБ",
             "PASS" if len(pptx) > 30 * 1024 else "FAIL",
             f"{len(pptx)} байт")
        (tmp / "защита.pptx").write_bytes(pptx)

        chrome = subprocess.Popen(
            [str(CHROME), "--headless=new",
             f"--remote-debugging-port={PORT_CDP}",
             "--no-first-run", "--disable-gpu", "--window-size=1500,2400",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not ждать_порт(f"http://127.0.0.1:{PORT_CDP}/json/version"):
            print("FAIL: CDP не поднялся")
            return 1
        tabs = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{PORT_CDP}/json").read())
        page = [t for t in tabs if t["type"] == "page"][0]
        async with websockets.connect(page["webSocketDebuggerUrl"],
                                      max_size=50 * 1024 * 1024) as ws:
            c = CDP(ws)
            await c.cmd("Page.enable")
            await c.cmd("Runtime.enable")
            await c.cmd("Page.navigate", {"url": BASE + "/"})
            await asyncio.sleep(2.5)

            # --- 7. Без проекта: пустое состояние ---
            await c.eval("document.getElementById('mode-full-btn').click();''")
            await asyncio.sleep(0.6)
            await c.eval(
                "var s=document.getElementById('pj-select');s.value='';"
                "s.dispatchEvent(new Event('change',{bubbles:true}));''")
            await asyncio.sleep(0.5)
            await c.eval(
                "document.querySelector('.sn-tool[data-tool=\"preza\"]').click();''")
            await asyncio.sleep(1.0)
            пусто = await c.eval(
                "JSON.stringify({empty: !document.getElementById('pr-empty').hidden,"
                " build: document.getElementById('pr-build').disabled,"
                " dl: document.getElementById('pr-download').disabled})")
            пусто = json.loads(пусто)
            итог("без проекта: #pr-empty виден, кнопки disabled",
                 "PASS" if пусто["empty"] and пусто["build"] and пусто["dl"]
                 else "FAIL", json.dumps(пусто))

            # --- выбираем проект, открываем вкладку ---
            await c.eval(
                "var s=document.getElementById('pj-select');s.value='%d';"
                "s.dispatchEvent(new Event('change',{bubbles:true}));''" % pid)
            await asyncio.sleep(1.2)
            await c.eval(
                "document.querySelector('.sn-tool[data-tool=\"preza\"]').click();''")
            await asyncio.sleep(1.2)
            открыто = await c.eval(
                "JSON.stringify({card: document.getElementById('preza-card')"
                "  .style.display !== 'none',"
                " empty: document.getElementById('pr-empty').hidden,"
                " пред: document.getElementById('pr-titul-предприятие').value,"
                " поток: document.getElementById('pr-titul-поток').value})")
            открыто = json.loads(открыто)
            итог("меню: клик открывает карточку, #pr-empty скрыт",
                 "PASS" if открыто["card"] and открыто["empty"] else "FAIL",
                 json.dumps(открыто, ensure_ascii=False))
            итог("титул подтянут из карточки проекта",
                 "PASS" if открыто["пред"] == "Тест-завод"
                 and открыто["поток"] == "Тестовый поток" else "FAIL",
                 f"предприятие={открыто['пред']!r} поток={открыто['поток']!r}")
            await c.shot(UI / "_qa_p4_menu.png", sel="#preza-card .tool-head")

            # --- 3. Сборка ---
            await c.eval("document.getElementById('pr-build').click();''")
            for _ in range(40):
                await asyncio.sleep(0.5)
                st = await c.eval(
                    "document.getElementById('pr-status').textContent")
                if "Собрано" in (st or "") or "ошибка" in (st or "").lower():
                    break
            собрано = json.loads(await c.eval(
                "JSON.stringify({slides: document.querySelectorAll("
                "  '#pr-preview .pr-slide').length,"
                " dark: document.querySelectorAll("
                "  '#pr-preview .pr-slide.pr-dark').length,"
                " log_hidden: document.getElementById('pr-log').hidden,"
                " dl: document.getElementById('pr-download').disabled,"
                " zone: document.getElementById('pr-result-zone').hidden,"
                " first_dark: document.querySelector('#pr-preview .pr-slide')"
                "  .classList.contains('pr-dark'),"
                " last_dark: document.querySelector('#pr-preview .pr-slide"
                ":last-child').classList.contains('pr-dark'),"
                " src: !!document.querySelector('#pr-preview .pr-src'),"
                " status: document.getElementById('pr-status').textContent})"))
            итог("сборка: 8 слайдов, лог пуст и скрыт, «Скачать PPTX» активна",
                 "PASS" if собрано["slides"] == 8 and собрано["log_hidden"]
                 and not собрано["dl"] and not собрано["zone"] else "FAIL",
                 json.dumps(собрано, ensure_ascii=False))
            итог("тёмные слайды: первый и последний (титул/выводы)",
                 "PASS" if собрано["dark"] == 2 and собрано["first_dark"]
                 and собрано["last_dark"] else "FAIL",
                 f"dark={собрано['dark']}")
            итог("трассировка: у слайдов есть строка «источник: прогон № N»",
                 "PASS" if собрано["src"] else "FAIL")
            print("  статус:", собрано["status"])
            await c.shot(UI / "_qa_p4_preview.png", sel="#pr-preview")
            await c.shot(UI / "_qa_p4_dark.png",
                         sel="#pr-preview .pr-slide:last-child")

            # --- 5. Сохранение прогона preza ---
            await c.eval(
                "document.getElementById('save-preza-коммент').value="
                "'QA П4';document.getElementById('save-preza-btn').click();''")
            for _ in range(30):
                await asyncio.sleep(0.5)
                st = await c.eval(
                    "document.getElementById('save-preza-status').textContent")
                if "сохранён" in (st or "") or "не сохранено" in (st or ""):
                    break
            with urllib.request.urlopen(f"{BASE}/api/proekty/{pid}",
                                        timeout=10) as r:
                пр = json.loads(r.read())
            есть_preza = any(g["инструмент"] == "preza"
                             for g in пр["progony"])
            итог("прогон preza сохранён в проект (история)",
                 "PASS" if "сохранён" in (st or "") and есть_preza else "FAIL",
                 f"статус={st!r}, прогонов preza: "
                 f"{sum(1 for g in пр['progony'] if g['инструмент'] == 'preza')}")

            # --- 6. Простой режим: пункт меню скрыт ---
            await c.eval(
                "document.getElementById('mode-simple-btn').click();''")
            await asyncio.sleep(0.8)
            скрыт = await c.eval(
                "getComputedStyle(document.querySelector("
                "'.sn-tool[data-tool=\"preza\"]')).display === 'none'")
            итог("простой режим: пункт «Презентации» скрыт",
                 "PASS" if скрыт else "FAIL")
            await c.eval(
                "document.getElementById('mode-full-btn').click();''")

        провалено = sum(1 for _, s, _ in результаты if s == "FAIL")
        print(f"\nИТОГ: {len(результаты) - провалено}/{len(результаты)} PASS")
        return 1 if провалено else 0
    finally:
        if chrome:
            chrome.terminate()
        app.terminate()
        try:
            if chrome:
                chrome.wait(10)
            app.wait(10)
        except Exception:
            if chrome:
                chrome.kill()
            app.kill()


sys.exit(asyncio.run(main()))
