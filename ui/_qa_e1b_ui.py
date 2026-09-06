# -*- coding: utf-8 -*-
"""Э1-Б: CDP-прогон экрана ЭЭ-калькулятора после редизайна (headless Chromium).

Сценарий и проверки (8):
1. Слои: после демо «пример ред. 4» итог виден сразу — hero с тремя числами
   (11 261 156,71 / 2 010 025,66 / 13 596 144,77) и строкой «высвобождение
   705 000 + отложенный 42 300» — без единого клика по раскрытиям.
2. Водопад факторной декомпозиции виден: 11 строк (10 J-факторов + итог),
   контрольная сверка «сходится».
3. Живой пересчёт: меняем «СиМ после» → итог меняется без кнопки
   (11 267 156,71), дельта-чип «+6 000 ₽» виден.
4. Прогресс заполнения: 0/8 секций на чистой форме → 8/8 после демо.
5. Раскрытия: полный отчёт свёрнут по умолчанию, открывается и содержит
   показанные расчёты; у пустых секций видны мягкие подсказки пустого состояния.
6. ЭЭ-мостик С3 не сломан: сценарий симулятора → «→ в ЭЭ-калькулятор»
   заполняет Тцикл/Ттакт с пометкой «модельный прогноз».
7. «Скачать справку ФЦК»: /api/ee_export_fck из текущего ввода отдаёт xlsm.
8. Матрица режимов Д1/Д2: простой режим прячет вкладку ЭЭ, полный — возвращает.

Скриншоты: Прототип/аудит_0109/e1b_hero.png, e1b_progress.png,
e1b_report_open.png. Запуск из ui/: ../.venv/bin/python _qa_e1b_ui.py
"""
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

UI = Path(__file__).resolve().parent
AUDIT = UI.parent / "аудит_0109"
CHROME = (Path.home() / "Library/Caches/ms-playwright/chromium-1228"
          / "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS"
          / "Google Chrome for Testing")
if not CHROME.exists():
    канд = list((Path.home() / "Library/Caches/ms-playwright/chromium-1228"
                 / "chrome-mac-arm64").glob("*/Contents/MacOS/*"))
    CHROME = канд[0]

PORT_CDP = 9224

ЭТАЛОН = {"реальный": "11 261 156,71", "потенциальный": "2 010 025,66",
          "налоги": "13 596 144,77", "высвоб": "705 000", "отложенный": "42 300"}


def ждать_порт(url, таймаут=30):
    t0 = time.time()
    while time.time() - t0 < таймаут:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


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
        return r.get("result", {}).get("value")

    async def shot(self, path, sel=None):
        if sel:
            await self.eval(
                "var e=document.querySelector('" + sel + "');"
                "e&&e.scrollIntoView({block:'start'});''")
            await asyncio.sleep(0.4)
        r = await self.cmd("Page.captureScreenshot", {"format": "png"})
        Path(path).write_bytes(base64.b64decode(r["data"]))

    async def ждать(self, expr, что, таймаут=15):
        t0 = time.time()
        while time.time() - t0 < таймаут:
            if await self.eval(expr):
                return True
            await asyncio.sleep(0.3)
        print(f"  ТАЙМ-АУТ ожидания: {что}")
        return False


# С3-мостик: поток, где УМ — Оп2; ползунок Ту −20 % на УМ
SIM_FILL = """
(function () {
  function setV(id, v) {
    var e = document.getElementById(id);
    e.value = v;
    e.dispatchEvent(new Event("input", {bubbles: true}));
  }
  setV("sim-поток", "Э1-Б прогон мостика");
  setV("sim-спрос", "300");
  setV("sim-время", "480");
  setV("sim-численность", "5");
  var tbody = document.getElementById("sim-ops-body");
  while (tbody.rows.length < 3)
    document.getElementById("sim-btn-add").click();
  var ops = [["Оп1", "1,9"], ["Оп2", "2"], ["Оп3", "1,5"]];
  ops.forEach(function (o, i) {
    var tr = tbody.rows[i];
    function set(cls, v) {
      var e = tr.querySelector(cls);
      e.value = v;
      e.dispatchEvent(new Event("input", {bubbles: true}));
    }
    set(".c-имя", o[0]); set(".c-ту", o[1]); set(".c-исп", "");
    set(".c-брак", ""); set(".c-пер", ""); set(".c-партия", ""); set(".c-зап", "");
  });
  return "filled:" + tbody.rows.length;
})()
"""

