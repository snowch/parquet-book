// The levels laboratory (ch04): one column's repetition and definition levels, the values beside
// them, what each triple means, and the records rebuilt from them.
//
// Everything is `report::levels` from Rust: the level runs are decoded from the page bytes, the
// explanations are `nested::explain`, and the records are `nested::assemble`. Selecting a triple,
// a run or a value highlights the bytes it came from.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const span = (s) => escapeHtml(JSON.stringify(s));
const show = (v) => (v === null || v === undefined ? "·" : escapeHtml(JSON.stringify(v)));

export function mountLevels(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const picker = document.createElement("div");
  picker.className = "controls column-picker";
  root.append(picker);
  const grid = document.createElement("div");
  grid.className = "levels-grid";
  grid.innerHTML = `
    <section class="panel p-path"><h4>The column's path</h4><div class="path"></div></section>
    <section class="panel p-runs"><h4>The levels, as stored</h4><div class="runs"></div></section>
    <section class="panel p-triples"><h4>Triples: repetition, definition, value</h4><div class="triples"></div></section>
    <section class="panel p-records"><h4>Records rebuilt from them</h4><div class="records"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });

  let column = Number(config.column || 0);
  const run = () => {
    const r = lab.levels(views.id, column);
    root.dataset.state = r.ok ? "ok" : "error";
    if (r.columns) drawPicker(picker, r.columns, column);
    if (!r.ok) {
      grid.querySelector(".triples").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      for (const k of [".path", ".runs", ".records"]) grid.querySelector(k).innerHTML = "";
      return;
    }
    root.dataset.triples = String(r.triples.length);
    root.dataset.records = JSON.stringify(r.records);
    drawPath(grid.querySelector(".path"), r);
    drawRuns(grid.querySelector(".runs"), r);
    drawTriples(grid.querySelector(".triples"), r);
    drawRecords(grid.querySelector(".records"), r);
  };
  views.onChange = run;

  picker.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-column]");
    if (!b) return;
    column = Number(b.dataset.column);
    run();
  });
  root.addEventListener("click", (e) => {
    const t = e.target.closest("[data-span]");
    if (!t || !grid.contains(t)) return;
    for (const m of grid.querySelectorAll(".levels-picked")) m.classList.remove("levels-picked");
    t.classList.add("levels-picked");
    const s = JSON.parse(t.dataset.span);
    views.hex.highlight(s);
    views.hex.select(s[0], s[1]);
  });

  const choose = fileChooser(head, files, initial, async (name) => {
    column = Number(config.column || 0);
    await views.open(name, await files.get(name));
  });
  choose();
}

function drawPicker(box, columns, current) {
  box.innerHTML = `<fieldset><legend>Column</legend>${columns.map((c) =>
    `<button type="button" data-column="${c.column}"${c.column === current ? ' aria-pressed="true"' : ""}>` +
    `<code>${escapeHtml(c.label)}</code> <small>d ≤ ${c.max_definition_level}, r ≤ ${c.max_repetition_level}</small>` +
    "</button>").join("")}</fieldset>`;
}

function drawPath(box, r) {
  box.innerHTML = `<table class="path-table"><thead><tr><th>Field</th><th>Repetition</th>` +
    `<th>d when present</th><th>r of its list</th></tr></thead><tbody>` +
    r.fields.map((f) => `<tr><td><code>${escapeHtml(f.name)}</code>${f.list ? " <small>(LIST)</small>" : ""}</td>` +
      `<td>${f.repetition}</td><td>${f.definition_level}</td>` +
      `<td>${f.repetition === "repeated" ? f.repetition_level : ""}</td></tr>`).join("") +
    `</tbody></table><p class="note">Maximum definition level ${r.max_definition_level}, ` +
    `maximum repetition level ${r.max_repetition_level}.</p>`;
}

function streamHtml(name, stream) {
  if (!stream) return `<p class="note">${name}: none stored; the maximum is 0.</p>`;
  return `<p class="stream-title">${name} <button type="button" class="span" data-span="${span(stream.span)}">` +
    `[${stream.span[0]}, ${stream.span[1]})</button></p><ol class="runs-list">` +
    stream.runs.map((run) => `<li><button type="button" class="span" data-span="${span(run.header)}">header</button> ` +
      `${run.kind} run, <button type="button" class="span" data-span="${span(run.body)}">body</button> → ` +
      `<code>${run.values.join(" ")}</code></li>`).join("") + "</ol>";
}

function drawRuns(box, r) {
  box.innerHTML = r.pages.map((p, i) =>
    `<div class="page-runs"><p class="note">Page ${i}${r.pages.some((q) => q.row_group) ? `, row group ${p.row_group}` : ""}: ` +
    `four-byte length, then the runs.</p>` +
    streamHtml("Repetition levels", p.repetition_levels) +
    streamHtml("Definition levels", p.definition_levels) +
    `<p class="stream-title">Values <button type="button" class="span" data-span="${span(p.values)}">` +
    `[${p.values[0]}, ${p.values[1]})</button></p></div>`).join("");
}

function drawTriples(box, r) {
  box.innerHTML = `<div class="table-wrap"><table class="triples-table"><thead><tr><th>#</th><th>r</th><th>d</th>` +
    `<th>Value</th><th>Meaning</th></tr></thead><tbody>` +
    r.triples.map((t, i) => `<tr class="${t.rep === 0 ? "record-start" : ""}"><td>${i}</td><td>${t.rep}</td><td>${t.def}</td>` +
      `<td>${t.value_span ? `<button type="button" class="span" data-span="${span(t.value_span)}">${show(t.value)}</button>` : "·"}</td>` +
      `<td class="meaning">${escapeHtml(t.explain).replace(/`([^`]+)`/g, "<code>$1</code>")}</td></tr>`).join("") +
    "</tbody></table></div>";
}

function drawRecords(box, r) {
  box.innerHTML = `<ol class="records-list" start="0">${r.records.map((rec) =>
    `<li><code>${escapeHtml(JSON.stringify(rec))}</code></li>`).join("")}</ol>`;
}
