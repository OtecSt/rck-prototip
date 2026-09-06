// Приёмка 06.09 · Блоки С2.1, С2.2, Д3.1-2 (история sim), Д3.1-5 (пресет Пока-йоке).
const { startHarness, sleep } = require("./priemka0609_cdp.js");
const PID = 15;

const FILL = `
(function () {
  function setV(id, v) { var e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
  setV("sim-поток", "Поток приёмки 0609");
  setV("sim-спрос", "300");
  setV("sim-время", "480");
  setV("sim-численность", "5");
  var tbody = document.getElementById("sim-ops-body");
  var ops = [["Оп1", "1,9"], ["Оп2", "2"], ["Оп3", "1,5"]];
  while (tbody.rows.length < ops.length) document.getElementById("sim-btn-add").click();
  ops.forEach(function (o, i) {
    var tr = tbody.rows[i];
    function set(cls, v) { var e = tr.querySelector(cls); e.value = v; e.dispatchEvent(new Event("input", {bubbles: true})); }
    set(".c-имя", o[0]); set(".c-ту", o[1]); set(".c-исп", ""); set(".c-брак", ""); set(".c-пер", ""); set(".c-партия", ""); set(".c-зап", "");
  });
  return "filled:" + tbody.rows.length;
})()`;

const SLIDER = (box, v) => `
(function () {
  var inp = document.getElementById("sim-scen-ops").children[${box}].querySelector('input[type="range"]');
  inp.value = ${v};
  inp.dispatchEvent(new Event("input", {bubbles: true}));
  return inp.value;
})()`;

