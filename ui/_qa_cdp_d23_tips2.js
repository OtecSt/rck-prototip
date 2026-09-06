// Д2.3: строгая проверка hover-тултипов sim — для каждой колонки: реальный hover
// через CDP, проверка класса tip-fixed и ::after content, скриншот.
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9339;
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
    "--window-size=1400,1000", "--user-data-dir=/tmp/edge-qa-d23-tips2", "about:blank"], { stdio: "ignore" });
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
  await sleep(1600);
  await evl(`document.getElementById("sim-ops-table").scrollIntoView({block:"center"}); 1`);
  await sleep(400);
  const out = {};
  const nCols = await evl(`document.querySelectorAll("#sim-ops-table th").length`);
  for (let col = 0; col < nCols; col++) {
    // сначала уводим курсор в сторону — сброс hover
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 700, y: 300 });
    await sleep(150);
    const pos = JSON.parse(await evl(`(function(){
      var th = document.querySelectorAll("#sim-ops-table th")[${col}];
      var tip = th && th.querySelector(".f-tip");
      if (!tip) return JSON.stringify(null);
      var r = tip.getBoundingClientRect();
      return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2,
        hit: (document.elementFromPoint(r.x + r.width/2, r.y + r.height/2) || {}).className});
    })()`));
    if (!pos) { out["col" + col] = "no-tip"; continue; }
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: pos.x, y: pos.y });
    await sleep(400);
    const st = JSON.parse(await evl(`(function(){
      var th = document.querySelectorAll("#sim-ops-table th")[${col}];
      var tip = th.querySelector(".f-tip");
      var cs = getComputedStyle(tip, "::after");
      var fixed = tip.classList.contains("tip-fixed");
      // реальная видимость: координаты тултипа в вьюпорте
      var y = parseFloat(getComputedStyle(tip).getPropertyValue("--tip-y")) || 0;
      return JSON.stringify({ hovered: tip.matches(":hover"),
        fixed: fixed, content: cs.content.slice(0, 30), pos: cs.position, tipY: y });
    })()`));
    const o = st; o.aim = pos;
    out["col" + col] = o;
    if (o.fixed) await shot(`_qa_d23_tip2_col${col}.png`);
  }
  console.log(JSON.stringify(out, null, 1));
  const pass = Object.keys(out).every((k) => out[k] && out[k].hovered && out[k].fixed);
  console.log(pass ? "TIPS_PASS" : "TIPS_FAIL");
  edge.kill("SIGKILL");
  process.exit(pass ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
