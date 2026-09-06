// С3: CDP-проверка «Просимулировать» у мероприятий + ЭЭ-мостик.
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9340;
const BASE = "http://127.0.0.1:8015";
const AUTH_USER = "рцк", AUTH_PASS = "H8BgJlzfjESRDv4F";
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
  const edge = spawn(EDGE, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${PORT}`,
    "--window-size=1500,1100", "--user-data-dir=/tmp/edge-qa-с3", "about:blank"], { stdio: "ignore" });
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
  log("ws open");
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
  await sleep(2500);
  log("navigated");
  // Полный режим (в «простом старте» meropriyatiya/sim/ee недоступны)
  await evl(`localStorage.setItem("agentцех_режим","full"); location.reload(); 1`);
  await sleep(2500);
  log("mode:", await evl(`localStorage.getItem("agentцех_режим")`));

  // 0. sanity: страница и мосты на месте
  log("title:", await evl("document.title"));
  log("acSim keys:", await evl("Object.keys(window.__acSim||{}).join(',')"));

  // 1. выбрать проект 40 (с прогоном potok_calc)
  await evl(`(function(){var s=document.getElementById("pj-select"); s.value="40"; s.dispatchEvent(new Event("change",{bubbles:true})); return s.value;})()`);
  await sleep(800);

  // 2. генератор мероприятий: заполнить обязательные + признаки, сформировать план
  await evl(`window.__acShowTool("meropriyatiya"); 1`);
  await sleep(400);
  await evl(`(function(){
    function set(id,v){var e=document.getElementById(id); e.value=v; e.dispatchEvent(new Event("input",{bubbles:true}));}
    set("mp-участок","фасовка"); set("mp-впп","38,7"); set("mp-разрыв","23,7");
    set("mp-тц","4,0"); set("mp-смена","480");
    ["простои_оборудования","проблемы_качества","организация_рабочих мест".replace(" ","_"),"вариативность_операций"].forEach(function(k){
      var c=document.getElementById("mp-priz-"+k); if(c) c.checked=true;
    });
    return 1;})()`);
  await evl(`document.getElementById("mp-btn-run").click(); 1`);
  await sleep(2500);
  log("mp status:", await evl(`document.getElementById("mp-status-line").textContent`));
  const btns = JSON.parse(await evl(`JSON.stringify(Array.prototype.map.call(document.querySelectorAll("#mp-топ .mp-sim-btn, #mp-топ button[disabled]"), function(b){return {t:b.textContent, dis:b.disabled, ин:b.getAttribute("data-инстр")};}))`));
  log("кнопки mp:", JSON.stringify(btns));
  const enabled = btns.filter(b => !b.dis);
  const disabled = btns.filter(b => b.dis);
  log("активных:", enabled.length, "неактивных:", disabled.length);
  await evl(`document.getElementById("mp-топ").scrollIntoView({block:"center"}); 1`);
  await sleep(400);
  await shot("с3_mp_buttons.png");

  // 3. клик по активной кнопке (SMED, если есть)
  const pickName = (enabled.find(b => /SMED/.test(b.ин || "")) || enabled[0]);
  log("кликаем:", JSON.stringify(pickName));
  await evl(`(function(){var b=Array.prototype.find.call(document.querySelectorAll("#mp-топ .mp-sim-btn"), function(x){return x.getAttribute("data-инстр")===${JSON.stringify(pickName.ин)};}); b.scrollIntoView(); b.click(); return 1;})()`);
  await sleep(6000); // подтяжка входа + база (10 прогонов) + сценарий
  log("sim tool видим:", await evl(`(function(){var t=document.querySelector('.stages .tool[data-tool="sim"]'); return t && t.offsetHeight>0;})()`));
  log("banner:", await evl(`(function(){var b=document.getElementById("sim-mp-banner"); return JSON.stringify({hidden:b.hidden, text:b.textContent});})()`));
  log("sim status:", await evl(`document.getElementById("sim-status-line").textContent`));
  log("verdict:", await evl(`(function(){var v=document.getElementById("sim-verdict"); return JSON.stringify({hidden:v.hidden, text:v.textContent});})()`));
  log("cmp rows:", await evl(`document.querySelectorAll("#sim-cmp-body tr").length`));
  log("slider vals:", await evl(`JSON.stringify(Array.prototype.map.call(document.querySelectorAll("#sim-scen-ops input[type=range]"), function(i){return i.value;}))`));
  await evl(`document.getElementById("sim-mp-banner").scrollIntoView({block:"start"}); 1`);
  await sleep(400);
  await shot("с3_sim_scenario.png");

  // 4. ЭЭ-мостик
  log("sim-to-ee disabled:", await evl(`document.getElementById("sim-to-ee").disabled`));
  await evl(`document.getElementById("sim-to-ee").click(); 1`);
  await sleep(1500);
  log("ee поля:", await evl(`JSON.stringify({
    тцДо: document.getElementById("ee-тц-до").value,
    тцПосле: document.getElementById("ee-тц-после").value,
    ттДо: document.getElementById("ee-тт-до").value,
    ттПосле: document.getElementById("ee-тт-после").value})`));
  log("ee-контекст:", await evl(`(function(){var b=document.getElementById("ee-контекст"); return JSON.stringify({hidden:b.hidden, text:b.textContent});})()`));
  log("ee tool видим:", await evl(`(function(){var t=document.querySelector('.stages .tool[data-tool="ee"]'); return t && t.offsetHeight>0;})()`));
  await evl(`document.getElementById("ee-контекст").scrollIntoView({block:"center"}); 1`);
  await sleep(400);
  await shot("с3_ee_bridge.png");

  // 5. пустой проект: честное сообщение при отсутствии прогона
  const emptyPid = await evl(`fetch("/api/proekty",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({"название":"С3-пустой"})}).then(r=>r.json()).then(r=>r.id)`);
  // чистая сессия (сброс состояния симуляции) + пустой проект
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(2500);
  await evl(`(function(){var s=document.getElementById("pj-select"); s.value=String(${emptyPid}); s.dispatchEvent(new Event("change",{bubbles:true})); return 1;})()`);
  await sleep(1000);
  await evl(`window.__acShowTool("sim"); window.__acSim.сценарийИзМероприятия({"instrument":"SMED (быстрая переналадка)","instrument_id":null}); 1`);
  await sleep(3000);
  log("пустой проект, sim status:", await evl(`document.getElementById("sim-status-line").textContent`));
  await evl(`document.querySelector('.tool[data-tool="sim"]').scrollIntoView(); 1`);
  await sleep(300);
  await shot("с3_sim_no_input.png");

  fs.writeFileSync(SHOTS + "/с3_cdp.log", out.join("\n"));
  log("DONE");
  process.exit(0);
}
main().catch(e => { console.error(e); process.exit(1); });
