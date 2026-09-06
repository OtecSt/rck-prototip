// Репродукция Д2.3: баг №1 — старт в простом режиме → полный → «Поиск узкого места»
const { spawn } = require("child_process");
const http = require("http");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9335;
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
    "--user-data-dir=/tmp/edge-qa-d23-repro", "about:blank"], { stdio: "ignore" });
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
    if (r && r.exceptionDetails) return "EXC:" + JSON.stringify(r.exceptionDetails.exception && r.exceptionDetails.exception.description || r.exceptionDetails.text);
    return r && r.result ? r.result.value : null;
  };
  await send("Page.enable");
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(1200);
  // Сценарий владельца: предыдущая сессия была в простом режиме
  await evl(`localStorage.setItem("agentцех_режим","simple"); location.reload(); 1`);
  await sleep(1500);
  // Кликаем все 4 инструмента простого режима
  for (const tk of ["vsm", "potok_calc", "oee", "uzkie_mesta"]) {
    await evl(`var it=document.querySelector('.sn-tool[data-tool="${tk}"]'); it && it.click(); 1`);
    await sleep(250);
  }
  const simpleState = await evl(`JSON.stringify({
    hostKids: document.getElementById("simple-host").children.length,
    umInHost: !!document.querySelector('#simple-host .tool[data-tool="uzkie_mesta"]')
  })`);
  // Переходим в полный режим
  await evl(`document.getElementById("mode-full-btn").click(); 1`);
  await sleep(600);
  const fullState = JSON.parse(await evl(`JSON.stringify({
    umInStages: !!document.querySelector('.stages .tool[data-tool="uzkie_mesta"]'),
    umInHost: !!document.querySelector('#simple-host .tool[data-tool="uzkie_mesta"]'),
    hostKids: document.getElementById("simple-host").children.length,
    // эмулируем проверку toolStage через showTool
    showToolWorks: (function(){ try { window.__acShowTool("uzkie_mesta"); return "called"; } catch(e){ return "ERR:"+e.message; } })()
  })`));
  await sleep(400);
  const afterShow = JSON.parse(await evl(`JSON.stringify({
    umVisible: (function(){var t=document.querySelector('.stages .tool[data-tool="uzkie_mesta"]'); return !!t && t.offsetHeight>0;})(),
    activeNav: (document.querySelector('.sn-tool.active')||{}).textContent || null,
    wzTitle: document.getElementById("wz-title").textContent,
    hash: location.hash
  })`));
  // Перезагрузка в полном режиме, затем попытка открыть uzkie_mesta сразу
  await evl(`location.hash="#tool=uzkie_mesta"; location.reload(); 1`);
  await sleep(1500);
  const directHash = JSON.parse(await evl(`JSON.stringify({
    mode: localStorage.getItem("agentцех_режим"),
    umVisible: (function(){var t=document.querySelector('.stages .tool[data-tool="uzkie_mesta"]'); return !!t && t.offsetHeight>0;})(),
    wzTitle: document.getElementById("wz-title").textContent
  })`));
  console.log(JSON.stringify({ simpleState: JSON.parse(simpleState), fullState, afterShow, directHash }, null, 1));
  edge.kill("SIGKILL");
  process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(1); });
