// The encryption laboratory (ch13): an encrypted file's structure and bytes, and its columns as a
// reader without keys finds them. The table is `report::encryption`: the Rust reader tried to
// read each column.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const span = (s) => escapeHtml(JSON.stringify(s));

export function mountEncryption(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const grid = document.createElement("div");
  grid.className = "crypt-grid";
  grid.innerHTML = `<section class="panel p-crypt-cols"><h4>Column by column</h4><div class="crypt-cols"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });
  const cols = grid.querySelector(".crypt-cols");

  const run = () => {
    const r = lab.encryption(views.id);
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      cols.innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      return;
    }
    root.dataset.mode = r.mode;
    root.dataset.encrypted = String(r.columns.filter((c) => c.encrypted).length);
    cols.innerHTML = r.columns.length
      ? `<div class="table-wrap"><table class="pages-list"><thead><tr><th>Column</th><th>Protected by</th><th>Statistics</th><th>First values</th></tr></thead><tbody>` +
        r.columns.map((c) => `<tr><td><button type="button" class="span" data-span="${span(c.span)}"><code>${escapeHtml(c.path)}</code></button></td>` +
          `<td>${c.encrypted ? `key <code>${escapeHtml(c.key)}</code>, ${c.modules} encrypted modules` : "not encrypted"}</td>` +
          `<td>${c.statistics_visible ? "visible" : "withheld"}</td>` +
          `<td>${c.encrypted ? "unreadable" : escapeHtml(c.sample.map((v) => JSON.stringify(v)).join(", "))}</td></tr>`).join("") +
        "</tbody></table></div>"
      : `<p class="note">No column can be located: the footer that would say where they are is encrypted (${escapeHtml(r.mode)}).</p>`;
  };
  views.onChange = run;
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
