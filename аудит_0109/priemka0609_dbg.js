// Отладка Д3.1-2: загрузка прогона 88 в форму sim.
const { startHarness, sleep } = require("./priemka0609_cdp.js");
(async () => {
  const h = await startHarness("simfix3", 9414);
  try {
    await h.init(15);
    await h.evl(`window.__acShowTool("sim"); 1`);
    await sleep(1500);
    await h.evl(`(function(){var e=document.getElementById("sim-спрос"); e.value="999"; e.dispatchEvent(new Event("input",{bubbles:true})); return 1;})()`);
    const dbg = `
(async function () {
  try {
    var resp = await fetch("/api/progony/88").then(function(r){return r.json();});
    if (!resp.ok) return "API_FAIL:" + JSON.stringify(resp.errors);
    var g = resp.progon;
    var btn = document.querySelector('#hist-sim-list [data-load="88"]');
    if (!btn) return "NO_BUTTON";
    btn.click();
    await new Promise(function(r){setTimeout(r, 2000);});
    var msgs = Array.prototype.map.call(document.querySelectorAll(".pj-msg, [id$=msg], .msg"), function(e){return e.id + "=" + e.textContent;}).join(" | ");
    return JSON.stringify({
      api_instrument: g["инструмент"],
      spros_v_progone: g["вход"]["спрос_шт_в_период"],
      pole: document.getElementById("sim-спрос").value,
      msgs: msgs.slice(0, 300)
    });
  } catch (e) { return "EXC:" + e.message; }
})()`;
    h.log("DEBUG:", await h.evl(dbg));
  } finally { h.saveLog("priemka0609_sim_fix3.log"); process.exit(0); }
})().catch(e => { console.error(e); process.exit(2); });
