// The encryption laboratory (ch13): what a reader without keys can see in an encrypted file, and
// what it cannot. Every item is `report::encryption`: the Rust reader tried to read it.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const span = (s) => escapeHtml(JSON.stringify(s));

export function mountEncryption(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const grid = document.createElement("div");
  grid.className = "crypt-grid";
  grid.innerHTML = `
    <section class="panel p-seen"><h4>What a reader without keys can see</h4><ul class="seen"></ul></section>
    <section class="panel p-unseen"><h4>What it cannot</h4><ul class="unseen"></ul></section>
    <section class="panel p-crypt-cols"><h4>Column by column</h4><div class="crypt-cols"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });

  const li = (x) => `<li>${x.span ? `<button type="button" class="span" data-span="${span(x.span)}">${escapeHtml(x.what)}</button>` : `<strong>${escapeHtml(x.what)}</strong>`}` +
    `${x.value ? `: <span class="detail">${escapeHtml(x.value)}</span>` : ""}</li>`;

  const run = () => {
    const r = lab.encryption(views.id);
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".seen").innerHTML = `<li class="lab-error">${escapeHtml(r.error)}</li>`;
      for (const k of [".unseen", ".crypt-cols"]) grid.querySelector(k).innerHTML = "";
      return;
    }
    root.dataset.mode = r.mode;
    root.dataset.hidden = String(r.hidden.length);
    grid.querySelector(".seen").innerHTML = `<li class="mode">This file: <strong>${escapeHtml(r.mode)}</strong></li>` + r.visible.map(li).join("");
    grid.querySelector(".unseen").innerHTML = r.hidden.length ? r.hidden.map(li).join("") : "<li>Nothing: the file is not encrypted.</li>";
    grid.querySelector(".crypt-cols").innerHTML = r.columns.length
      ? `<div class="table-wrap"><table class="pages-list"><thead><tr><th>Column</th><th>Protected by</th><th>Statistics</th><th>First values</th></tr></thead><tbody>` +
        r.columns.map((c) => `<tr><td><button type="button" class="span" data-span="${span(c.span)}"><code>${escapeHtml(c.path)}</code></button></td>` +
          `<td>${c.encrypted ? `key <code>${escapeHtml(c.key)}</code>, ${c.modules} encrypted modules` : "not encrypted"}</td>` +
          `<td>${c.statistics_visible ? "visible" : "withheld"}</td>` +
          `<td>${c.encrypted ? "unreadable" : escapeHtml(c.sample.map((v) => JSON.stringify(v)).join(", "))}</td></tr>`).join("") +
        "</tbody></table></div>"
      : '<p class="note">No column can be located: the footer that would say where they are is encrypted.</p>';
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
