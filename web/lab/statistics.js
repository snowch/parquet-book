// The statistics laboratory (ch08): what the footer says about every column chunk, whether the
// reader may use it, and for one chunk every field, its values in the column's order, and what a
// mistaken order would have made of them.
//
// Every verdict, order and sorted list is `report::statistics`, computed by the Rust reader.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const span = (s) => escapeHtml(JSON.stringify(s));
const show = (v) => (v === null || v === undefined ? "·" : escapeHtml(String(v)));

export function mountStatistics(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const grid = document.createElement("div");
  grid.className = "stats-grid";
  grid.innerHTML = `
    <section class="panel p-stats-all"><h4>Every column chunk's minimum and maximum, as the reader may use them</h4><div class="stats-all"></div></section>
    <section class="panel p-stats-fields"><h4>The chunk's statistics, field by field</h4><div class="stats-fields"></div></section>
    <section class="panel p-stats-order"><h4>The values, in the column's order</h4><div class="stats-order"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });

  let rowGroup = Number(config.rowGroup || 0);
  let column = Number(config.column || 0);

  const run = () => {
    const r = lab.statistics(views.id, rowGroup, column);
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".stats-all").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      return;
    }
    const sel = r.selected;
    root.dataset.selected = `${sel.row_group}:${sel.column}`;
    root.dataset.usable = String(sel.verdict.usable);
    root.dataset.order = sel.order;
    drawAll(grid.querySelector(".stats-all"), r);
    drawFields(grid.querySelector(".stats-fields"), sel);
    drawOrder(grid.querySelector(".stats-order"), sel);
  };
  views.onChange = run;

  grid.addEventListener("click", (e) => {
    const cell = e.target.closest("button[data-cell]");
    if (cell) {
      [rowGroup, column] = cell.dataset.cell.split(":").map(Number);
      return run();
    }
    const t = e.target.closest("[data-span]");
    if (!t) return;
    const s = JSON.parse(t.dataset.span);
    views.hex.highlight(s);
    views.hex.select(s[0], s[1]);
  });

  const choose = fileChooser(head, files, initial, async (name) => {
    rowGroup = 0;
    column = Number(config.column || 0);
    await views.open(name, await files.get(name));
  });
  choose();
}

function drawAll(box, r) {
  const groups = r.row_groups;
  const sorted = groups.flatMap((g) => g.sorting_columns.map((s) => s.path)).filter(Boolean);
  box.innerHTML = `<div class="table-wrap"><table class="pages-list stats-table"><thead><tr><th>Column</th><th>Order</th>` +
    groups.map((g) => `<th>Row group ${g.index} <small>(${g.num_rows} rows)</small></th>`).join("") + "</tr></thead><tbody>" +
    r.columns.map((c) => `<tr><td><code>${escapeHtml(c.path)}</code><br><small>${escapeHtml(c.type)}${c.logical ? ` · ${escapeHtml(c.logical)}` : ""}</small></td>` +
      `<td>${escapeHtml(c.order)}</td>` +
      c.chunks.map((k) => {
        const chosen = k.row_group === r.selected.row_group && c.column === r.selected.column;
        const label = k.usable
          ? `${escapeHtml(k.min)} … ${escapeHtml(k.max)}`
          : `<span class="unusable">not usable</span>`;
        const nulls = k.null_count ? ` <small>${k.null_count} null</small>` : "";
        return `<td><button type="button" data-cell="${k.row_group}:${c.column}"${chosen ? ' aria-pressed="true"' : ""}` +
          `${k.usable ? "" : ` title="${escapeHtml(k.reason)}"`}>${label}</button>${nulls}</td>`;
      }).join("") + "</tr>").join("") +
    "</tbody></table></div>" +
    `<p class="note">Written by ${show(r.created_by)}. The footer ${r.column_orders ? "gives" : "does not give"} each column's sort order` +
    `${sorted.length ? `, and every row group says it is sorted by <code>${escapeHtml([...new Set(sorted)].join(", "))}</code>` : ""}. Pick a cell.</p>`;
}

function drawFields(box, sel) {
  const v = sel.verdict;
  box.innerHTML = `<p><code>${escapeHtml(sel.path)}</code>, row group ${sel.row_group}. Order: <strong>${escapeHtml(sel.order)}</strong>, ` +
    `comparing ${escapeHtml(sel.comparator)}.</p>` +
    (sel.fields.length
      ? `<table class="pages-list"><thead><tr><th>Field</th><th>Bytes</th><th>Value</th></tr></thead><tbody>` +
        sel.fields.map((f) => `<tr><td><button type="button" class="span" data-span="${span(f.span)}">${escapeHtml(f.name)}</button></td>` +
          `<td><code>${show(f.hex)}</code></td><td>${show(f.value)}</td></tr>`).join("") + "</tbody></table>"
      : '<p class="note">The footer has no statistics for this column chunk.</p>') +
    (v.usable
      ? `<p class="verdict ok">The reader uses <strong>${escapeHtml(v.source)}</strong>: every value lies between ${escapeHtml(v.min)} and ${escapeHtml(v.max)}` +
        `${v.min_exact && v.max_exact ? "" : ", and at least one bound is not exact"}.</p>`
      : `<p class="verdict no">The reader uses no bounds: ${escapeHtml(v.reason)}.</p>`);
}

function drawOrder(box, sel) {
  const vals = sel.values;
  if (!vals) {
    box.innerHTML = '<p class="note">The reader cannot decode this column chunk, so it cannot check the statistics against the values.</p>';
    return;
  }
  const obs = vals.observed;
  const m = vals.mistake;
  box.innerHTML = `<ol class="value-list sorted-values">${vals.sorted.map((x, i) =>
    `<li class="${i === 0 ? "lo" : ""}${i === vals.sorted.length - 1 ? " hi" : ""}">${escapeHtml(x)}</li>`).join("")}</ol>` +
    `<p class="note">${vals.sorted.length} values in order` +
    `${vals.unplaced ? `, ${vals.unplaced} NaN left out because it has no place in the order` : ""}` +
    `${vals.nulls ? `, ${vals.nulls} null` : ""}.</p>` +
    (obs ? `<p>Smallest and largest, found by the reader from the values: <strong>${escapeHtml(obs.min)}</strong> and <strong>${escapeHtml(obs.max)}</strong>.</p>` : "") +
    (m && m.result
      ? `<p class="mistake">A reader comparing ${escapeHtml(m.comparator)} ${escapeHtml(m.what)}. It would find ` +
        `<strong>${escapeHtml(m.result.min)}</strong> and <strong>${escapeHtml(m.result.max)}</strong>` +
        `${obs && (m.result.min !== obs.min || m.result.max !== obs.max) ? ", which is wrong here." : ", which happens to be right for these values."}</p>`
      : "");
}
