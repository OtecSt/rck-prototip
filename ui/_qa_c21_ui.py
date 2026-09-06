# -*- coding: utf-8 -*-
"""С2.1: UI-прогон симулятора через CDP (headless Chromium, без playwright).

Сценарий: открыть инструмент sim, вбить эталонный поток (спрос 240, время
480, операции 1,25/1,5/1,44 с запасами — такт 2,00), дождаться базы,
сдвинуть ползунок Ту на не-УМ (первая операция) на −20 %, проверить:
- появилось пояснение нулевой дельты (#sim-zero-note),
- у УМ (вторая операция) есть метка «⚑ узкое место» (.sim-um-flag).
Скриншоты: _qa_c21_sim_um_mark.png (панель сценария),
           _qa_c21_sim_zero_delta.png (таблица сравнения).
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

PORT_APP = 8000
PORT_CDP = 9222


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
  setV("sim-поток", "Тестовый поток");
  setV("sim-спрос", "240");
  setV("sim-время", "480");
  setV("sim-численность", "5");
  var tbody = document.getElementById("sim-ops-body");
  // эталон: Оп1 1,25 запас 2000; Оп2 1,5 запас 700; Оп3 1,44 запас 800
  var ops = [["Оп1", "1,25", "2000"], ["Оп2", "1,5", "700"], ["Оп3", "1,44", "800"]];
  while (tbody.rows.length < ops.length)
    document.getElementById("sim-btn-add").click();
  ops.forEach(function (o, i) {
    var tr = tbody.rows[i];
    function set(cls, v) {
      var e = tr.querySelector(cls);
      e.value = v;
      e.dispatchEvent(new Event("input", {bubbles: true}));
    }
    set(".c-имя", o[0]); set(".c-ту", o[1]); set(".c-зап", o[2]);
  });
  return "filled:" + tbody.rows.length;
})()
"""

SLIDER = """
(function () {
  var box = document.getElementById("sim-scen-ops").children[0]; // Оп1 — не УМ
  var inp = box.querySelector('input[type="range"]');            // Ту
  inp.value = -20;
  inp.dispatchEvent(new Event("input", {bubbles: true}));
  return inp.value;
})()
"""

CHECK = """
(function () {
  var note = document.getElementById("sim-zero-note");
  var flags = document.querySelectorAll(".sim-um-flag");
  var zeros = document.querySelectorAll("#sim-cmp-body td.dl-zero");
  var names = Array.prototype.map.call(
    document.querySelectorAll("#sim-scen-ops .sim-scen-name"),
    function (h) { return h.textContent; });
  return JSON.stringify({
    note_hidden: note.hidden,
    note_text: note.textContent,
    flags: flags.length,
    zero_cells: zeros.length,
    scen_names: names,
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
            # полный режим (иначе showTool скрыт), затем инструмент sim
            await c.eval("document.getElementById('mode-full-btn').click();''")
            await asyncio.sleep(0.8)
            # открыть инструмент sim
            opened = await c.eval(
                "window.__acShowTool && window.__acShowTool('sim');"
                "!!document.querySelector('.tool[data-tool=\"sim\"]')")
            print("открытие sim:", opened)
            await asyncio.sleep(1.0)
            print("заполнение:", await c.eval(FILL))
            # ждём базу (дебаунс 500 мс + 10 прогонов на сервере)
            for _ in range(40):
                await asyncio.sleep(0.5)
                st = await c.eval(
                    "document.getElementById('sim-status-line').textContent")
                if "База посчитана" in (st or ""):
                    break
            print("статус базы:", st)
            # скриншот панели сценария с меткой УМ (до движения ползунка)
            print("rect .sim-scen:", await c.eval(
                "var e=document.querySelector('.sim-scen');"
                "var r=e.getBoundingClientRect();"
                "JSON.stringify({w:r.width,h:r.height,vis:e.offsetParent!==null})"))
            await c.shot(UI / "_qa_c21_sim_um_mark.png", sel=".sim-scen")
            # двигаем ползунок Ту на не-УМ −20 %
            print("ползунок:", await c.eval(SLIDER))
            for _ in range(40):
                await asyncio.sleep(0.5)
                st2 = await c.eval(
                    "document.getElementById('sim-status-line').textContent")
                if "Сценарий пересчитан" in (st2 or ""):
                    break
            print("статус сценария:", st2)
            res = json.loads(await c.eval(CHECK))
            print("CHECK:", json.dumps(res, ensure_ascii=False, indent=1))
            await c.shot(UI / "_qa_c21_sim_zero_delta.png", sel=".sim-out")
            ок = (not res["note_hidden"] and res["flags"] == 1
                  and res["zero_cells"] >= 1
                  and "улучшение не на узком месте" in res["note_text"])
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
