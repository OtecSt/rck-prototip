// Приёмка 06.09 · Д3.1-1 (SMART сохранение + цепочка SMART→ОРД) и Д3.1-4 (мероприятия без «Экономики»).
const { startHarness, sleep } = require("./priemka0609_cdp.js");
const PID = 15;

async function main() {
  const h = await startHarness("d31", 9416);
  const R = [];
  const chk = (name, ok, doc) => { R.push([name, ok ? "PASS" : "FAIL", doc]); h.log(`[${ok ? "PASS" : "FAIL"}] ${name} :: ${doc}`); };
  try {
    await h.init(PID);

    // --- Д3.1-1: SMART ---
    await h.evl(`window.__acShowTool("smart"); 1`);
    await sleep(1200);
    await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  set("sm-предприятие", "Приёмка-0609");
  set("sm-поток", "Поток приёмки 0609");
  document.getElementById("sm-цель-add").click();
  var b = document.querySelector("#sm-цели .sm-цель");
  function setC(cls, v) { var e = b.querySelector(cls); if (e) { e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); } }
  setC(".c-наим", "Выработка"); setC(".c-ед", "шт/чел"); setC(".c-тек", "10"); setC(".c-цел", "12");
  return "цель добавлена";
})()`);
    const smst = await h.waitText(`document.getElementById("sm-status-line").textContent`, "Пересчитано", 30);
    h.log("smart статус:", smst);
    const smZone = await h.evl(`!document.getElementById("sm-result-zone").hidden && document.getElementById("sm-report").textContent.length > 50`);
    await h.evl(`document.getElementById("save-sm-метка").value="приёмка0609"; document.getElementById("save-sm-btn").click(); 1`);
    const sv = await h.waitText(`document.getElementById("save-sm-status").textContent`, "сохранён", 30);
    h.log("save smart:", sv);
    const smHist = await h.evl(`
(async function () {
  var r = await fetch("/api/proekty/${PID}").then(function(x){return x.json();});
  return r.progony.filter(function(g){return g["инструмент"] === "smart";}).length;
})()`);
    h.log("smart прогонов в проекте:", smHist);
    chk("Д3.1-1а SMART: сохранить прогон → не 500, прогон в истории",
        sv.indexOf("сохранён") >= 0 && smHist >= 2, `отчёт=${smZone} save=${sv} smart-прогонов=${smHist}`);
    await h.shot("priemka0609_smart.png");

    // цепочка SMART→ОРД
    await h.evl(`window.__acShowTool("ord"); 1`);
    await sleep(1000);
    await h.evl(`document.getElementById("ord-цели-pull").click(); 1`);
    await sleep(2000);
    const ord = JSON.parse(await h.evl(`
JSON.stringify({
  hint: document.getElementById("ord-цели-hint").textContent,
  rows: document.querySelectorAll("#ord-цели-body tr").length,
  first: (document.querySelector("#ord-цели-body tr") || {textContent: ""}).textContent.replace(/\\s+/g, " ").trim().slice(0, 80)
})`));
    h.log("ORD:", JSON.stringify(ord));
    chk("Д3.1-1б цепочка SMART→ОРД цела", ord.rows >= 1, `строк целей=${ord.rows} hint=${ord.hint} первая=${ord.first}`);
    await h.shot("priemka0609_ord_chain.png");

    // --- Д3.1-4: мероприятия без «Экономики» ---
    await h.evl(`window.__acShowTool("meropriyatiya"); 1`);
    await sleep(1200);
    await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  set("mp-участок", "фасовка"); set("mp-впп", "38,7"); set("mp-разрыв", "23,7");
  set("mp-тц", "4,0"); set("mp-смена", "480");
  ["простои_оборудования", "организация_рабочих_мест"].forEach(function (k) {
    var c = document.getElementById("mp-priz-" + k); if (c) c.checked = true;
  });
  return "заполнено (экономика пустая: ттакт=" + document.getElementById("mp-ттакт").value + " цена=" + document.getElementById("mp-цена").value + ")";
})()`);
    await h.evl(`document.getElementById("mp-btn-run").click(); 1`);
    await sleep(3500);
    const mpst = await h.evl(`document.getElementById("mp-status-line").textContent`);
    h.log("mp статус:", mpst);
    await h.evl(`document.getElementById("save-mp-метка").value="приёмка0609 без экономики"; document.getElementById("save-mp-btn").click(); 1`);
    const svmp = await h.waitText(`document.getElementById("save-mp-status").textContent`, "сохранён", 30);
    h.log("save mp:", svmp);
    const mpHist = JSON.parse(await h.evl(`
(async function () {
  var r = await fetch("/api/proekty/${PID}").then(function(x){return x.json();});
  var mps = r.progony.filter(function(g){return g["инструмент"] === "meropriyatiya";});
  var last = mps[mps.length - 1];
  return JSON.stringify({count: mps.length, last_id: last.id, itog: JSON.stringify(last["итоги"] || {}).slice(0, 300)});
})()`));
    h.log("MP HIST:", JSON.stringify(mpHist));
    chk("Д3.1-4 мероприятия: прогон с «Тцикл УМ» без «Экономики»",
        svmp.indexOf("сохранён") >= 0 && mpHist.count >= 2,
        `run=${mpst} save=${svmp} mp-прогонов=${mpHist.count} итог=${mpHist.itog}`);
    await h.shot("priemka0609_mp_noecon.png");
  } catch (e) {
    h.log("EXC:", e.message);
  } finally {
    h.saveLog("priemka0609_d31.log");
    const fails = R.filter(r => r[1] === "FAIL");
    h.log(`ИТОГ d31: ${R.length - fails.length}/${R.length} PASS`);
    console.log("RESULT_JSON:" + JSON.stringify(R));
    process.exit(0);
  }
}
main().catch(e => { console.error(e); process.exit(2); });
