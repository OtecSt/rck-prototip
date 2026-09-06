// Приёмка 06.09 — общий CDP-харнес по продy (по образцу с3_prod.js).
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const BASE = "https://201.34.132.154";
const AUTH_USER = "рцк", AUTH_PASS = "H8BgJlzfjESRDv4F";
const SHOTS = __dirname;

function jreq(method, path, port) {
  return new Promise((res, rej) => {
    const r = http.request({ host: "127.0.0.1", port, path, method }, (resp) => {
      let d = ""; resp.on("data", (c) => d += c); resp.on("end", () => res(JSON.parse(d)));
    });
    r.on("error", rej); r.end();
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function startHarness(tag, port) {
  const out = [];
  const log = (...a) => { console.log(...a); out.push(a.join(" ")); };
  const edge = spawn(EDGE, ["--headless=new", "--disable-gpu", "--ignore-certificate-errors",
    `--remote-debugging-port=${port}`, "--window-size=1500,1200",
    `--user-data-dir=/tmp/edge-p0609-${tag}`, "about:blank"], { stdio: "ignore" });
  process.on("exit", () => { try { edge.kill("SIGKILL"); } catch (e) {} });
  let target = null;
  for (let i = 0; i < 60; i++) {
    await sleep(300);
    try { target = await jreq("PUT", "/json/new?about:blank", port); break; } catch (e) {}
  }
  if (!target) throw new Error("CDP не поднялся");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0; const pend = {};
  const send = (m, p) => new Promise((res) => { const i = ++id; pend[i] = res; ws.send(JSON.stringify({ id: i, method: m, params: p || {} })); });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pend[m.id]) { pend[m.id](m.result); delete pend[m.id]; return; }
    if (m.method === "Fetch.authRequired") {
      send("Fetch.continueWithAuth", { requestId: m.params.requestId,
        authChallengeResponse: { response: "ProvideCredentials", username: AUTH_USER, password: AUTH_PASS } });
    } else if (m.method === "Fetch.requestPaused") {
      send("Fetch.continueRequest", { requestId: m.params.requestId });
    }
  };
  await new Promise((r) => ws.onopen = r);
  const evl = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    if (r && r.exceptionDetails) return "EXC:" + (r.exceptionDetails.exception && r.exceptionDetails.exception.description || r.exceptionDetails.text);
    return r && r.result ? r.result.value : null;
  };
  async function shot(name) {
    const r = await send("Page.captureScreenshot", { format: "png" });
    if (r && r.data) { fs.writeFileSync(SHOTS + "/" + name, Buffer.from(r.data, "base64")); log("shot:", name); }
  }
  async function waitText(expr, needle, tries = 40) {
    let v = null;
    for (let i = 0; i < tries; i++) {
      await sleep(500);
      v = await evl(expr);
      if ((v || "").indexOf(needle) >= 0) break;
    }
    return v;
  }
  async function init(pid) {
    await send("Page.enable");
    await send("Fetch.enable", { handleAuthRequests: true, patterns: [{ urlPattern: "*" }] });
    await send("Emulation.setDeviceMetricsOverride", { width: 1500, height: 1200, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url: BASE + "/" });
    await sleep(3000);
    await evl(`localStorage.setItem("agentцех_режим","full"); location.reload(); 1`);
    await sleep(3000);
    log("title:", await evl("document.title"));
    if (pid) {
      await evl(`(function(){var s=document.getElementById("pj-select"); s.value="${pid}"; s.dispatchEvent(new Event("change",{bubbles:true})); return s.value;})()`);
      await sleep(1200);
    }
  }
  function saveLog(name) { fs.writeFileSync(SHOTS + "/" + name, out.join("\n")); }
  return { log, evl, shot, waitText, init, saveLog, edge };
}

module.exports = { startHarness, sleep, BASE, AUTH_USER, AUTH_PASS };
