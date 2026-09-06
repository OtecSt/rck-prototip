// Д2.3: проверка hover-тултипов .f-tip в таблице sim (скриншоты)
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9337;
const BASE = process.env.QA_BASE || "http://localhost:8000";
function jreq(method, path) {
  return new Promise((res, rej) => {
    const r = http.request({ host: "127.0.0.1", port: PORT, path, method }, (resp) => {
      let d = ""; resp.on("data", (c) => d += c); resp.on("end", () => res(JSON.parse(d)));
    });
    r.on("error", rej); r.end();
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function main() {
  const edge = spawn(EDGE, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${PORT}`,
    "--window-size=1400,1000", "--user-data-dir=/tmp/edge-qa-d23-tips", "about:blank"], { stdio: "ignore" });
  process.on("exit", () => { try { edge.kill("SIGKILL"); } catch (e) {} });
  let target = null;
  for (let i = 0; i < 40; i++) {
    await sleep(300);
    try { target = await jreq("PUT", "/json/new?about:blank"); break; } catch (e) {}
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0; const pend = {};
  const send = (m, p) => new Promise((res) => { const i = ++id; pend[i] = res; ws.send(JSON.stringify({ id: i, method: m, params: p || {} })); });
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pend[m.id]) { pend[m.id](m.result); delete pend[m.id]; } };
  await new Promise((r) => ws.onopen = r);
  const evl = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    return r && r.result ? r.result.value : null;
  };
  const shot = async (name) => {
    const r = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(name, Buffer.from(r.data, "base64"));
  };
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(1200);
  await evl(`localStorage.setItem("agentцех_режим","full"); location.hash="#tool=sim"; location.reload(); 1`);
  await sleep(1500);
  await evl(`document.getElementById("sim-ops-table").scrollIntoView({block:"center"}); 1`);
  await sleep(300);
  const results = {};
  // hover по вопросикам колонок 0 (Операция), 1 (Ту), 4 (Перенал.)
  for (const col of [0, 1, 4]) {
    const pos = JSON.parse(await evl(`(function(){
      var th = document.querySelectorAll("#sim-ops-table th")[${col}];
      var tip = th.querySelector(".f-tip");
      var r = tip.getBoundingClientRect();
      return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2, col: ${col}});
    })()`));
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: pos.x, y: pos.y });
    await sleep(350);
    const vis = JSON.parse(await evl(`(function(){
      var th = document.querySelectorAll("#sim-ops-table th")[${col}];
      var tip = th.querySelector(".f-tip");
      var cs = getComputedStyle(tip, "::after");
      // псевдоэлемент: проверяем content и направление (top/bottom)
      return JSON.stringify({ content: cs.content.slice(0,40), top: cs.top, bottom: cs.bottom,
        clipTest: (function(){ var r2 = tip.getBoundingClientRect(); return {x:r2.x,y:r2.y}; })() });
    })()`));
    results["col" + col] = vis;
    await shot(`_qa_d23_tip_col${col}.png`);
  }
  // Тултип в таблице uzkie_mesta (внутри tab-pane)
  await evl(`window.__acShowTool("uzkie_mesta"); 1`);
  await sleep(400);
  await evl(`var t=document.querySelector('.tool[data-tool="uzkie_mesta"] table.ops'); t && t.scrollIntoView({block:"center"}); 1`);
  await sleep(300);
  const pos2 = JSON.parse(await evl(`(function(){
    var th = document.querySelector('.tool[data-tool="uzkie_mesta"] table.ops th');
    var tip = th && th.querySelector(".f-tip");
    if (!tip) return JSON.stringify(null);
    var r = tip.getBoundingClientRect();
    return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
  })()`));
  if (pos2) {
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: pos2.x, y: pos2.y });
    await sleep(350);
    await shot("_qa_d23_tip_um.png");
  }
  console.log(JSON.stringify({ results, umTip: !!pos2 }, null, 1));
  edge.kill("SIGKILL");
  process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(1); });
