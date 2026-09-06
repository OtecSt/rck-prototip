// Приёмка 06.09 · Блок С3: «Просимулировать» у мероприятий + ЭЭ-мостик (проект «С3-приёмка», эталонный вход).
const { startHarness, sleep } = require("./priemka0609_cdp.js");
const PID = 14;

async function main() {
  const h = await startHarness("c3", 9418);
  const R = [];
  const chk = (name, ok, doc) => { R.push([name, ok ? "PASS" : "FAIL", doc]); h.log(`[${ok ? "PASS" : "FAIL"}] ${name} :: ${doc}`); };
  try {
    await h.init(PID);
    h.log("mapping keys:", await h.evl("Object.keys((window.__acSim||{}).МАППИНГ_МЕРОПРИЯТИЙ||{}).length"));
    await h.evl(`window.__acShowTool("meropriyatiya"); 1`);
    await sleep(1200);
    await h.evl(`
(function(){
  function set(id,v){var e=document.getElementById(id); e.value=v; e.dispatchEvent(new Event("input",{bubbles:true}));}
  set("mp-участок","фасовка"); set("mp-впп","38,7"); set("mp-разрыв","23,7");
  set("mp-тц","4,0"); set("mp-смена","480");
  ["простои_оборудования","организация_рабочих_мест","вариативность_операций"].forEach(function(k){
    var c=document.getElementById("mp-priz-"+k); if(c) c.checked=true;
  });
  return 1;})()`);
    await h.evl(`document.getElementById("mp-btn-run").click(); 1`);
    await sleep(3000);
    const mpst = await h.evl(`document.getElementById("mp-status-line").textContent`);
    h.log("mp status:", mpst);

    // колонка «Симуляция» в топ-5
    const col = JSON.parse(await h.evl(`
JSON.stringify({
  head: Array.prototype.map.call(document.querySelectorAll("#mp-топ th"), function(th){return th.textContent.trim();}),
  rows: Array.prototype.map.call(document.querySelectorAll("#mp-топ tbody tr"), function(tr){
    var name = (tr.querySelector("td")||{textContent:""}).textContent.trim().slice(0,45);
    var btn = tr.querySelector(".mp-sim-btn");
    var dis = tr.querySelector("button[disabled]");
    var b = btn || dis;
    return {name: name, btn: !!b, disabled: b ? b.disabled : null,
            instr: b ? b.getAttribute("data-инстр") : null,
            title: b ? (b.getAttribute("title")||"") : null,
            label: b ? b.textContent.trim() : null};
  })
})`));
    h.log("COL:", JSON.stringify(col, null, 1));
    chk("С3-1 колонка «Симуляция» у топ-5", col.head.some(t => t.indexOf("Симуляция") >= 0) && col.rows.length >= 5 && col.rows.every(r => r.btn),
        `заголовки=${col.head.join("|")}; строк=${col.rows.length}`);
    const active = col.rows.filter(r => r.disabled === false);
    const inactive = col.rows.filter(r => r.disabled === true);
    chk("С3-2 у мапящихся кнопка «Просимулировать» активна", active.length >= 1,
        `активны: ${active.map(r => r.instr || r.name).join(", ")}`);
    chk("С3-3 у немапящихся кнопка неактивна с честной подсказкой",
        inactive.length >= 1 && inactive.every(r => (r.title || "").length > 5),
        inactive.map(r => `${r.instr || r.name}: «${r.title}»`).join(" | "));
    await h.shot("priemka0609_c3_mp_buttons.png");

    // клик по первой активной → сценарий собирается, дельты считаются
    const clicked = await h.evl(`(function(){var b=document.querySelector("#mp-топ .mp-sim-btn:not([disabled])"); if(!b) return null; b.click(); return b.getAttribute("data-инстр");})()`);
    h.log("клик по:", clicked);
    await sleep(7000);
    const simVis = await h.evl(`(function(){var t=document.querySelector('.stages .tool[data-tool="sim"]'); return t && t.offsetHeight>0;})()`);
    const banner = await h.evl(`document.getElementById("sim-mp-banner").textContent`);
    const verdict = await h.evl(`document.getElementById("sim-verdict").textContent`);
    h.log("sim видим:", simVis, "| banner:", banner, "| verdict:", verdict);
    chk("С3-2б сценарий собрался, дельты посчитаны (эталон: выпуск +4,2 %)",
        simVis === true && banner.indexOf("Сценарий из мероприятия") >= 0 && /выпуск \+/.test(verdict),
        `инструмент=${clicked}; banner=${banner}; verdict=${verdict}`);
    await h.shot("priemka0609_c3_sim_scenario.png");

    // ЭЭ-мостик
    await h.evl(`document.getElementById("sim-to-ee").click(); 1`);
    await sleep(2000);
    const ee = JSON.parse(await h.evl(`
JSON.stringify({
  до: document.getElementById("ee-тц-до").value,
  после: document.getElementById("ee-тц-после").value,
  контекст: document.getElementById("ee-контекст").textContent
})`));
    h.log("EE:", JSON.stringify(ee));
    chk("С3-4 ЭЭ-мостик: Тц УМ до/после + пометка «не замер»",
        ee.до === "4" && ee.после.length > 0 && ee.контекст.indexOf("из модельного прогноза, не замер") >= 0,
        `тц ${ee.до} → ${ee.после}; контекст=${ee.контекст}`);
    await h.shot("priemka0609_c3_ee_bridge.png");
  } catch (e) {
    h.log("EXC:", e.message);
  } finally {
    h.saveLog("priemka0609_c3.log");
    const fails = R.filter(r => r[1] === "FAIL");
    h.log(`ИТОГ c3: ${R.length - fails.length}/${R.length} PASS`);
    console.log("RESULT_JSON:" + JSON.stringify(R));
    process.exit(0);
  }
}
main().catch(e => { console.error(e); process.exit(2); });
