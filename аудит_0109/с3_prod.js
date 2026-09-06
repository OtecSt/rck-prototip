// С3: CDP-приёмка по продy — кнопка у мероприятия есть, переход работает.
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9344;
const BASE = "https://201.34.132.154";
const AUTH_USER = "рцк", AUTH_PASS = "H8BgJlzfjESRDv4F";
const PID = "14";
const SHOTS = __dirname;
function jreq(method, path) {
  return new Promise((res, rej) => {
    const r = http.request({ host: "127.0.0.1", port: PORT, path, method }, (resp) => {
      let d = ""; resp.on("data", (c) => d += c); resp.on("end", () => res(JSON.parse(d)));
    });
    r.on("error", rej); r.end();
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const out = [];
function log(...a) { console.log(...a); out.push(a.join(" ")); }
async function main() {
  const edge = spawn(EDGE, ["--headless=new", "--disable-gpu", "--ignore-certificate-errors",
    `--remote-debugging-port=${PORT}`, "--window-size=1500,1100",
    "--user-data-dir=/tmp/edge-qa-c3-prod", "about:blank"], { stdio: "ignore" });
  process.on("exit", () => { try { edge.kill("SIGKILL"); } catch (e) {} });
  let target = null;
  for (let i = 0; i < 40; i++) {
    await sleep(300);
    try { target = await jreq("PUT", "/json/new?about:blank"); break; } catch (e) {}
  }
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
  await send("Page.enable");
  await send("Fetch.enable", { handleAuthRequests: true, patterns: [{ urlPattern: "*" }] });
  await send("Emulation.setDeviceMetricsOverride", { width: 1500, height: 1100, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(3000);
  await evl(`localStorage.setItem("agentцех_режим","full"); location.reload(); 1`);
  await sleep(3000);
  log("title:", await evl("document.title"));
  log("mapping keys:", await evl("Object.keys((window.__acSim||{}).МАППИНГ_МЕРОПРИЯТИЙ||{}).length"));

  await evl(`(function(){var s=document.getElementById("pj-select"); s.value="${PID}"; s.dispatchEvent(new Event("change",{bubbles:true})); return 1;})()`);
  await sleep(1000);
  await evl(`window.__acShowTool("meropriyatiya"); 1`);
  await sleep(400);
  await evl(`(function(){
    function set(id,v){var e=document.getElementById(id); e.value=v; e.dispatchEvent(new Event("input",{bubbles:true}));}
    set("mp-участок","фасовка"); set("mp-впп","38,7"); set("mp-разрыв","23,7");
    set("mp-тц","4,0"); set("mp-смена","480");
    ["простои_оборудования","организация_рабочих_мест","вариативность_операций"].forEach(function(k){
      var c=document.getElementById("mp-priz-"+k); if(c) c.checked=true;
    });
    return 1;})()`);
  await evl(`document.getElementById("mp-btn-run").click(); 1`);
  await sleep(2500);
  log("mp status:", await evl(`document.getElementById("mp-status-line").textContent`));
  log("кнопки:", await evl(`JSON.stringify(Array.prototype.map.call(document.querySelectorAll("#mp-топ .mp-sim-btn, #mp-топ button[disabled]"), function(b){return {dis:b.disabled, ин:b.getAttribute("data-инстр")};}))`));
  // клик по первой активной
  await evl(`(function(){var b=document.querySelector("#mp-топ .mp-sim-btn:not([disabled])"); if(!b) return "нет активной"; b.click(); return b.getAttribute("data-инстр");})()`).then(x => log("клик по:", x));
  await sleep(7000);
  log("sim видим:", await evl(`(function(){var t=document.querySelector('.stages .tool[data-tool="sim"]'); return t && t.offsetHeight>0;})()`));
  log("banner:", await evl(`document.getElementById("sim-mp-banner").textContent`));
  log("verdict:", await evl(`document.getElementById("sim-verdict").textContent`));
  await evl(`document.getElementById("sim-to-ee").click(); 1`);
  await sleep(1500);
  log("ee тц до/после:", await evl(`document.getElementById("ee-тц-до").value + " / " + document.getElementById("ee-тц-после").value`));
  log("ee пометка:", await evl(`document.getElementById("ee-контекст").textContent`));
  await shot("с3_prod_ee.png");
  fs.writeFileSync(SHOTS + "/с3_prod.log", out.join("\n"));
  log("DONE");
  process.exit(0);
}
main().catch(e => { console.error(e); process.exit(1); });
