// The pages laboratory (ch06): walk one column chunk page by page.
//
// Each row is a page as `report::pages` found it: the header's own fields, where the header, the
// levels and the values sit, which rows the page holds (counted from its decoded repetition
// levels), and whether its body still matches the checksum in its header. Damage a byte in the
// byte view and the walk runs again on the damaged file.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const span = (s) => escapeHtml(JSON.stringify(s));
const show = (v) => (v === null || v === undefined ? "·" : escapeHtml(String(v)));
const part = (label, s) => (s ? `<button type="button" class="span" data-span="${span(s)}">${label}</button>` : "");

export function mountPages(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const picker = document.createElement("div");
  picker.className = "controls column-picker";
  root.append(picker);
  const box = document.createElement("section");
  box.className = "panel p-pages";
  box.innerHTML = "<h4>The column chunk, page by page</h4><div class=\"pages-table\"></div>";
  root.append(box);
  const views = new FileViews(root, lab, { withTrace: false });

  let column = Number(config.column || 0);
  const run = () => {
    const r = lab.pages(views.id, column);
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      box.querySelector(".pages-table").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      return;
    }
    root.dataset.pages = String(r.pages.length);
    root.dataset.crc = r.pages.map((p) => (p.crc_ok === null ? "-" : p.crc_ok ? "ok" : "bad")).join(",");
    picker.innerHTML = `<fieldset><legend>Column</legend>${r.columns.map((c) =>
      `<button type="button" data-column="${c.column}"${c.column === column ? ' aria-pressed="true"' : ""}><code>${escapeHtml(c.path)}</code></button>`).join("")}</fieldset>`;
    const v2 = r.pages.some((p) => p.v2);
    box.querySelector(".pages-table").innerHTML = `<div class="table-wrap"><table class="pages-list"><thead><tr>` +
      `<th>#</th><th>Type</th><th>Parts</th><th class="num">Body bytes</th><th class="num">Values</th>` +
      `<th class="num">First row</th><th class="num">Rows</th>${v2 ? '<th class="num">Nulls</th>' : ""}` +
      `<th>Encoding</th><th>Min</th><th>Max</th><th>Checksum</th></tr></thead><tbody>` +
      r.pages.map((p) => `<tr class="${p.crc_ok === false ? "err" : ""}">` +
        `<td>${p.index}</td><td>${escapeHtml(p.type)}</td>` +
        `<td class="parts">${part("page", p.span)} ${part("header", p.header)} ${part("rep", p.repetition_levels)} ` +
        `${part("def", p.definition_levels)} ${part("values", p.values)}${p.type === "DICTIONARY_PAGE" ? part("entries", p.body) : ""}</td>` +
        `<td class="num">${show(p.compressed_page_size)}</td><td class="num">${show(p.num_values)}</td>` +
        `<td class="num">${show(p.first_row)}</td><td class="num">${show(p.v2 ? p.v2.num_rows : p.rows_started)}</td>` +
        (v2 ? `<td class="num">${show(p.v2 ? p.v2.num_nulls : null)}</td>` : "") +
        `<td>${show(p.encoding)}</td><td>${show(p.statistics && p.statistics.min)}</td><td>${show(p.statistics && p.statistics.max)}</td>` +
        `<td>${p.crc_ok === null ? "none stored" : p.crc_ok ? "matches" : "<strong>does not match</strong>"}</td></tr>`).join("") +
      "</tbody></table></div>";
  };
  views.onChange = run;
  picker.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-column]");
    if (!b) return;
    column = Number(b.dataset.column);
    run();
  });
  box.addEventListener("click", (e) => {
    const t = e.target.closest("[data-span]");
    if (!t) return;
    const s = JSON.parse(t.dataset.span);
    views.hex.highlight(s);
    views.hex.select(s[0], s[1]);
  });
  const choose = fileChooser(head, files, initial, async (name) => views.open(name, await files.get(name)));
  choose();
}