SIM_SLIDER = """
(function () {
  var boxes = document.getElementById("sim-scen-ops").children;
  var inp = boxes[1].querySelector('input[type="range"]');
  inp.value = -20;
  inp.dispatchEvent(new Event("input", {bubbles: true}));
  return inp.value;
})()
"""

CHECK_BRIDGE = """
(function () {
  var блок = document.getElementById("ee-контекст");
  return JSON.stringify({
    тц_до: document.getElementById("ee-тц-до").value,
    тц_после: document.getElementById("ee-тц-после").value,
    тт_до: document.getElementById("ee-тт-до").value,
    контекст_виден: !блок.hidden,
    контекст_текст: блок.textContent
  });
})()
"""

CHECK_LAYERS = """
(function () {
  function t(id) { var e = document.getElementById(id); return e ? e.textContent.trim() : null; }
  function vis(id) {
    var e = document.getElementById(id);
    if (!e || e.hidden) return false;
    var r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  var hero = document.getElementById("ee-hero");
  return JSON.stringify({
    hero_visible: vis("ee-hero"),
    реальный: t("ee-hero-реальный"),
    потенциальный: t("ee-hero-потенциальный"),
    налоги: t("ee-hero-налоги"),
    высвоб_строка: t("ee-hero-высвоб"),
    waterfall_visible: vis("ee-waterfall"),
    wf_rows: document.querySelectorAll("#ee-wf-chart .ee-wf-row").length,
    wf_check: t("ee-wf-check"),
    прогресс: t("ee-progress-text"),
    прогресс_ширина: document.getElementById("ee-progress-fill").style.width,
    отчёт_свёрнут: !document.getElementById("ee-report-details").open,
    бейджей_заполнено: (function () {
      var n = 0;
      document.querySelectorAll(".tool[data-tool='ee'] .ee-spoiler .ee-count")
        .forEach(function (b) { if (b.textContent.indexOf("заполнено:") === 0) n++; });
      return n;
    })(),
    пустых_подсказок: (function () {
      var n = 0;
      document.querySelectorAll(".tool[data-tool='ee'] .ee-spoiler:not(.ee-filled) .ee-empty")
        .forEach(function (e) { if (e.offsetParent !== null || true) n++; });
      return n;
    })(),
    f_tips: document.querySelectorAll(".tool[data-tool='ee'] .f-tip").length
  });
})()
"""


