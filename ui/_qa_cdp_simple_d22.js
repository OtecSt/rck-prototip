// QA Д2.2: простой режим — 4 инструмента кликабельны, чужой шапки нет.
const { spawn } = require("child_process");
const http = require("http");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9334;
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
    "--user-data-dir=/tmp/edge-qa-d22", "about:blank"], { stdio: "ignore" });
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
  await send("Page.enable");
  // Старт в полном режиме
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(1200);
  await evl(`localStorage.setItem("agentцех_режим","full"); location.hash="#tool=sim"; location.reload(); 1`);
  await sleep(1500);
  const fullSim = await evl(`JSON.stringify({
    wzHidden: document.getElementById("wz-head").hidden,
    wzTitle: document.getElementById("wz-title").textContent,
    simVisible: !!document.querySelector('.tool[data-tool="sim"]') && document.querySelector('.tool[data-tool="sim"]').offsetHeight > 0
  })`);
  // Переключаемся в простой режим (сценарий бага двойной шапки)
  await evl(`document.getElementById("mode-simple-btn").click(); 1`);
  await sleep(400);
  const simpleHead = await evl(`JSON.stringify({
    wzHidden: document.getElementById("wz-head").hidden,
    wzHeight: document.getElementById("wz-head").offsetHeight,
    simpleVisible: !document.getElementById("simple-start").hidden,
    title: document.querySelector("#simple-start .simple-title").textContent
  })`);
  // Кликаем каждый из 4 пунктов простого режима
  const out = {};
  for (const tk of ["uzkie_mesta", "vsm", "potok_calc", "oee"]) {
    await evl(`document.querySelector('.sn-tool[data-tool="${tk}"]').click(); 1`);
    await sleep(300);
    out[tk] = JSON.parse(await evl(`JSON.stringify({
      inHost: !!document.querySelector('#simple-host .tool[data-tool="${tk}"]'),
      visible: (function(){var t=document.querySelector('#simple-host .tool[data-tool="${tk}"]'); return !!t && t.offsetHeight>0;})(),
      title: document.querySelector("#simple-start .simple-title").textContent,
      wzHidden: document.getElementById("wz-head").hidden,
      fullHidden: document.getElementById("full-mode").style.display === "none"
    })`));
  }
  // Возврат в полный режим — всё на месте
  await evl(`document.getElementById("mode-to-full").click(); 1`);
  await sleep(400);
  const back = JSON.parse(await evl(`JSON.stringify({
    hostEmpty: document.getElementById("simple-host").children.length === 0,
    umHome: !!document.querySelector('#full-mode .tool[data-tool="uzkie_mesta"]'),
    wzHidden: document.getElementById("wz-head").hidden
  })`));
  console.log(JSON.stringify({ fullSim: JSON.parse(fullSim), simpleHead: JSON.parse(simpleHead), clicks: out, backToFull: back }, null, 1));
  edge.kill("SIGKILL");
  process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(1); });
