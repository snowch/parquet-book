// The writer-settings laboratory (ch11): one query run against every file the chapter wrote, each
// written from the same rows with one setting changed.
//
// Each row of the table is `report::scan` for that file: the Rust reader ran the query through the
// simulated object store with the same strategy each time. Pick a file to see its bytes.

import { FileViews } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];

// The same reader for every file: the footer found exactly, every skipping mechanism, only ranges
// that touch merged, one connection. What differs is only what each file's layout allows.
const STRATEGY = {
  footer: "head", prefetch: 8, connections: 1, gap: 0, statistics: true, bloom: true,
  pageIndex: true, wholeChunks: false, latencyUs: 20000, bandwidth: 100000000,
};

export async function mountWriting(root, lab, files, initial, config) {
  const form = document.createElement("form");
  form.className = "controls skip-form";
  form.innerHTML = `
    <strong>SELECT *</strong>
    <label>where <select name="column"><option value="-1">no condition</option></select></label>
    <select name="op" aria-label="comparison">${OPS.map((o) => `<option>${escapeHtml(o)}</option>`).join("")}</select>
    <input name="value" size="10" aria-label="value"> <button type="submit">Run on every file</button>`;
  root.append(form);
  const box = document.createElement("section");
  box.className = "panel p-writing";
  box.innerHTML = '<h4>The same query against every file</h4><div class="writing-table"></div>';
  root.append(box);
  const views = new FileViews(root, lab, { withTrace: false });

  // Every file, loaded once into the reader.
  const names = files.names();
  const ids = new Map();
  for (const name of names) ids.set(name, lab.load(name, await files.get(name)));

  let whereColumn = Number(config.column ?? -1);
  let shown = initial;
  form.elements.op.value = config.op || "=";
  form.elements.value.value = config.value || "";

  const run = () => {
    const f = form.elements;
    const op = f.op.value;
    f.value.disabled = op.startsWith("is ");
    const where = whereColumn >= 0 ? { column: whereColumn, op, value: f.value.value } : null;
    const results = names.map((name) => [name, lab.scan(ids.get(name), [], where, STRATEGY)]);
    const first = results.find(([, r]) => r.columns);
    if (first) {
      f.column.innerHTML = '<option value="-1">no condition</option>' + first[1].columns.map((c) =>
        `<option value="${c.column}"${c.column === whereColumn ? " selected" : ""}>${escapeHtml(c.path)}</option>`).join("");
    }
    const ok = results.filter(([, r]) => r.ok);
    root.dataset.state = ok.length === results.length ? "ok" : "error";
    const least = Math.min(...ok.map(([, r]) => r.totals.bytes_after_footer));
    root.dataset.bytes = ok.map(([, r]) => r.totals.bytes_after_footer).join(",");
    box.querySelector(".writing-table").innerHTML = `<div class="table-wrap"><table class="pages-list"><thead><tr>` +
      `<th>File</th><th class="num">Bytes</th><th class="num">Footer</th><th class="num">Row groups</th>` +
      `<th class="num">Read after the footer</th><th class="num">Requests</th><th class="num">Matches</th></tr></thead><tbody>` +
      results.map(([name, r]) => r.ok
        ? `<tr class="${name === shown ? "chosen" : ""}"><td><button type="button" data-file="${escapeHtml(name)}"><code>${escapeHtml(name)}</code></button></td>` +
          `<td class="num">${fmt(r.file_size)}</td><td class="num">${fmt(r.totals.footer_bytes)}</td><td class="num">${r.totals.row_groups}</td>` +
          `<td class="num">${r.totals.bytes_after_footer === least ? "<strong>" : ""}${fmt(r.totals.bytes_after_footer)}${r.totals.bytes_after_footer === least ? "</strong>" : ""}</td>` +
          `<td class="num">${fmt(r.totals.requests_after_footer)}</td><td class="num">${fmt(r.totals.rows_matching)}</td></tr>`
        : `<tr><td><code>${escapeHtml(name)}</code></td><td colspan="6" class="lab-error">${escapeHtml(r.error)}</td></tr>`).join("") +
      `</tbody></table></div><p class="note">Sizes are in bytes. Every file holds the same rows, so every query matches the same number of them. ` +
      `The least read is in bold. Pick a file to see its bytes and structure below.</p>`;
  };

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    whereColumn = Number(form.elements.column.value);
    run();
  });
  form.addEventListener("change", (e) => {
    if (e.target.name === "value") return;
    whereColumn = Number(form.elements.column.value);
    run();
  });
  box.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-file]");
    if (!b) return;
    shown = b.dataset.file;
    await views.open(shown, await files.get(shown));
    run();
  });
  await views.open(shown, await files.get(shown));
  run();
}
