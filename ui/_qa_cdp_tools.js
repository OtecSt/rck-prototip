// CDP-прогон: видимость всех 16 инструментов при #tool=<key>
const { spawn } = require("child_process");
const http = require("http");

const EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const PORT = 9333;
const BASE = process.env.QA_BASE || "http://localhost:8000";
const TOOLS = ["otbor","otbor_potok","akt","ord","soglashenie","smart","uzkie_mesta","vsm","potok_calc","oee","ee","meropriyatiya","sim","protokol","vr","zamer"];

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
    "--user-data-dir=/tmp/edge-qa-profile", "about:blank"], { stdio: "ignore" });
  process.on("exit", () => { try { edge.kill("SIGKILL"); } catch (e) {} });
  let target = null;
  for (let i = 0; i < 40; i++) {
    await sleep(300);
    try { target = await jreq("PUT", "/json/new?about:blank"); break; } catch (e) {}
  }
  if (!target) { console.error("no target"); process.exit(1); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0; const pend = {};
  const send = (method, params) => new Promise((res) => {
    const mid = ++id; pend[mid] = res;
    ws.send(JSON.stringify({ id: mid, method, params: params || {} }));
  });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pend[m.id]) { pend[m.id](m.result); delete pend[m.id]; }
  };
  await new Promise((r) => ws.onopen = r);
  await send("Page.enable");
  await send("Runtime.enable");
  const evalJs = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    return r && r.result ? r.result.value : null;
  };
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(2500);
  await evalJs(`try{localStorage.setItem("agentцех_режим","full");localStorage.removeItem("rck_nav_tool");}catch(e){}; location.reload(); "ok"`);
  await sleep(2500);
  const results = [];
  for (const key of TOOLS) {
    await evalJs(`location.hash="#tool=${key}"; "ok"`);
    await sleep(600);
    const snap = await evalJs(`(function(){
      function vis(el){ if(!el) return false; var cs=getComputedStyle(el);
        return cs.display!=="none" && !el.hidden && el.getClientRects().length>0; }
      var card=document.querySelector('#full-mode .tool[data-tool="${key}"]');
      var ov=document.querySelector(".stage-overview:not([hidden])");
      var errs=[]; 
      return { key:"${key}", hash:location.hash,
        cardExists:!!card, cardVisible:vis(card),
        cardHeight:card?card.offsetHeight:0,
        cardTextLen:card?card.textContent.replace(/\\s+/g," ").trim().length:0,
        wzTitle:(document.getElementById("wz-title")||{}).textContent||"",
        overviewVisible: ov?vis(ov):false };
    })()`);
    results.push(snap);
  }
  // простой режим: какие пункты меню видны
  await evalJs(`try{localStorage.setItem("agentцех_режим","simple");}catch(e){}; location.reload(); "ok"`);
  await sleep(2500);
  const simpleMenu = await evalJs(`(function(){
    function vis(el){ var cs=getComputedStyle(el); return cs.display!=="none" && !el.hidden && el.getClientRects().length>0; }
    var items=Array.prototype.slice.call(document.querySelectorAll("#side-nav .sn-item"));
    return items.filter(vis).map(function(it){ return (it.getAttribute("data-tool")||it.getAttribute("data-stage")||"?")+":"+(it.textContent||"").replace(/\\s+/g," ").trim().slice(0,40); });
  })()`);
  console.log("QA-RESULT:" + JSON.stringify({ tools: results, simpleMenu }, null, 1));
  ws.close(); edge.kill("SIGKILL");
  process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(1); });
