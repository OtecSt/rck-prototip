// Репродукция Д2.3: баги №2 (meropriyatiya вёрстка) и №3 (тултипы/обрезание в sim)
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9336;
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
    "--window-size=1400,1000", "--user-data-dir=/tmp/edge-qa-d23-shot", "about:blank"], { stdio: "ignore" });
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
  await evl(`localStorage.setItem("agentцех_режим","full"); 1`);
  // meropriyatiya
  await evl(`location.hash="#tool=meropriyatiya"; location.reload(); 1`);
  await sleep(1500);
  await evl(`document.querySelector('.tool[data-tool="meropriyatiya"]').scrollIntoView(); window.scrollBy(0,-60); 1`);
  await sleep(300);
  await shot("_qa_d23_merop_before.png");
  const mpDom = JSON.parse(await evl(`JSON.stringify({
    prizKids: document.getElementById("mp-признаки").children.length,
    firstPrizDisplay: getComputedStyle(document.querySelector("#mp-признаки .field")).display,
    firstPrizText: document.querySelector("#mp-признаки .field").textContent.slice(0,60),
    gridCols: getComputedStyle(document.querySelector('.tool[data-tool="meropriyatiya"] .meta-grid')).gridTemplateColumns
  })`));
  // sim
  await evl(`window.__acShowTool("sim"); 1`);
  await sleep(500);
  await evl(`document.getElementById("sim-ops-table").scrollIntoView({block:"center"}); 1`);
  await sleep(300);
  await shot("_qa_d23_sim_before.png");
  const simDom = JSON.parse(await evl(`(function(){
    var ths = Array.prototype.slice.call(document.querySelectorAll("#sim-ops-table th"));
    var sc = document.querySelector('.tool[data-tool="sim"] .ops-scroll');
    return JSON.stringify({
      scrollLeft: sc.scrollLeft,
      firstTh: ths[0] ? { text: ths[0].textContent.trim(), rect: ths[0].getBoundingClientRect().toJSON(),
        scrollRect: sc.getBoundingClientRect().toJSON() } : null,
      thCount: ths.length,
      tipsInTh: ths.map(function(t){ return !!t.querySelector(".f-tip"); })
    });
  })()`));
  console.log(JSON.stringify({ mpDom, simDom }, null, 1));
  edge.kill("SIGKILL");
  process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(1); });
