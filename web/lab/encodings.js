// The encodings laboratory (ch05): step through how one column's values were encoded, byte range
// by byte range, and compare the result with PLAIN.
//
// The steps are the Rust decoder's own record of what it read (`decode::Step`); the values are
// what it produced; the sizes are measured from the page. Stepping highlights each step's bytes.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const span = (s) => escapeHtml(JSON.stringify(s));

export function mountEncodings(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const picker = document.createElement("div");
  picker.className = "controls column-picker";
  root.append(picker);
  const grid = document.createElement("div");
  grid.className = "enc-grid";
  grid.innerHTML = `
    <section class="panel p-summary"><h4>What the encoding saved</h4><div class="summary"></div></section>
    <section class="panel p-steps-enc"><h4>How the decoder read it</h4>
      <div class="stepper"><button type="button" data-step="-1">Previous step</button>
      <button type="button" data-step="1">Next step</button><span class="where"></span></div>
      <ol class="enc-steps"></ol></section>
    <section class="panel p-dict"><h4>Dictionary</h4><div class="dict"></div></section>
    <section class="panel p-values"><h4>Decoded values</h4><div class="enc-values"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });

  let column = Number(config.column || 0);
  let steps = [];
  let current = -1;

  const highlight = (s) => {
    views.hex.highlight(s);
    views.hex.select(s[0], s[1]);
  };
  const goto = (i) => {
    if (!steps.length) return;
    current = Math.max(0, Math.min(steps.length - 1, i));
    for (const li of grid.querySelectorAll(".enc-steps li")) li.classList.toggle("current", Number(li.dataset.i) === current);
    grid.querySelector(".where").textContent = `step ${current + 1} of ${steps.length}`;
    highlight(steps[current].span);
    root.dataset.step = String(current);
  };

  const run = () => {
    const r = lab.encodings(views.id, column);
    root.dataset.state = r.ok ? "ok" : "error";
    if (r.columns) drawPicker(picker, r.columns, column);
    if (!r.ok) {
      grid.querySelector(".summary").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      for (const k of [".enc-steps", ".dict", ".enc-values"]) grid.querySelector(k).innerHTML = "";
      steps = [];
      return;
    }
    steps = r.pages.flatMap((p) => p.steps);
    current = -1;
    root.dataset.encoding = r.pages.map((p) => p.encoding).join(",");
    root.dataset.values = JSON.stringify(r.values.map((v) => v.value));
    drawSummary(grid.querySelector(".summary"), r);
    grid.querySelector(".enc-steps").innerHTML = steps.map((s, i) =>
      `<li data-i="${i}"><button type="button" class="span" data-span="${span(s.span)}">${escapeHtml(s.label)}</button> ` +
      `<span class="detail">${escapeHtml(s.detail)}</span></li>`).join("");
    grid.querySelector(".where").textContent = `${steps.length} steps`;
    drawDict(grid.querySelector(".dict"), r);
    grid.querySelector(".enc-values").innerHTML = `<ol class="value-list" start="0">${r.values.map((v) =>
      `<li><button type="button" class="span" data-span="${span(v.span)}">${escapeHtml(JSON.stringify(v.value))}</button></li>`).join("")}</ol>`;
  };
  views.onChange = run;

  picker.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-column]");
    if (!b) return;
    column = Number(b.dataset.column);
    run();
  });
  grid.addEventListener("click", (e) => {
    const step = e.target.closest("button[data-step]");
    if (step) return goto(current + Number(step.dataset.step));
    const t = e.target.closest("[data-span]");
    if (!t) return;
    const li = t.closest(".enc-steps li");
    if (li) return goto(Number(li.dataset.i));
    highlight(JSON.parse(t.dataset.span));
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
    `<code>${escapeHtml(c.path)}</code> <small>${escapeHtml((c.encodings || []).filter((e) => e !== "RLE" || c.encodings.length === 1).join(", "))}</small>` +
    "</button>").join("")}</fieldset>`;
}

function drawSummary(box, r) {
  const { encoded, plain, count } = r.sizes;
  const pct = plain ? Math.round((encoded / plain) * 100) : 0;
  box.innerHTML = `<p><code>${escapeHtml(r.path)}</code>: ${fmt(count)} ${escapeHtml(r.physical_type)} values` +
    `${r.logical_type ? ` (${escapeHtml(r.logical_type)})` : ""}, encoded with <strong>${escapeHtml([...new Set(r.pages.map((p) => p.encoding))].join(", "))}</strong>.</p>` +
    `<div class="bars"><div class="bar-row"><span>PLAIN</span><span class="bar"><i style="width:100%"></i></span><span>${fmt(plain)} bytes</span></div>` +
    `<div class="bar-row"><span>As stored</span><span class="bar"><i style="width:${Math.min(100, pct)}%"></i></span><span>${fmt(encoded)} bytes</span></div></div>` +
    `<p class="note">Stored size is the encoded values${r.dictionary ? " plus the dictionary page's body" : ""}; ` +
    `it is ${pct}% of PLAIN. Levels and page headers are not counted in either.</p>`;
}

function drawDict(box, r) {
  if (!r.dictionary) {
    box.innerHTML = '<p class="note">None: this column is not dictionary-encoded.</p>';
    return;
  }
  box.innerHTML = `<p class="note">The dictionary page stores each distinct value once, PLAIN. ` +
    `<button type="button" class="span" data-span="${span(r.dictionary.body)}">its body</button></p>` +
    `<ol class="value-list" start="0">${r.dictionary.entries.map((e) =>
      `<li><button type="button" class="span" data-span="${span(e.span)}">${escapeHtml(JSON.stringify(e.value))}</button></li>`).join("")}</ol>`;
}
