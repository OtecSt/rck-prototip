// Д2.3: полная матрица режимов простой↔полный, все 16 инструментов после переключений.
// A: старт в простом (localStorage), клик 4 инструментов → полный → все 16.
// B: полный → простой → полный → все 16.
// C: идемпотентность — 3 цикла простой↔полный, карточки на местах, host пуст.
const { spawn } = require("child_process");
const http = require("http");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9338;
const BASE = process.env.QA_BASE || "http://localhost:8000";
const TOOLS = ["otbor","otbor_potok","akt","ord","soglashenie","smart","uzkie_mesta","vsm","potok_calc","oee","ee","meropriyatiya","sim","protokol","vr","zamer"];
const SIMPLE = ["uzkie_mesta","vsm","potok_calc","oee"];
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
    "--window-size=1400,1000", "--user-data-dir=/tmp/edge-qa-d23-matrix", "about:blank"], { stdio: "ignore" });
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
    if (r && r.exceptionDetails) return "EXC:" + (r.exceptionDetails.exception && r.exceptionDetails.exception.description || r.exceptionDetails.text);
    return r && r.result ? r.result.value : null;
  };
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 1000, deviceScaleFactor: 1, mobile: false });

  // Проверка всех 16 инструментов в полном режиме: showTool → карточка видима в .stages
  const checkAll16 = async (tag) => {
    const bad = [];
    for (const tk of TOOLS) {
      await evl(`window.__acShowTool("${tk}"); 1`);
      await sleep(200);
      const ok = await evl(`(function(){
        var t = document.querySelector('.stages .tool[data-tool="${tk}"]');
        if (!t) return "no-card-in-stages";
        if (getComputedStyle(t).display === "none" || t.offsetHeight === 0) return "hidden";
        var wz = document.getElementById("wz-title").textContent;
        return wz ? "ok" : "no-wz";
      })()`);
      if (ok !== "ok") bad.push(tk + ":" + ok);
    }
    return { tag, bad, pass: bad.length === 0 };
  };
  const hostState = () => evl(`JSON.stringify({
    hostKids: document.getElementById("simple-host").children.length,
    inHost: Array.prototype.map.call(document.querySelectorAll('#simple-host .tool[data-tool]'), function(t){return t.getAttribute('data-tool');}),
    // все 4 простые карточки должны лежать в .stages, когда полный режим
    inStages: Array.prototype.map.call(document.querySelectorAll('.stages .tool[data-tool]'), function(t){return t.getAttribute('data-tool');}).filter(function(k){return ${JSON.stringify(SIMPLE)}.indexOf(k)>=0;})
  })`);

  const report = {};

  // --- Сценарий A: старт сессии в простом режиме ---
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(1200);
  await evl(`localStorage.setItem("agentцех_режим","simple"); localStorage.removeItem("rck_nav_tool"); location.hash=""; location.reload(); 1`);
  await sleep(1600);
  for (const tk of SIMPLE) {
    await evl(`var it=document.querySelector('.sn-tool[data-tool="${tk}"]'); it && it.click(); 1`);
    await sleep(250);
  }
  report.A_simpleClicks = JSON.parse(await hostState());
  await evl(`document.getElementById("mode-full-btn").click(); 1`);
  await sleep(600);
  report.A_afterFull = JSON.parse(await hostState());
  report.A_all16 = await checkAll16("A");

  // --- Сценарий B: полный → простой → полный → все 16 ---
  await evl(`document.getElementById("mode-simple-btn").click(); 1`);
  await sleep(400);
  for (const tk of ["oee", "uzkie_mesta"]) {
    await evl(`var it=document.querySelector('.sn-tool[data-tool="${tk}"]'); it && it.click(); 1`);
    await sleep(250);
  }
  await evl(`document.getElementById("mode-full-btn").click(); 1`);
  await sleep(600);
  report.B_afterFull = JSON.parse(await hostState());
  report.B_all16 = await checkAll16("B");

  // --- Сценарий C: идемпотентность — 3 цикла ---
  report.C_cycles = [];
  for (let c = 0; c < 3; c++) {
    await evl(`document.getElementById("mode-simple-btn").click(); 1`);
    await sleep(350);
    await evl(`var it=document.querySelector('.sn-tool[data-tool="potok_calc"]'); it && it.click(); 1`);
    await sleep(250);
    await evl(`document.getElementById("mode-full-btn").click(); 1`);
    await sleep(500);
    report.C_cycles.push(JSON.parse(await hostState()));
  }
  report.C_all16 = await checkAll16("C");

  // --- Сценарий D: прямой хэш в простом режиме на не-простой инструмент ---
  await evl(`document.getElementById("mode-simple-btn").click(); 1`);
  await sleep(350);
  await evl(`location.hash="#tool=sim"; 1`);
  await sleep(400);
  report.D_hashSimInSimple = JSON.parse(await evl(`JSON.stringify({
    simpleVisible: !document.getElementById("simple-start").hidden,
    hostKids: document.getElementById("simple-host").children.length
  })`));

  const pass = report.A_all16.pass && report.B_all16.pass && report.C_all16.pass &&
    report.A_afterFull.hostKids === 0 && report.A_afterFull.inStages.length === 4 &&
    report.B_afterFull.hostKids === 0 &&
    report.C_cycles.every((c) => c.hostKids === 0 && c.inStages.length === 4);
  console.log(JSON.stringify(report, null, 1));
  console.log(pass ? "MATRIX_PASS" : "MATRIX_FAIL");
  edge.kill("SIGKILL");
  process.exit(pass ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
