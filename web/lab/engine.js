// The query-engine laboratory (ch12): SQL answered from the file's bytes, with every stage of
// the pipeline and a few of the rows each produced.
//
// The answer and the stages are `report::query`, from the Rust engine. The page only draws them.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const cell = (v) => escapeHtml(v === null ? "null" : typeof v === "number" && !Number.isInteger(v) ? v.toFixed(2) : String(v));

const EXAMPLES = {
  "writing-baseline.parquet": [
    "SELECT country, count(*) FROM orders GROUP BY country ORDER BY country",
    "SELECT status, sum(amount_cents), avg(amount_cents) FROM orders GROUP BY status ORDER BY status",
    "SELECT order_id, customer_id, amount_cents FROM orders WHERE order_id >= 431 AND order_id < 436",
    "SELECT order_id, amount_cents FROM orders WHERE amount_cents > 9800 ORDER BY amount_cents DESC LIMIT 5",
  ],
  "statistics.parquet": [
    "SELECT count(*), count(coupon) FROM orders",
    "SELECT city, customer_id FROM orders WHERE customer_id > 2147483647 ORDER BY customer_id",
    "SELECT city, temp_c FROM orders WHERE temp_c < 5 ORDER BY temp_c",
  ],
};

export function mountEngine(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const form = document.createElement("form");
  form.className = "controls engine-form";
  form.innerHTML = `<textarea name="sql" rows="3" spellcheck="false" aria-label="SQL"></textarea>
    <div class="row"><button type="submit">Run</button> <span class="examples"></span></div>`;
  root.append(form);
  const grid = document.createElement("div");
  grid.className = "engine-grid";
  grid.innerHTML = `
    <section class="panel p-pipeline"><h4>The pipeline, stage by stage</h4><ol class="pipeline"></ol></section>
    <section class="panel p-answer"><h4>The answer</h4><div class="answer"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });
  let file = initial;
  form.elements.sql.value = config.sql || EXAMPLES[initial]?.[0] || "SELECT count(*) FROM t";

  const drawExamples = () => {
    form.querySelector(".examples").innerHTML = (EXAMPLES[file] || []).map((q, i) =>
      `<button type="button" data-example="${i}">Example ${i + 1}</button>`).join(" ");
  };
  const run = () => {
    const r = lab.query(views.id, form.elements.sql.value);
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".pipeline").innerHTML = "";
      grid.querySelector(".answer").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      return;
    }
    root.dataset.rows = String(r.rows.length);
    root.dataset.answer = JSON.stringify(r.rows);
    grid.querySelector(".pipeline").innerHTML = r.stages.map((s) =>
      `<li><div class="stage-head"><strong>${escapeHtml(s.name)}</strong> <span class="flow">${fmt(s.rows_in)} rows in, ${fmt(s.rows_out)} out</span></div>` +
      `<p class="detail">${escapeHtml(s.detail)}</p>${table(s.columns, s.sample)}` +
      `${s.rows_out > s.sample.length ? `<p class="note">and ${fmt(s.rows_out - s.sample.length)} more</p>` : ""}</li>`).join("");
    grid.querySelector(".answer").innerHTML = table(r.columns, r.rows.slice(0, 50)) +
      `<p class="note">${fmt(r.rows.length)} rows. The scan read ${r.row_groups_read} of ${r.row_groups} row groups, ${fmt(r.bytes_read)} bytes of column chunks.</p>`;
  };
  views.onChange = run;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    run();
  });
  form.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-example]");
    if (!b) return;
    form.elements.sql.value = EXAMPLES[file][Number(b.dataset.example)];
    run();
  });
  const choose = fileChooser(head, files, initial, async (name) => {
    file = name;
    drawExamples();
    if (EXAMPLES[name] && !form.elements.sql.value.trim()) form.elements.sql.value = EXAMPLES[name][0];
    await views.open(name, await files.get(name));
  });
  drawExamples();
  choose();
}

function table(columns, rows) {
  if (!rows.length) return '<p class="note">No rows.</p>';
  return `<div class="table-wrap"><table class="pages-list"><thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.map((r) => `<tr>${r.map((v) => `<td>${cell(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
