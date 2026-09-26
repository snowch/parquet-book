// The layouts laboratory (ch01): one table, stored by rows and by columns, and what a query
// costs against each.
//
// `report::layouts` in Rust encodes the table both ways, works out the byte ranges the query
// needs in each layout, and reads them through the simulated object store twice: range by
// range, and as one whole-object GET. This draws the answer: which bytes the query needed,
// how many separate ranges that is, and what each way of fetching them cost.

import { escapeHtml } from "./hexview.js";
import { engineNote } from "./footer.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const ms = (us) => `${(us / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} ms`;

export function mountLayouts(root, lab) {
  const first = lab.layouts({ columns: [] });
  const cols = first.columns;
  const rows = first.rows;

  root.insertAdjacentHTML("beforeend", `
    <div class="lab-head"><span class="lab-title">Row layout or column layout</span>
      <span class="lab-note">${engineNote(root)}</span></div>
    <form class="controls">
      <fieldset><legend>Columns the query needs</legend>
        ${cols.map((c, i) => `<label><input type="checkbox" name="col" value="${i}"${i === 2 || i === 3 ? " checked" : ""}> <code>${escapeHtml(c)}</code></label>`).join("")}
      </fieldset>
      <fieldset><legend>Rows</legend>
        <label><input type="radio" name="rows" value="all" checked> every row (a scan)</label>
        <label><input type="radio" name="rows" value="one"> one order:
          <select name="row">${rows.map((r, i) => `<option value="${i}">order_id ${escapeHtml(r[0])}</option>`).join("")}</select></label>
      </fieldset>
      <fieldset><legend>Simulated network</legend>
        <label>latency <input type="number" name="latency" min="0" max="1000" value="20"> ms per request</label>
      </fieldset>
    </form>
    <p class="sql"></p>
    <div class="table-wrap"><table class="data"></table></div>
    <div class="strips"></div>
    <div class="table-wrap"><table class="costs"></table></div>`);

  const form = root.querySelector("form");
  const run = () => {
    const columns = Array.from(form.querySelectorAll("input[name=col]:checked"), (x) => Number(x.value));
    const one = form.querySelector("input[name=rows]:checked").value === "one";
    const row = one ? Number(form.row.value) : -1;
    const latencyUs = Math.max(0, Number(form.latency.value) || 0) * 1000;
    const r = lab.layouts({ columns, row, latencyUs, bandwidth: 100e6 });
    draw(root, r, one);
    root.dataset.rowsRanges = String(r.rows_layout.needed.length);
    root.dataset.columnsRanges = String(r.columns_layout.needed.length);
  };
  form.addEventListener("input", run);
  form.addEventListener("submit", (e) => e.preventDefault());
  run();
}

function draw(root, r, one) {
  const cols = r.query.columns;
  const colNames = cols.map((c) => r.columns[c]);
  const where = one ? ` WHERE order_id = ${escapeHtml(r.rows[r.query.rows[0]][0])}` : "";
  root.querySelector(".sql").innerHTML = cols.length
    ? `<code>SELECT ${colNames.map(escapeHtml).join(", ")} FROM sales${where}</code>`
    : "Pick at least one column.";

  const wanted = new Set(r.query.rows);
  root.querySelector("table.data").innerHTML =
    `<thead><tr>${r.columns.map((c, i) => `<th class="c${i}${cols.includes(i) ? " on" : ""}">${escapeHtml(c).replace(/_/g, "_<wbr>")}</th>`).join("")}</tr></thead>` +
    `<tbody>${r.rows.map((row, ri) => `<tr>${row.map((v, ci) =>
      `<td class="c${ci}${cols.includes(ci) && wanted.has(ri) ? " on" : ""}">${escapeHtml(v)}</td>`).join("")}</tr>`).join("")}</tbody>`;

  const strips = root.querySelector(".strips");
  strips.innerHTML = [r.rows_layout, r.columns_layout].map((L) => strip(L, r)).join("");

  // One column per layout, so the table fits a phone: what the query needs, and what each way
  // of fetching it costs.
  const [R, C] = [r.rows_layout, r.columns_layout];
  const requests = (L) => `${fmt(L.by_range.requests.length)} request${L.by_range.requests.length === 1 ? "" : "s"}`;
  const row = (name, f) => `<tr><th scope="row">${name}</th><td class="num">${f(R)}</td><td class="num">${f(C)}</td></tr>`;
  root.querySelector("table.costs").innerHTML =
    `<thead><tr><th></th><th class="num">By rows</th><th class="num">By columns</th></tr></thead><tbody>` +
    row("Bytes the query needs", (L) => `${fmt(L.needed_bytes)} of ${fmt(L.total_bytes)}`) +
    row("Separate ranges", (L) => fmt(L.needed.length)) +
    row("Fetch range by range", (L) => `${ms(L.by_range.elapsed_us)}<small>${requests(L)}</small>`) +
    row("Fetch the whole object", (L) => `${ms(L.whole.elapsed_us)}<small>${fmt(L.whole.bytes)} bytes</small>`) +
    "</tbody>";
}

// One layout's bytes, a cell per byte, coloured by column and lit where the query needs them.
// Each line is one unit of the layout: an order in the row layout, a column in the column
// layout. The cells share the width between them, so a line always fits, on a phone too.
function strip(L, r) {
  const owner = new Array(L.total_bytes);
  L.cells.forEach((row, ri) => row.forEach(([a, b], ci) => {
    for (let i = a; i < b; i++) owner[i] = [ri, ci];
  }));
  const need = new Array(L.total_bytes).fill(false);
  for (const [a, b] of L.needed) for (let i = a; i < b; i++) need[i] = true;
  const byRows = L.layout === "rows";
  const units = byRows
    ? L.cells.map((row, ri) => [`order ${r.rows[ri][0]}`, row])
    : r.columns.map((name, ci) => [name, L.cells.map((row) => row[ci])]);
  const lines = units.map(([label, spans]) => [label, Math.min(...spans.map((s) => s[0])), Math.max(...spans.map((s) => s[1]))]);
  const widest = Math.max(...lines.map(([, a, b]) => b - a));
  const cell = (i) => {
    const [ri, ci] = owner[i];
    const starts = L.cells[ri][ci][0] === i ? " start" : "";
    return `<span class="cell c${ci}${need[i] ? " on" : ""}${starts}" title="${escapeHtml(r.columns[ci])}, row ${ri + 1}, byte ${i}"></span>`;
  };
  const html = lines.map(([label, a, b]) => `<div class="line"><span class="line-name">${escapeHtml(label)}</span>` +
    `<span class="line-cells">${Array.from({ length: b - a }, (_, k) => cell(a + k)).join("")}</span></div>`).join("");
  const title = byRows ? "Stored by rows" : "Stored by columns";
  return `<figure class="strip"><figcaption><strong>${title}</strong>: ${fmt(L.total_bytes)} bytes, ` +
    `one square per byte, one line per ${byRows ? "order" : "column"}. Lit squares are the bytes the query needs, in ${fmt(L.needed.length)} ` +
    `separate range${L.needed.length === 1 ? "" : "s"}.</figcaption><div class="cells" style="--widest:${widest}">${html}</div></figure>`;
}
