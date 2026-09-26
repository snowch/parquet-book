// The table laboratory (ch14): a query over a table of many files in the simulated object store,
// with the files found by listing or by the table's log, and each file read or ruled out.
//
// Everything is `report::table`: the Rust reader listed or read the log, decided which files to
// read, fetched them through the store, and ran the ch12 engine over them.

import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const ms = (us) => `${(us / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} ms`;
const cell = (v) => escapeHtml(v === null ? "null" : String(v));

const EXAMPLES = [
  "SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200",
  "SELECT country, count(*) FROM orders WHERE status = 'refunded' GROUP BY country ORDER BY country",
  "SELECT order_id, country, amount_cents FROM orders WHERE order_id >= 431 AND order_id < 436 ORDER BY order_id",
  "SELECT count(*), sum(amount_cents) FROM orders WHERE country = 'SE'",
];

export async function mountTable(root, lab, files, initial, config) {
  const form = document.createElement("form");
  form.className = "controls engine-form";
  form.innerHTML = `<textarea name="sql" rows="2" spellcheck="false" aria-label="SQL"></textarea>
    <div class="row"><button type="submit">Run</button>
    ${EXAMPLES.map((_, i) => `<button type="button" data-example="${i}">Example ${i + 1}</button>`).join(" ")}</div>
    <div class="row"><fieldset class="mechanisms"><legend>Find the files by</legend>
      <label><input type="radio" name="discovery" value="list"> listing, and read them all</label>
      <label><input type="radio" name="discovery" value="prune"> listing, and ruling out by path</label>
      <label><input type="radio" name="discovery" value="log" checked> reading the log</label></fieldset>
      <label>Connections <select name="connections"><option>1</option><option>2</option><option selected>4</option><option>8</option></select></label></div>`;
  root.append(form);
  const grid = document.createElement("div");
  grid.className = "table-grid";
  grid.innerHTML = `
    <section class="panel p-files"><h4>The table's files</h4><div class="t-files"></div></section>
    <section class="panel p-t-reqs"><h4>Requests</h4><div class="t-reqs"></div></section>
    <section class="panel p-t-answer"><h4>The answer</h4><div class="t-answer"></div></section>`;
  root.append(grid);

  // Load every object into the reader's store, under its key. The listing says what exists;
  // the reader still has to LIST or read the log to find out for itself.
  const listing = JSON.parse(new TextDecoder().decode(await files.get(initial)));
  const ids = [];
  for (const o of listing.objects) ids.push(lab.load(o.key, await files.get(o.key)));
  form.elements.sql.value = config.sql || EXAMPLES[0];

  const run = () => {
    const f = form.elements;
    const r = lab.table(ids, f.sql.value, f.discovery.value, Number(f.connections.value));
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".t-files").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      for (const k of [".t-reqs", ".t-answer"]) grid.querySelector(k).innerHTML = "";
      return;
    }
    const t = r.totals;
    root.dataset.filesRead = String(t.files_read);
    root.dataset.requests = String(t.requests);
    root.dataset.answer = JSON.stringify(r.rows);
    grid.querySelector(".t-files").innerHTML = `<p class="note">Read ${t.files_read} of ${t.files} files.</p>` +
      `<div class="table-wrap"><table class="pages-list"><thead><tr><th>File</th><th class="num">Bytes</th><th class="num">Rows</th><th>Decision</th></tr></thead><tbody>` +
      r.files.map((x) => `<tr class="${x.read ? "" : "skipped"}"><td><code>${escapeHtml(x.key)}</code></td><td class="num">${fmt(x.size)}</td>` +
        `<td class="num">${x.rows === null ? "·" : fmt(x.rows)}</td><td>${escapeHtml(x.why)}</td></tr>`).join("") + "</tbody></table></div>";
    grid.querySelector(".t-reqs").innerHTML = `<p class="note">${fmt(t.requests)} requests, ${fmt(t.bytes_fetched)} bytes, ${ms(t.elapsed_us)} simulated.</p>` +
      `<div class="table-wrap"><table class="pages-list"><thead><tr><th>#</th><th>Request</th><th class="num">Bytes</th><th class="num">Start</th><th class="num">End</th></tr></thead><tbody>` +
      r.requests.map((q) => `<tr><td>${q.seq}</td><td><code>${escapeHtml(q.method)} ${escapeHtml(q.key)}</code></td><td class="num">${fmt(q.bytes)}</td>` +
        `<td class="num">${ms(q.start_us)}</td><td class="num">${ms(q.end_us)}</td></tr>`).join("") + "</tbody></table></div>";
    grid.querySelector(".t-answer").innerHTML = (r.rows.length
      ? `<div class="table-wrap"><table class="pages-list"><thead><tr>${r.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead><tbody>` +
        r.rows.map((row) => `<tr>${row.map((v) => `<td>${cell(v)}</td>`).join("")}</tr>`).join("") + "</tbody></table></div>"
      : '<p class="note">No rows.</p>') +
      `<ol class="pipeline">${r.stages.map((s) => `<li><strong>${escapeHtml(s.name)}</strong> <span class="flow">${fmt(s.rows_in)} in, ${fmt(s.rows_out)} out</span><p class="detail">${escapeHtml(s.detail)}</p></li>`).join("")}</ol>`;
  };
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    run();
  });
  form.addEventListener("change", run);
  form.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-example]");
    if (!b) return;
    form.elements.sql.value = EXAMPLES[Number(b.dataset.example)];
    run();
  });
  run();
}