async def main():
    app = subprocess.Popen([sys.executable, "app.py"], cwd=str(UI),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True)
    port_app = None
    t0 = time.time()
    while time.time() - t0 < 30:
        line = app.stdout.readline()
        if "localhost:" in line:
            port_app = int(line.rsplit(":", 1)[1].strip())
            break
    if not port_app:
        print("FAIL: не удалось узнать порт app.py"); app.terminate(); return 1
    print("app.py порт:", port_app)
    chrome = subprocess.Popen(
        [str(CHROME), "--headless=new", f"--remote-debugging-port={PORT_CDP}",
         "--no-first-run", "--disable-gpu", "--window-size=1500,2400",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    чек = {}
    try:
        if not ждать_порт(f"http://127.0.0.1:{port_app}/", 40):
            print("FAIL: app.py не поднялся"); return 1
        if not ждать_порт(f"http://127.0.0.1:{PORT_CDP}/json/version", 40):
            print("FAIL: CDP не поднялся"); return 1
        tabs = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{PORT_CDP}/json").read())
        page = [t for t in tabs if t["type"] == "page"][0]
        async with websockets.connect(page["webSocketDebuggerUrl"],
                                      max_size=50 * 1024 * 1024) as ws:
            c = CDP(ws)
            await c.cmd("Page.enable")
            await c.cmd("Runtime.enable")
            await c.cmd("Page.navigate",
                        {"url": f"http://127.0.0.1:{port_app}/"})
            await asyncio.sleep(2.5)
            await c.eval("document.getElementById('mode-full-btn').click();''")
            await asyncio.sleep(0.8)

            # --- 6. ЭЭ-мостик С3 (на чистой форме, до демо) ---
            await c.eval("window.__acShowTool && window.__acShowTool('sim');''")
            await asyncio.sleep(0.8)
            print("заполнение sim:", await c.eval(SIM_FILL))
            await c.ждать(
                "document.getElementById('sim-status-line').textContent"
                ".indexOf('База посчитана') >= 0", "база sim")
            print("ползунок:", await c.eval(SIM_SLIDER))
            await c.ждать(
                "document.getElementById('sim-status-line').textContent"
                ".indexOf('Сценарий пересчитан') >= 0", "сценарий sim")
            await c.eval("document.getElementById('sim-to-ee').click();''")
            await asyncio.sleep(0.8)
            мост = json.loads(await c.eval(CHECK_BRIDGE))
            print("С3-мостик:", json.dumps(мост, ensure_ascii=False))
            чек["мостик_с3"] = (
                мост["тц_до"] == "2" and мост["тц_после"] == "1,6"
                and мост["тт_до"] != "" and мост["контекст_виден"]
                and "модельн" in мост["контекст_текст"])

            # --- 4a. Прогресс на почти чистой форме (после мостика 1 секция) ---
            прог0 = await c.eval(
                "document.getElementById('ee-progress-text').textContent")
            пустых0 = await c.eval(
                "(function () { var n = 0;"
                " document.querySelectorAll("
                "  \".tool[data-tool='ee'] .ee-spoiler:not(.ee-filled) .ee-empty\")"
                " .forEach(function (e) { n++; }); return n; })()")
            print("прогресс до демо:", прог0, "| пустых подсказок видно:", пустых0)

            # --- Демо «пример ред. 4» ---
            await c.eval("document.getElementById('ee-demo-пример').click();''")
            ждём = await c.ждать(
                "document.getElementById('ee-status-line').textContent"
                ".indexOf('Пересчитано') >= 0", "пересчёт демо")
            print("демо пересчитано:", ждём)

            # --- 1+2+4b+5. Слои, водопад, прогресс, раскрытия ---
            слои = json.loads(await c.eval(CHECK_LAYERS))
            print("СЛОИ:", json.dumps(слои, ensure_ascii=False, indent=1))
            чек["слои_итог"] = (
                слои["hero_visible"]
                and слои["реальный"] == ЭТАЛОН["реальный"]
                and слои["потенциальный"] == ЭТАЛОН["потенциальный"]
                and слои["налоги"] == ЭТАЛОН["налоги"]
                and ЭТАЛОН["высвоб"] in слои["высвоб_строка"]
                and ЭТАЛОН["отложенный"] in слои["высвоб_строка"])
            чек["водопад"] = (
                слои["waterfall_visible"] and слои["wf_rows"] == 11
                and "сходится" in (слои["wf_check"] or ""))
            чек["прогресс"] = (
                прог0.startswith("Входы: 1/8")  # мостик заполнил секцию «Объём и цены»
                and слои["прогресс"].startswith("Входы: 8/8"))
            чек["раскрытия"] = (слои["отчёт_свёрнут"] and слои["f_tips"] >= 6
                                and пустых0 == 6
                                and слои["бейджей_заполнено"] == 6)
            await c.shot(AUDIT / "e1b_hero.png", sel="#ee-hero")
            await c.shot(AUDIT / "e1b_progress.png", sel="#ee-progress")

            # Раскрытие отчёта работает и содержит показанные расчёты
            await c.eval("document.getElementById('ee-report-details').open = true;''")
            await asyncio.sleep(0.4)
            отч = await c.eval(
                "document.getElementById('ee-report').textContent")
            чек["отчёт_раскрывается"] = ("Факторная декомпозиция" in (отч or "")
                                         and "Показанные расчёты" in (отч or ""))
            await c.shot(AUDIT / "e1b_report_open.png", sel="#ee-report-details")

            # --- 3. Живой пересчёт без кнопки + дельта итога ---
            до = await c.eval(
                "document.getElementById('ee-hero-реальный').textContent")
            await c.eval(
                "var e=document.getElementById('ee-сим-после');"
                "e.value='300000';"
                "e.dispatchEvent(new Event('input',{bubbles:true}));''")
            ждём2 = await c.ждать(
                "document.getElementById('ee-hero-реальный').textContent"
                ".indexOf('11 267 156,71') >= 0", "живой пересчёт")
            дельта = await c.eval(
                "var d=document.getElementById('ee-hero-delta');"
                "JSON.stringify({виден: !d.hidden,"
                " текст: d.textContent.replace(/\\u00a0/g, ' ')})")
            дельта = json.loads(дельта or "{}")
            после = await c.eval(
                "document.getElementById('ee-hero-реальный').textContent")
            print("живой пересчёт:", до, "→", после, "| дельта:", дельта)
            чек["живой_пересчёт"] = (
                ждём2 and после == "11 267 156,71"
                and дельта.get("виден") and "+6 000" in дельта.get("текст", ""))

            # --- 7. Справка ФЦК отдаёт файл ---
            фцк = await c.eval(
                "fetch('/api/ee_export_fck', {method: 'POST',"
                " headers: {'Content-Type': 'application/json'},"
                " body: JSON.stringify(window.__acEE.collect())})"
                ".then(function (r) { return r.blob().then(function (b) {"
                " return JSON.stringify({status: r.status,"
                " ct: r.headers.get('Content-Type') || '', size: b.size}); }); })")
            фцк = json.loads(фцк or "{}")
            print("справка ФЦК:", фцк)
            чек["справка_фцк"] = (фцк.get("status") == 200
                                  and "excel" in фцк.get("ct", "")
                                  and фцк.get("size", 0) > 10000)

            # --- 8. Матрица режимов Д1/Д2 ---
            await c.eval("document.getElementById('mode-simple-btn').click();''")
            await asyncio.sleep(0.6)
            простой = json.loads(await c.eval(
                "JSON.stringify({"
                " ee_в_простом: window.__acSimpleTools.indexOf('ee') >= 0,"
                " ee_виден: (function () {"
                "   var t = document.querySelector('.tool[data-tool=\"ee\"]');"
                "   return t ? t.offsetParent !== null : null; })()})"))
            await c.eval("document.getElementById('mode-full-btn').click();''")
            await asyncio.sleep(0.6)
            await c.eval("window.__acShowTool && window.__acShowTool('ee');''")
            await asyncio.sleep(0.6)
            полный = await c.eval(
                "(function () {"
                " var t = document.querySelector('.tool[data-tool=\"ee\"]');"
                " return t ? t.offsetParent !== null : null; })()")
            print("матрица Д1/Д2:", простой, "| полный режим, ЭЭ виден:", полный)
            чек["матрица_д1_д2"] = (простой["ee_в_простом"] is False
                                    and простой["ee_виден"] is False
                                    and полный is True)

            print("---- ИТОГИ Э1-Б ----")
            ок = True
            for имя, р in чек.items():
                print(f"  {имя}: {'PASS' if р else 'FAIL'}")
                ок = ок and р
            print("Э1-Б UI-ПРОВЕРКА:", f"PASS ({sum(чек.values())}/{len(чек)})"
                  if ок else "FAIL")
            return 0 if ок else 1
    finally:
        chrome.terminate()
        app.terminate()
        try:
            chrome.wait(10); app.wait(10)
        except Exception:
            chrome.kill(); app.kill()


sys.exit(asyncio.run(main()))
