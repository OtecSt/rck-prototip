// Приёмка 06.09 · Блок Д3.2: 5 починенных дефектов.
const { startHarness, sleep } = require("./priemka0609_cdp.js");
const PID = 15;

async function main() {
  const h = await startHarness("d32", 9417);
  const R = [];
  const chk = (name, ok, doc) => { R.push([name, ok ? "PASS" : "FAIL", doc]); h.log(`[${ok ? "PASS" : "FAIL"}] ${name} :: ${doc}`); };
  try {
    await h.init(PID);

    // --- Д3.2-1: отчёт ЭЭ не протекает на экран симуляции и обратно ---
    await h.evl(`window.__acShowTool("ee"); 1`);
    await sleep(1200);
    // грузим прогон ЭЭ из истории (вход заполнит форму, отчёт пересчитается сам)
    await h.evl(`(function(){var b=document.querySelector("#hist-ee-list [data-load]"); if(b) b.click(); return b ? b.getAttribute("data-load") : "нет";})()`);
    await sleep(4000);
    const eeRep = JSON.parse(await h.evl(`
JSON.stringify({zone: !document.getElementById("ee-result-zone").hidden,
  len: document.getElementById("ee-report").textContent.length})`));
    h.log("ЭЭ отчёт:", JSON.stringify(eeRep));
    await h.shot("priemka0609_ee_report.png");
    // переключаемся на sim
    await h.evl(`window.__acShowTool("sim"); 1`);
    await sleep(1500);
    const leak1 = JSON.parse(await h.evl(`
JSON.stringify({
  ee_hidden: document.querySelector('.stages .tool[data-tool="ee"]').offsetHeight === 0,
  sim_visible: document.querySelector('.stages .tool[data-tool="sim"]').offsetHeight > 0
})`));
    // наполняем sim, чтобы был свой отчёт
    await h.evl(`
(function () {
  function setV(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  setV("sim-поток", "Т"); setV("sim-спрос", "300"); setV("sim-время", "480"); setV("sim-численность", "5");
  var tbody = document.getElementById("sim-ops-body");
  while (tbody.rows.length < 3) document.getElementById("sim-btn-add").click();
  [["Оп1","1,9"],["Оп2","2"],["Оп3","1,5"]].forEach(function (o, i) {
    var tr = tbody.rows[i];
    tr.querySelector(".c-имя").value = o[0]; tr.querySelector(".c-ту").value = o[1];
    tr.querySelectorAll("input").forEach(function(inp){ inp.dispatchEvent(new Event("input", {bubbles: true})); });
  });
  return 1;})()`);
    await h.waitText(`document.getElementById("sim-status-line").textContent`, "База посчитана", 40);
    // обратно на ЭЭ
    await h.evl(`window.__acShowTool("ee"); 1`);
    await sleep(1500);
    const leak2 = JSON.parse(await h.evl(`
JSON.stringify({
  sim_hidden: document.querySelector('.stages .tool[data-tool="sim"]').offsetHeight === 0,
  ee_visible: document.querySelector('.stages .tool[data-tool="ee"]').offsetHeight > 0,
  ee_report_still: document.getElementById("ee-report").textContent.length
})`));
    h.log("LEAK:", JSON.stringify(leak1), JSON.stringify(leak2));
    chk("Д3.2-1 отчёт ЭЭ не протекает на sim и обратно",
        eeRep.zone && leak1.ee_hidden && leak1.sim_visible && leak2.sim_hidden && leak2.ee_visible && leak2.ee_report_still > 50,
        `ээ-зона=${eeRep.zone}; на sim: ee_hidden=${leak1.ee_hidden}; обратно: sim_hidden=${leak2.sim_hidden}, отчёт ээ ${leak2.ee_report_still} симв.`);

    // --- Д3.2-2: «→ в форму» у Акта и Соглашения ---
    await h.evl(`window.__acShowTool("akt"); 1`);
    await sleep(1000);
    await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); if (e) { e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); } }
  set("akt-предприятие", "Приёмка-0609 АКТ");
  set("akt-дата-начала", "«01» сентября 2026 г.");
  return 1;})()`);
    await h.evl(`document.getElementById("save-akt-btn").click(); 1`);
    const svAkt = await h.waitText(`document.getElementById("save-akt-status").textContent`, "охранен", 30);
    h.log("save akt:", svAkt);
    await sleep(1500);
    await h.evl(`(function(){var e=document.getElementById("akt-предприятие"); e.value="ИЗМЕНЕНО"; e.dispatchEvent(new Event("input",{bubbles:true})); return 1;})()`);
    const aktBtn = await h.evl(`(function(){var b=document.querySelector("#hist-akt-list [data-load]"); if(!b) return "нет кнопки"; b.click(); return b.getAttribute("data-load");})()`);
    await sleep(2500);
    const aktVal = await h.evl(`document.getElementById("akt-предприятие").value`);
    h.log("акт после загрузки:", aktVal, "(кнопка", aktBtn + ")");
    chk("Д3.2-2а «→ в форму» у Акта", svAkt.toLowerCase().indexOf("охранен") >= 0 && aktVal === "Приёмка-0609 АКТ",
        `save=${svAkt}; после загрузки прогона ${aktBtn}: ${aktVal}`);

    await h.evl(`window.__acShowTool("soglashenie"); 1`);
    await sleep(1000);
    await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); if (e) { e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); } }
  set("sg-предприятие", "Приёмка-0609 СОГЛ");
  set("sg-номер", "77");
  return 1;})()`);
    await h.evl(`document.getElementById("save-sg-btn").click(); 1`);
    const svSg = await h.waitText(`document.getElementById("save-sg-status").textContent`, "охранен", 30);
    h.log("save sg:", svSg);
    await sleep(1500);
    await h.evl(`(function(){var e=document.getElementById("sg-предприятие"); e.value="ИЗМЕНЕНО"; e.dispatchEvent(new Event("input",{bubbles:true})); return 1;})()`);
    const sgBtn = await h.evl(`(function(){var b=document.querySelector("#hist-soglashenie-list [data-load]"); if(!b) return "нет кнопки"; b.click(); return b.getAttribute("data-load");})()`);
    await sleep(2500);
    const sgVal = await h.evl(`document.getElementById("sg-предприятие").value`);
    h.log("соглашение после загрузки:", sgVal, "(кнопка", sgBtn + ")");
    chk("Д3.2-2б «→ в форму» у Соглашения", svSg.toLowerCase().indexOf("охранен") >= 0 && sgVal === "Приёмка-0609 СОГЛ",
        `save=${svSg}; после загрузки прогона ${sgBtn}: ${sgVal}`);

    // --- Д3.2-3: баннеры «данные устарели» в Показателях потока и OEE ---
    await h.evl(`window.__acShowTool("potok_calc"); 1`);
    await sleep(1000);
    await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  set("pp-поток", "Т"); set("pp-спрос", "240"); set("pp-время", "480"); set("pp-численность", "5");
  var tr = document.getElementById("pp-ops-body").rows[0];
  tr.querySelector(".c-имя").value = "Оп1"; tr.querySelector(".c-тц").value = "1,5";
  tr.querySelectorAll("input").forEach(function(inp){ inp.dispatchEvent(new Event("input", {bubbles: true})); });
  return 1;})()`);
    await h.waitText(`!document.getElementById("pp-result-zone").hidden ? "ok" : ""`, "ok", 30);
    const ppZone = await h.evl(`!document.getElementById("pp-result-zone").hidden`);
    // ломаем вход: спрос = мусор → пересчёт невозможен → баннер
    await h.evl(`(function(){var e=document.getElementById("pp-спрос"); e.value="абв"; e.dispatchEvent(new Event("input",{bubbles:true})); return 1;})()`);
    await sleep(2500);
    const ppStale = await h.evl(`!document.getElementById("pp-result-stale").hidden`);
    const ppStatus = await h.evl(`document.getElementById("pp-status-line").textContent`);
    h.log("PP: zone=", ppZone, "stale=", ppStale, "status=", ppStatus);
    chk("Д3.2-3а баннер в «Показателях потока»", ppZone && ppStale === true,
        `отчёт=${ppZone} баннер=${ppStale} статус=${ppStatus}`);
    await h.shot("priemka0609_pp_stale.png");

    await h.evl(`window.__acShowTool("oee"); 1`);
    await sleep(1000);
    await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  set("oe-время", "480"); set("oe-аварии", "47"); set("oe-переналадка", "38"); set("oe-микро", "22");
  set("oe-тц", "1"); set("oe-выпуск", "350"); set("oe-брак", "12");
  return 1;})()`);
    await h.waitText(`!document.getElementById("oe-result-zone").hidden ? "ok" : ""`, "ok", 30);
    const oeZone = await h.evl(`!document.getElementById("oe-result-zone").hidden`);
    await h.evl(`(function(){var e=document.getElementById("oe-выпуск"); e.value="абв"; e.dispatchEvent(new Event("input",{bubbles:true})); return 1;})()`);
    await sleep(2500);
    const oeStale = await h.evl(`!document.getElementById("oe-result-stale").hidden`);
    h.log("OE: zone=", oeZone, "stale=", oeStale);
    chk("Д3.2-3б баннер в OEE", oeZone && oeStale === true, `отчёт=${oeZone} баннер=${oeStale}`);
    await h.shot("priemka0609_oe_stale.png");

    // --- Д3.2-4: подсветка обязательных полей ---
    const req = JSON.parse(await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  var r = {};
  set("pp-спрос", ""); 
  r.empty_class = document.getElementById("pp-спрос").className;
  set("pp-спрос", "240");
  r.ok_class = document.getElementById("pp-спрос").className;
  set("pp-спрос", "абв");
  r.bad_class = document.getElementById("pp-спрос").className;
  // справка: текст про подсветку
  var help = document.body.textContent.indexOf("янтарное — не заполнено") >= 0;
  r.help_states = help;
  return JSON.stringify(r);
})()`));
    h.log("REQ:", JSON.stringify(req));
    chk("Д3.2-4 обязательные поля: янтарь/зелёный/красный + справка",
        req.empty_class.indexOf("miss") >= 0 && req.ok_class.indexOf("ok-line") >= 0 && req.bad_class.indexOf("bad") >= 0 && req.help_states,
        `пустое=${req.empty_class} ок=${req.ok_class} мусор=${req.bad_class} справка=${req.help_states}`);

    // --- Д3.2-5: sanity-check такта ---
    await h.evl(`
(function () {
  function set(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  set("pp-спрос", "240"); set("pp-время", "480000");
  return 1;})()`);
    const sane = await h.waitText(`document.getElementById("pp-status-line").textContent`, "неправдоподобен", 30);
    h.log("SANITY:", sane);
    chk("Д3.2-5 неправдоподобный такт — предупреждение", (sane || "").indexOf("неправдоподобен") >= 0, sane);
    await h.shot("priemka0609_pp_sanity.png");
  } catch (e) {
    h.log("EXC:", e.message);
  } finally {
    h.saveLog("priemka0609_d32.log");
    const fails = R.filter(r => r[1] === "FAIL");
    h.log(`ИТОГ d32: ${R.length - fails.length}/${R.length} PASS`);
    console.log("RESULT_JSON:" + JSON.stringify(R));
    process.exit(0);
  }
}
main().catch(e => { console.error(e); process.exit(2); });
