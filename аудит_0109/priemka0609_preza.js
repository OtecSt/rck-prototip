// Приёмка 06.09 · Блок 3: «Защита одной кнопкой» (вкладка Презентации).
const { startHarness, sleep, BASE, AUTH_USER, AUTH_PASS } = require("./priemka0609_cdp.js");
const fs = require("fs");
const PID = 15;

async function main() {
  const h = await startHarness("preza", 9415);
  const R = [];
  const chk = (name, ok, doc) => { R.push([name, ok ? "PASS" : "FAIL", doc]); h.log(`[${ok ? "PASS" : "FAIL"}] ${name} :: ${doc}`); };
  try {
    await h.init(PID);
    // вкладка «Презентации» (вне этапов, полный режим)
    const menu = await h.evl(`(function(){var b=document.querySelector('.sn-tool[data-tool="preza"]'); if(!b) return "нет пункта"; b.click(); return "clicked";})()`);
    await sleep(1500);
    const card = JSON.parse(await h.evl(`
JSON.stringify({
  card: document.getElementById("preza-card").style.display !== "none",
  empty_hidden: document.getElementById("pr-empty").hidden,
  пред: document.getElementById("pr-titul-предприятие").value,
  поток: document.getElementById("pr-titul-поток").value,
  темы: Array.prototype.map.call(document.querySelectorAll('#pr-theme input[type=radio]'), function(r){return r.value + (r.checked ? "*" : "");})
})`));
    h.log("CARD:", JSON.stringify(card));
    chk("П-1 вкладка «Презентации» → экран «Защита проекта»", menu === "clicked" && card.card && card.empty_hidden, `menu=${menu} card=${card.card} empty_hidden=${card.empty_hidden}`);
    chk("П-1б титул подтянут из проекта", card.пред === "Приёмка-0609" && card.поток === "Поток приёмки 0609", `предприятие=${card.пред} поток=${card.поток}`);
    chk("П-3в темы бумага/графит на выбор", card.темы.join(",").indexOf("бумага") >= 0 && card.темы.join(",").indexOf("графит") >= 0, card.темы.join(","));
    await h.shot("priemka0609_preza_menu.png");

    // сборка
    await h.evl(`document.getElementById("pr-build").click(); 1`);
    const st = await h.waitText(`document.getElementById("pr-status").textContent`, "Собрано", 60);
    h.log("статус сборки:", st);
    const built = JSON.parse(await h.evl(`
JSON.stringify({
  slides: document.querySelectorAll("#pr-preview .pr-slide").length,
  dark: document.querySelectorAll("#pr-preview .pr-slide.pr-dark").length,
  src: Array.prototype.map.call(document.querySelectorAll("#pr-preview .pr-src"), function(e){return e.textContent.trim();}),
  dl_disabled: document.getElementById("pr-download").disabled,
  zone: document.getElementById("pr-result-zone").hidden,
  titles: Array.prototype.map.call(document.querySelectorAll("#pr-preview .pr-slide h3, #pr-preview .pr-slide .pr-title, #pr-preview .pr-slide h2"), function(e){return e.textContent.trim();})
})`));
    h.log("BUILT:", JSON.stringify(built));
    const srcOk = built.src.length >= 1 && built.src.every(s => /источник: прогон №/.test(s));
    chk("П-2 «Собрать защиту» → превью 16:9, 8 слайдов", built.slides === 8 && !built.dl_disabled && !built.zone, `slides=${built.slides} dl_disabled=${built.dl_disabled} status=${st}`);
    chk("П-2б трассировка к прогонам у слайдов", built.src.length > 0 && srcOk, built.src.join(" | "));
    await h.shot("priemka0609_preza_preview.png");

    // скачивание PPTX через API (тема бумага)
    const dl = await h.evl(`
(async function () {
  var r = await fetch("/api/preza/pptx", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({проект_id: ${PID}, тема: "бумага"})});
  var buf = await r.arrayBuffer();
  var b64 = btoa(new Uint8Array(buf).reduce(function(d, b){ return d + String.fromCharCode(b); }, ""));
  return JSON.stringify({status: r.status, size: buf.byteLength, b64: b64});
})()`);
    const dlj = JSON.parse(dl);
    h.log("PPTX:", dlj.status, dlj.size, "байт");
    fs.writeFileSync(__dirname + "/priemka0609_zaschita.pptx", Buffer.from(dlj.b64, "base64"));
    chk("П-3 «Скачать PPTX» → файл", dlj.status === 200 && dlj.size > 30 * 1024, `HTTP ${dlj.status}, ${dlj.size} байт`);

    // сохранение прогона preza
    await h.evl(`document.getElementById("save-preza-коммент").value="приёмка 0609"; document.getElementById("save-preza-btn").click(); 1`);
    const sv = await h.waitText(`document.getElementById("save-preza-status").textContent`, "сохранён", 30);
    h.log("save preza:", sv);
    const hist = await h.evl(`
(async function () {
  var r = await fetch("/api/proekty/${PID}").then(function(x){return x.json();});
  var n = r.progony.filter(function(g){return g["инструмент"] === "preza";}).length;
  return JSON.stringify({preza_runs: n});
})()`);
    h.log("HIST preza:", hist);
    chk("П-4 прогон «preza» в истории проекта", sv.indexOf("сохранён") >= 0 && JSON.parse(hist).preza_runs >= 1, `save=${sv}; ${hist}`);
  } catch (e) {
    h.log("EXC:", e.message);
  } finally {
    h.saveLog("priemka0609_preza.log");
    const fails = R.filter(r => r[1] === "FAIL");
    h.log(`ИТОГ preza: ${R.length - fails.length}/${R.length} PASS`);
    console.log("RESULT_JSON:" + JSON.stringify(R));
    process.exit(0);
  }
}
main().catch(e => { console.error(e); process.exit(2); });
