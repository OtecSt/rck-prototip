# -*- coding: utf-8 -*-
"""С2.2: UI-прогон симулятора через CDP (headless Chromium, без playwright).

Сценарий: открыть инструмент sim, вбить эталонный поток владельца
(спрос 3500, время 7000; обработка 2/6/2/10/36/5000, покраска 3/2/2/50/5000/10000),
дождаться базы, проверить:
- строка пользы .sim-lead видна;
- «Как пользоваться и допущения модели» свёрнуто;
- у каждого ползунка есть «?» (.f-tip), наведение включает tip-fixed;
- у заголовков строк таблицы результата есть «?»;
- после ползунка Ту −20 % на УМ появляется «Итог сценария: …».
Скриншоты: _qa_c22_lead.png (шапка), _qa_c22_result.png (результат с итогом).
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
CHROME = (Path.home() / "Library/Caches/ms-playwright/chromium-1228"
          / "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS"
          / "Google Chrome for Testing")
if not CHROME.exists():
    канд = list((Path.home() / "Library/Caches/ms-playwright/chromium-1228"
                 / "chrome-mac-arm64").glob("*/Contents/MacOS/*"))
    CHROME = канд[0]

PORT_CDP = 9223


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


FILL = """
(function () {
  function setV(id, v) {
    var e = document.getElementById(id);
    e.value = v;
    e.dispatchEvent(new Event("input", {bubbles: true}));
  }
  setV("sim-поток", "Эталонный поток владельца");
  setV("sim-спрос", "3500");
  setV("sim-время", "7000");
  setV("sim-численность", "8");
  var tbody = document.getElementById("sim-ops-body");
  // имя, ту, исп, брак, перенал, партия, запас
  var ops = [
    ["обработка", "2", "6", "2", "10", "36", "5000"],
    ["покраска", "3", "2", "2", "50", "5000", "10000"]
  ];
  while (tbody.rows.length < ops.length)
    document.getElementById("sim-btn-add").click();
  ops.forEach(function (o, i) {
    var tr = tbody.rows[i];
    var cls = [".c-имя", ".c-ту", ".c-исп", ".c-брак", ".c-пер", ".c-партия", ".c-зап"];
    cls.forEach(function (c, j) {
      var e = tr.querySelector(c);
      e.value = o[j];
      e.dispatchEvent(new Event("input", {bubbles: true}));
    });
  });
  return "filled:" + tbody.rows.length;
})()
"""

CHECK_BEFORE = """
(function () {
  var lead = document.querySelector(".tool[data-tool='sim'] .sim-lead");
  var dop = document.querySelector(".tool[data-tool='sim'] details.sim-dop-all");
  var slTips = document.querySelectorAll("#sim-scen-ops .sim-sl .f-tip");
  var tbTips = document.querySelectorAll("#sim-cmp-body .f-tip");
  // имитация наведения на первый вопросик ползунка
  var t0 = slTips[0];
  var fixed0 = false;
  if (t0) {
    t0.dispatchEvent(new MouseEvent("mouseover", {bubbles: true}));
    fixed0 = t0.classList.contains("tip-fixed");
    t0.dispatchEvent(new MouseEvent("mouseout", {bubbles: true}));
  }
  var leadR = lead ? lead.getBoundingClientRect() : {width:0, height:0};
  return JSON.stringify({
    lead_text: lead ? lead.textContent.trim() : null,
    lead_visible: !!(lead && leadR.width > 0 && leadR.height > 0),
    dop_present: !!dop,
    dop_open: dop ? dop.open : null,
    dop_summary: dop ? dop.querySelector("summary").textContent.trim() : null,
    slider_tips: slTips.length,
    table_tips: tbTips.length,
    tip_fixed_works: fixed0,
    tip0_text: t0 ? t0.getAttribute("data-tip") : null
  });
})()
"""

SLIDER = """
(function () {
  // поток из _test_sim_s2: УМ — Оп2 (вторая операция), ползунок Ту −20 %
  var boxes = document.getElementById("sim-scen-ops").children;
  var inp = boxes[1].querySelector('input[type="range"]');
  inp.value = -20;
  inp.dispatchEvent(new Event("input", {bubbles: true}));
  return inp.value;
})()
"""

FILL2 = """
(function () {
  function setV(id, v) {
    var e = document.getElementById(id);
    e.value = v;
    e.dispatchEvent(new Event("input", {bubbles: true}));
  }
  setV("sim-спрос", "300");
  setV("sim-время", "480");
  setV("sim-численность", "5");
  var tbody = document.getElementById("sim-ops-body");
  while (tbody.rows.length < 3)
    document.getElementById("sim-btn-add").click();
  // поток, где выпуск ограничен мощностью УМ (Оп2), а не спросом:
  // −20 % Ту на УМ поднимает выпуск и снижает ВПП
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
  return "filled2:" + tbody.rows.length;
})()
"""

CHECK_AFTER = """
(function () {
  var v = document.getElementById("sim-verdict");
  return JSON.stringify({
    verdict_hidden: v.hidden,
    verdict_text: v.textContent,
    status: document.getElementById("sim-status-line").textContent
  });
})()
"""


async def main():
    # порт читаем из stdout app.py (свободный из 8000–8099), чтобы не
    # попасть на чужой/старый сервер на 8000
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
         "--no-first-run", "--disable-gpu", "--window-size=1500,2200",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            opened = await c.eval(
                "window.__acShowTool && window.__acShowTool('sim');"
                "!!document.querySelector('.tool[data-tool=\"sim\"]')")
            print("открытие sim:", opened)
            await asyncio.sleep(1.0)
            print("заполнение:", await c.eval(FILL))
            for _ in range(40):
                await asyncio.sleep(0.5)
                st = await c.eval(
                    "document.getElementById('sim-status-line').textContent")
                if "База посчитана" in (st or ""):
                    break
            print("статус базы:", st)
            # скриншот шапки с .sim-lead
            await c.shot(UI / "_qa_c22_lead.png",
                         sel=".tool[data-tool='sim'] .tool-head")
            res1 = json.loads(await c.eval(CHECK_BEFORE))
            print("CHECK_BEFORE:", json.dumps(res1, ensure_ascii=False, indent=1))
            # у эталонного потока владельца выпуск ограничен спросом, а ВПП —
            # буферами: ненулевых дельт выпуска/ВПП нет, строка-итог честно
            # скрыта. Для проверки строки-итога переключаемся на поток из
            # _test_sim_s2 (240/480; 1,25/1,5/1,44), где −20 % Ту на УМ
            # поднимает выпуск.
            print("заполнение 2:", await c.eval(FILL2))
            for _ in range(40):
                await asyncio.sleep(0.5)
                st = await c.eval(
                    "document.getElementById('sim-status-line').textContent")
                if "База посчитана" in (st or ""):
                    break
            print("статус базы 2:", st)
            # двигаем ползунок Ту на УМ −20 %
            print("ползунок:", await c.eval(SLIDER))
            for _ in range(40):
                await asyncio.sleep(0.5)
                st2 = await c.eval(
                    "document.getElementById('sim-status-line').textContent")
                if "Сценарий пересчитан" in (st2 or ""):
                    break
            print("статус сценария:", st2)
            res2 = json.loads(await c.eval(CHECK_AFTER))
            print("CHECK_AFTER:", json.dumps(res2, ensure_ascii=False, indent=1))
            await c.shot(UI / "_qa_c22_result.png", sel=".sim-out")
            ок = (res1["lead_visible"]
                  and res1["lead_text"].startswith("Что вы получите:")
                  and res1["dop_present"] and res1["dop_open"] is False
                  and res1["dop_summary"] == "Как пользоваться и допущения модели"
                  and res1["slider_tips"] == 8
                  and res1["table_tips"] >= 6
                  and res1["tip_fixed_works"]
                  and not res2["verdict_hidden"]
                  and res2["verdict_text"].startswith("Итог сценария:"))
            print("UI-ПРОВЕРКА:", "PASS" if ок else "FAIL")
            return 0 if ок else 1
    finally:
        chrome.terminate()
        app.terminate()
        try:
            chrome.wait(10); app.wait(10)
        except Exception:
            chrome.kill(); app.kill()


sys.exit(asyncio.run(main()))