async function main() {
  const h = await startHarness("sim", 9411);
  const R = [];
  const chk = (name, ok, doc) => { R.push([name, ok ? "PASS" : "FAIL", doc]); h.log(`[${ok ? "PASS" : "FAIL"}] ${name} :: ${doc}`); };
  try {
    await h.init(PID);
    await h.evl(`window.__acShowTool("sim"); 1`);
    await sleep(1200);
    h.log("заполнение:", await h.evl(FILL));
    const st = await h.waitText(`document.getElementById("sim-status-line").textContent`, "База посчитана");
    h.log("статус базы:", st);

    // --- С2.2: шапка, допущения, подсказки ---
    const c22 = JSON.parse(await h.evl(`
(function () {
  var lead = document.querySelector(".tool[data-tool='sim'] .sim-lead");
  var dop = document.querySelector(".tool[data-tool='sim'] details.sim-dop-all");
  var slTips = document.querySelectorAll("#sim-scen-ops .sim-sl .f-tip");
  var tbTips = document.querySelectorAll("#sim-cmp-body .f-tip");
  var t0 = slTips[0]; var fixed0 = false;
  if (t0) { t0.dispatchEvent(new MouseEvent("mouseover", {bubbles: true})); fixed0 = t0.classList.contains("tip-fixed"); t0.dispatchEvent(new MouseEvent("mouseout", {bubbles: true})); }
  var leadR = lead ? lead.getBoundingClientRect() : {width:0,height:0};
  return JSON.stringify({
    lead_text: lead ? lead.textContent.trim() : null,
    lead_visible: !!(lead && leadR.width > 0 && leadR.height > 0),
    dop_open: dop ? dop.open : null,
    dop_summary: dop ? dop.querySelector("summary").textContent.trim() : null,
    slider_tips: slTips.length, table_tips: tbTips.length, tip_fixed_works: fixed0
  });
})()`));
    h.log("C22:", JSON.stringify(c22));
    chk("С2.2а строка пользы", c22.lead_visible && (c22.lead_text || "").startsWith("Что вы получите:"), c22.lead_text);
    chk("С2.2б допущения под раскрытием", c22.dop_open === false && c22.dop_summary === "Как пользоваться и допущения модели", `open=${c22.dop_open} summary=${c22.dop_summary}`);
    chk("С2.2в вопросики у ползунков и строк", c22.slider_tips >= 8 && c22.table_tips >= 6 && c22.tip_fixed_works, `sliders=${c22.slider_tips} table=${c22.table_tips} fixed=${c22.tip_fixed_works}`);
    await h.shot("priemka0609_sim_lead.png");

    // --- С2.1: метка УМ ---
    const um = JSON.parse(await h.evl(`
(function () {
  var flags = document.querySelectorAll("#sim-scen-ops .sim-um-flag");
  var names = Array.prototype.map.call(document.querySelectorAll("#sim-scen-ops .sim-scen-name"), function (e) { return e.textContent; });
  return JSON.stringify({flags: flags.length, flag_text: flags[0] ? flags[0].textContent : null, names: names});
})()`));
    h.log("UM:", JSON.stringify(um));
    chk("С2.1а метка «⚑ узкое место»", um.flags === 1 && (um.flag_text || "").indexOf("узкое место") >= 0, `flags=${um.flags} text=${um.flag_text} у ${um.names.join("/")}`);
    await h.shot("priemka0609_sim_um_mark.png");

    // --- С2.1: ползунок НЕ на УМ (Оп1) → честный ноль ---
    await h.evl(SLIDER(0, -20));
    const st1 = await h.waitText(`document.getElementById("sim-status-line").textContent`, "Сценарий пересчитан");
    h.log("статус после ползунка не-УМ:", st1);
    const zero = JSON.parse(await h.evl(`
(function () {
  var note = document.getElementById("sim-zero-note");
  var zeros = document.querySelectorAll("#sim-cmp-body td.dl-zero");
  var firstRow = document.querySelector("#sim-cmp-body tr");
  return JSON.stringify({
    note_hidden: note.hidden, note_text: note.textContent,
    zero_cells: zeros.length,
    row0: firstRow ? firstRow.textContent.replace(/\\s+/g, " ").trim() : null
  });
})()`));
    h.log("ZERO:", JSON.stringify(zero));
    chk("С2.1б дельта 0 + пояснение", !zero.note_hidden && zero.zero_cells >= 1 && zero.note_text.indexOf("улучшение не на узком месте") >= 0, `note=${zero.note_text} | zero_cells=${zero.zero_cells} | row0=${zero.row0}`);
    await h.shot("priemka0609_sim_zero_delta.png");

    // --- С2.1: ползунок на УМ (Оп2) → выпуск растёт ---
    await h.evl(`document.getElementById("sim-btn-reset").click(); 1`);
    await sleep(800);
    const baseVyp = await h.evl(`(function(){var r=document.querySelector("#sim-cmp-body tr td"); return r ? r.textContent : null;})()`);
    await h.evl(SLIDER(1, -20));
    const st2 = await h.waitText(`document.getElementById("sim-status-line").textContent`, "Сценарий пересчитан");
    h.log("статус после ползунка УМ:", st2);
    const up = JSON.parse(await h.evl(`
(function () {
  var v = document.getElementById("sim-verdict");
  var rows = Array.prototype.map.call(document.querySelectorAll("#sim-cmp-body tr"), function (tr) { return tr.textContent.replace(/\\s+/g, " ").trim(); });
  return JSON.stringify({verdict_hidden: v.hidden, verdict: v.textContent, rows: rows.slice(0, 3)});
})()`));
    h.log("UP:", JSON.stringify(up));
    chk("С2.1в выпуск растёт на УМ", !up.verdict_hidden && /выпуск \+/.test(up.verdict), `verdict=${up.verdict} | ${up.rows.join(" | ")}`);
    chk("С2.2г «Итог сценария» человеческим языком", !up.verdict_hidden && up.verdict.startsWith("Итог сценария:"), up.verdict);
    await h.shot("priemka0609_sim_verdict.png");

    // --- Д3.1-5: пресет Пока-йоке ---
    await h.evl(`document.getElementById("sim-btn-reset").click(); 1`);
    await sleep(800);
    await h.evl(`document.getElementById("sim-preset-poka").click(); 1`);
    await sleep(2500);
    const poka = JSON.parse(await h.evl(`
(function () {
  var sliders = Array.prototype.map.call(document.querySelectorAll("#sim-scen-ops .sim-sl"), function (sl) {
    var lab = sl.querySelector("label, .sim-sl-label, span");
    var inp = sl.querySelector('input[type="range"]');
    return {lab: lab ? lab.textContent.replace(/\\s+/g," ").trim() : "", min: inp.min, val: inp.value};
  }).filter(function (s) { return s.lab.indexOf("Брак") === 0; });
  return JSON.stringify({брак: sliders, status: document.getElementById("sim-status-line").textContent});
})()`));
    h.log("POKA:", JSON.stringify(poka));
    const allMinus70 = poka.брак.length === 3 && poka.брак.every(s => s.val === "-70");
    const min90 = poka.брак.every(s => s.min === "-90");
    chk("Д3.1-5 пресет «Пока-йоке −70 %» честно", allMinus70 && min90, `слайдеры Брак=${poka.брак.map(s => s.val).join(",")} min=${poka.брак.map(s => s.min).join(",")}`);
    await h.shot("priemka0609_sim_preset.png");

    // --- Д3.1-2: история sim + «→ в форму» ---
    await h.evl(`document.getElementById("save-sim-метка").value="приёмка0609"; document.getElementById("save-sim-btn").click(); 1`);
    const sv = await h.waitText(`document.getElementById("save-sim-status").textContent`, "сохранён", 30);
    h.log("save sim:", sv);
    await sleep(1000);
    const hist = JSON.parse(await h.evl(`
(function () {
  var rows = document.querySelectorAll("#hist-sim-list [data-load]");
  return JSON.stringify({rows: rows.length, block_hidden: document.getElementById("hist-sim-block").hidden});
})()`));
    h.log("HIST sim:", JSON.stringify(hist));
    // портим форму, затем грузим прогон обратно
    await h.evl(`(function(){var e=document.getElementById("sim-спрос"); e.value="999"; e.dispatchEvent(new Event("input",{bubbles:true})); return 1;})()`);
    await sleep(600);
    const loadRes = await h.evl(`
(function () {
  var b = document.querySelector("#hist-sim-list [data-load]");
  if (!b) return "нет кнопки";
  b.click();
  return "clicked:" + b.getAttribute("data-load");
})()`);
    await sleep(1500);
    const after = await h.evl(`document.getElementById("sim-спрос").value`);
    h.log("→ в форму:", loadRes, "спрос после:", after);
    chk("Д3.1-2 история sim + «→ в форму»", sv.indexOf("сохранён") >= 0 && hist.rows >= 1 && after === "300", `save=${sv}; кнопок в истории=${hist.rows}; спрос после загрузки=${after}`);
    await h.shot("priemka0609_sim_history.png");
  } catch (e) {
    h.log("EXC:", e.message);
  } finally {
    h.saveLog("priemka0609_sim.log");
    const fails = R.filter(r => r[1] === "FAIL");
    h.log(`ИТОГ sim: ${R.length - fails.length}/${R.length} PASS`);
    console.log("RESULT_JSON:" + JSON.stringify(R));
    process.exit(fails.length ? 1 : 0);
  }
}
main().catch(e => { console.error(e); process.exit(2); });
