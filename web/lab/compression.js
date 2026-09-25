// The compression laboratory (ch07): what a codec did to every column chunk, and one page
// decompressed token by token.
//
// The sizes are the footer's, so every codec has them. The tokens are the Rust decompressor's own
// record of what it read and wrote (`compress::Token`): stepping through them highlights the
// compressed bytes in the byte view and the bytes they became in the decompressed page, and for a
// copy, the earlier bytes it copied.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const span = (s) => escapeHtml(JSON.stringify(s));
const printable = (b) => (b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : "·");

export function mountCompression(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const grid = document.createElement("div");
  grid.className = "comp-grid";
  grid.innerHTML = `
    <section class="panel p-chunks"><h4>Every column chunk, before and after the codec</h4><div class="chunks"></div></section>
    <section class="panel p-comp-pages"><h4>Pages of this column chunk</h4><div class="comp-pages"></div></section>
    <section class="panel p-tokens"><h4>How the decompressor rebuilt the page</h4>
      <div class="stepper"><button type="button" data-step="-1">Previous token</button>
      <button type="button" data-step="1">Next token</button><span class="where"></span></div>
      <ol class="enc-steps comp-tokens"></ol></section>
    <section class="panel p-output"><h4>The decompressed page</h4><div class="out-bytes"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });

  let column = Number(config.column || 0);
  let page = null;
  let tokens = [];
  let current = -1;

  const goto = (i) => {
    if (!tokens.length) return;
    current = Math.max(0, Math.min(tokens.length - 1, i));
    const t = tokens[current];
    for (const li of grid.querySelectorAll(".comp-tokens li")) li.classList.toggle("current", Number(li.dataset.i) === current);
    grid.querySelector(".where").textContent = `token ${current + 1} of ${tokens.length}`;
    views.hex.highlight(t.input);
    views.hex.select(t.input[0], t.input[1]);
    const from = t.kind === "copy" ? [t.output[0] - t.distance, t.output[1] - t.distance] : null;
    for (const b of grid.querySelectorAll(".out-bytes [data-o]")) {
      const o = Number(b.dataset.o);
      b.classList.toggle("out", o >= t.output[0] && o < t.output[1]);
      b.classList.toggle("src", !!from && o >= from[0] && o < from[1]);
    }
    const first = grid.querySelector(".out-bytes .out");
    if (first) first.scrollIntoView({ block: "nearest" });
    root.dataset.token = String(current);
  };

  const run = () => {
    const r = lab.compression(views.id, column, page);
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".chunks").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      return;
    }
    page = r.page;
    root.dataset.codec = r.codec;
    drawChunks(grid.querySelector(".chunks"), r, column);
    drawPages(grid.querySelector(".comp-pages"), r);
    const d = r.decompressed;
    tokens = d.ok ? d.tokens : [];
    current = -1;
    root.dataset.tokens = String(tokens.length);
    root.dataset.decompressed = d.ok ? String(d.bytes ? d.bytes.split(" ").length : 0) : "none";
    if (!d.ok) {
      grid.querySelector(".comp-tokens").innerHTML = "";
      grid.querySelector(".where").textContent = "";
      grid.querySelector(".out-bytes").innerHTML =
        `<p class="note">${escapeHtml(d.error)}. The sizes above come from the footer, which every reader can read.</p>`;
      return;
    }
    grid.querySelector(".comp-tokens").innerHTML = tokens.map((t, i) =>
      `<li data-i="${i}" class="k-${t.kind}"><button type="button" class="span" data-span="${span(t.input)}">${escapeHtml(t.label)}</button> ` +
      `<span class="detail">${escapeHtml(t.detail)}</span></li>`).join("");
    grid.querySelector(".where").textContent = `${tokens.length} tokens`;
    const bytes = d.bytes ? d.bytes.split(" ").map((h) => parseInt(h, 16)) : [];
    grid.querySelector(".out-bytes").innerHTML = bytes.length
      ? `<p class="note">${fmt(bytes.length)} bytes, as the encoding left them. Shaded: what the current token wrote; outlined: what a copy copied.</p>` +
        `<div class="out-rows">${rows(bytes)}</div>`
      : '<p class="note">The page is empty.</p>';
  };
  views.onChange = run;

  grid.addEventListener("click", (e) => {
    const step = e.target.closest("button[data-step]");
    if (step) return goto(current + Number(step.dataset.step));
    const col = e.target.closest("button[data-column]");
    if (col) {
      column = Number(col.dataset.column);
      page = null;
      return run();
    }
    const p = e.target.closest("button[data-page]");
    if (p) {
      page = Number(p.dataset.page);
      return run();
    }
    const li = e.target.closest(".comp-tokens li");
    if (li) return goto(Number(li.dataset.i));
  });

  const choose = fileChooser(head, files, initial, async (name) => {
    page = null;
    await views.open(name, await files.get(name));
  });
  choose();
}

function rows(bytes) {
  let out = "";
  for (let at = 0; at < bytes.length; at += 16) {
    const row = bytes.slice(at, at + 16);
    out += `<div class="out-row"><span class="off">${at.toString(16).padStart(4, "0")}</span>` +
      `<span class="hx">${row.map((b, i) => `<i data-o="${at + i}">${b.toString(16).padStart(2, "0")}</i>`).join("")}</span>` +
      `<span class="tx">${row.map((b, i) => `<i data-o="${at + i}">${escapeHtml(printable(b))}</i>`).join("")}</span></div>`;
  }
  return out;
}

function drawChunks(box, r, column) {
  const total = r.chunks.reduce((a, c) => [a[0] + c.uncompressed, a[1] + c.compressed], [0, 0]);
  box.innerHTML = `<div class="table-wrap"><table class="pages-list"><thead><tr><th>Column</th><th>Codec</th>` +
    `<th class="num">Before</th><th class="num">After</th><th>After, as a share of before</th></tr></thead><tbody>` +
    r.chunks.map((c) => {
      const pct = c.uncompressed ? Math.round((c.compressed / c.uncompressed) * 100) : 0;
      return `<tr${c.column === column ? ' class="chosen"' : ""}><td><button type="button" data-column="${c.column}"` +
        `${c.column === column ? ' aria-pressed="true"' : ""}><code>${escapeHtml(c.path)}</code></button></td>` +
        `<td>${escapeHtml(c.codec || "")}</td><td class="num">${fmt(c.uncompressed)}</td><td class="num">${fmt(c.compressed)}</td>` +
        `<td><span class="bar"><i style="width:${Math.min(100, pct)}%"></i></span> ${pct}%</td></tr>`;
    }).join("") +
    `</tbody></table></div><p class="note">Column chunks: ${fmt(total[0])} bytes before, ${fmt(total[1])} after, in a ` +
    `${fmt(r.file_size)}-byte file. Both sizes include page headers, which are never compressed.</p>`;
}

function drawPages(box, r) {
  box.innerHTML = `<p class="note">Pick a page to decompress.</p><div class="page-picks">` +
    r.pages.map((p) =>
      `<button type="button" data-page="${p.index}"${p.index === r.page ? ' aria-pressed="true"' : ""}>` +
      `${p.index}: ${escapeHtml(p.type)} <small>${fmt(p.compressed_page_size)} of ${fmt(p.uncompressed_page_size)} bytes</small></button>`).join("") +
    "</div>" + (r.pages.some((p) => p.compressed_section[0] !== p.header[1])
    ? '<p class="note">Version 2 pages: the levels before each values section are not compressed, so the codec saw only the values.</p>'
    : "");
}
