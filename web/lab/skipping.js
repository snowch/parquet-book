// The skipping laboratory (ch09): a condition on one column, and what the reader skips to answer
// SELECT * with it: row groups ruled out by statistics or a Bloom filter, pages ruled out by the
// page index, and the bytes it still reads.
//
// Every decision, reason and byte count is `report::skipping`, computed by the Rust reader. The
// matching-row count is the reader's too: it decodes the whole column to check the plan.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const span = (s) => escapeHtml(JSON.stringify(s));
const OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];
const MECHANISMS = [[1, "Row group statistics"], [2, "Bloom filters"], [4, "The page index"]];

export function mountSkipping(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const form = document.createElement("form");
  form.className = "controls skip-form";
  form.innerHTML = `
    <label>Where <select name="column"></select></label>
    <select name="op" aria-label="comparison">${OPS.map((o) => `<option>${escapeHtml(o)}</option>`).join("")}</select>
    <input name="value" size="12" aria-label="value">
    <button type="submit">Plan the read</button>
    <fieldset class="mechanisms"><legend>The reader may use</legend>${MECHANISMS.map(([bit, label]) =>
      `<label><input type="checkbox" name="m" value="${bit}" checked> ${label}</label>`).join("")}</fieldset>`;
  root.append(form);
  const grid = document.createElement("div");
  grid.className = "skip-grid";
  grid.innerHTML = `
    <section class="panel p-skip-sum"><h4>What the reader reads</h4><div class="skip-sum"></div></section>
    <section class="panel p-skip-groups"><h4>Row group by row group</h4><div class="skip-groups"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });

  form.elements.op.value = config.op || "=";
  form.elements.value.value = config.value || "";
  let column = Number(config.column || 0);

  const mechanisms = () => [...form.querySelectorAll('input[name="m"]:checked')].reduce((a, i) => a + Number(i.value), 0);
  const run = () => {
    const op = form.elements.op.value;
    form.elements.value.disabled = op.startsWith("is ");
    const r = lab.skipping(views.id, column, op, form.elements.value.value, mechanisms());
    if (r.columns) {
      form.elements.column.innerHTML = r.columns.map((c) =>
        `<option value="${c.column}"${c.column === column ? " selected" : ""}>${escapeHtml(c.path)}</option>`).join("");
    }
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".skip-sum").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      grid.querySelector(".skip-groups").innerHTML = "";
      return;
    }
    root.dataset.bytesRead = String(r.totals.bytes_read);
    root.dataset.matching = String(r.totals.rows_matching);
    root.dataset.skipped = r.row_groups.map((g) => (g.skipped ? "skip" : "read")).join(",");
    drawSummary(grid.querySelector(".skip-sum"), r);
    drawGroups(grid.querySelector(".skip-groups"), r);
  };
  views.onChange = run;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    column = Number(form.elements.column.value);
    run();
  });
  form.addEventListener("change", (e) => {
    if (e.target.name === "value") return;
    column = Number(form.elements.column.value);
    run();
  });
  grid.addEventListener("click", (e) => {
    const t = e.target.closest("[data-span]");
    if (!t) return;
    const s = JSON.parse(t.dataset.span);
    views.hex.highlight(s);
    views.hex.select(s[0], s[1]);
  });
  const choose = fileChooser(head, files, initial, async (name) => views.open(name, await files.get(name)));
  choose();
}

function bar(part, whole) {
  const pct = whole ? Math.min(100, (part / whole) * 100) : 0;
  return `<span class="bar"><i style="width:${pct.toFixed(1)}%"></i></span>`;
}

function drawSummary(box, r) {
  const t = r.totals;
  box.innerHTML = `<p><code>SELECT * WHERE ${escapeHtml(r.condition)}</code></p>` +
    `<div class="bars"><div class="bar-row"><span>Full scan</span>${bar(t.bytes_full_scan, t.bytes_full_scan)}<span>${fmt(t.bytes_full_scan)} bytes</span></div>` +
    `<div class="bar-row"><span>This plan</span>${bar(t.bytes_read, t.bytes_full_scan)}<span>${fmt(t.bytes_read)} bytes</span></div>` +
    `<div class="bar-row"><span>To decide</span>${bar(t.index_bytes, t.bytes_full_scan)}<span>${fmt(t.index_bytes)} bytes</span></div></div>` +
    `<p class="note">The plan decodes ${fmt(t.rows_read)} of ${fmt(t.rows)} rows, and ${fmt(t.rows_matching)} match, ` +
    `found by the reader decoding the whole column to check. "To decide" is the Bloom filters and page indexes the plan fetched; ` +
    `the footer's statistics are already in memory.</p>`;
}

function drawGroups(box, r) {
  box.innerHTML = r.row_groups.map((g) => {
    const steps = g.steps.length
      ? g.steps.map((s) => `<li class="${s.skip ? "skip" : "keep"}"><strong>${escapeHtml(s.mechanism)}</strong>: ` +
          `${s.skip ? "skip" : "read"}, because ${escapeHtml(s.why)}</li>`).join("")
      : "<li>No mechanism consulted: read everything.</li>";
    const bloom = g.bloom
      ? `<p class="bloom">Hash <code>${escapeHtml(g.bloom.hash)}</code> chose <button type="button" class="span" data-span="${span(g.bloom.block_span)}">block ${g.bloom.block} of ${g.bloom.blocks}</button>; ` +
        `bits tested: ${g.bloom.bits.map((b) => `<span class="${b.set ? "set" : "clear"}">${b.bit}</span>`).join(" ")}</p>`
      : "";
    const pages = g.pages.length
      ? `<div class="page-strip">${g.pages.map((p) => `<button type="button" class="pg ${p.skip ? "skip" : "keep"}" data-span="${span(p.span)}" ` +
          `title="rows ${p.rows[0]} to ${p.rows[1] - 1}: ${escapeHtml(p.why)}" style="flex:${p.rows[1] - p.rows[0]}">${p.rows[0]}</button>`).join("")}</div>`
      : "";
    const reads = g.reads.length
      ? `<ul class="reads">${g.reads.map((c) => `<li><code>${escapeHtml(c.path)}</code>: ${fmt(c.bytes)} bytes` +
          `${c.pages_total ? `, ${c.pages_read} of ${c.pages_total} pages` : ""} ` +
          c.spans.map((s) => `<button type="button" class="span" data-span="${span(s)}">${s[0]}–${s[1] - 1}</button>`).join(" ") + "</li>").join("")}</ul>`
      : "";
    return `<article class="rg ${g.skipped ? "skipped" : ""}"><h5>Row group ${g.index} <small>${fmt(g.num_rows)} rows, ${fmt(g.matching)} matching</small>` +
      ` <span class="verdict">${g.skipped ? "skipped" : "read"}</span></h5><ul class="steps">${steps}</ul>${bloom}${pages}${reads}</article>`;
  }).join("");
}
