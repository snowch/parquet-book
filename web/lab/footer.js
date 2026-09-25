// The footer laboratory (ch02): open a Parquet file the way a reader must, from the end.
//
// Every number on this panel comes from one call into the Rust reader, `report::footer_lab`,
// which puts the file in a simulated object store and opens it through a tracing wrapper. The
// steps are the reader's own record of what it learned; the trace is the store's own record of
// what it was asked; the dim bytes are the bytes nobody asked for. Change a control and the
// reader runs again from nothing.

import { HexView, escapeHtml } from "./hexview.js";
import { StructureTree, regionsFrom, pathTo } from "./tree.js";
import { Inspector } from "./inspector.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const ms = (us) => `${(us / 1000).toLocaleString("en-GB", { maximumFractionDigits: 3 })} ms`;
const hex2 = (b) => b.toString(16).padStart(2, "0");
const PREFETCH = Array.from({ length: 14 }, (_, i) => 2 ** (i + 3)); // 8 bytes to 64 KiB
const BANDWIDTH = [
  ["1 MB/s", 1e6], ["10 MB/s", 1e7], ["100 MB/s", 1e8], ["1 GB/s", 1e9], ["unlimited", 0],
];
const SIZE_LABELS = {
  head: "a HEAD request",
  known: "a directory listing (no request)",
  suffix: "the response to a suffix range",
};

// A panel with a title, into which a component draws.
function panel(parent, title, cls) {
  const box = document.createElement("section");
  box.className = `panel ${cls}`;
  box.innerHTML = `<h4>${title}</h4>`;
  parent.append(box);
  return box;
}

// Shared by both experiments: a file loaded into the module, its bytes, its structure, and the
// three coordinated views over them.
export class FileViews {
  constructor(root, lab, { withTrace }) {
    this.lab = lab;
    this.grid = document.createElement("div");
    this.grid.className = withTrace ? "lab-grid with-trace" : "lab-grid";
    root.append(this.grid);
    const hexBox = panel(this.grid, "Bytes", "p-hex");
    this.legend = document.createElement("p");
    this.legend.className = "legend";
    hexBox.append(this.legend);
    this.hex = new HexView(hexBox, { onSelect: (sel) => this.#selected(sel) });
    const treeBox = panel(this.grid, "Structure, as the reader parsed it", "p-tree");
    this.tree = new StructureTree(treeBox, {
      onPick: (node) => { this.hex.highlight(node.span); this.#inspect(node.span, false); },
    });
    const inspBox = panel(this.grid, "Inspector", "p-inspect");
    this.inspector = new Inspector(inspBox, {
      onEdit: (offset, value) => this.edit(offset, value),
      onRestore: () => this.restore(),
    });
    this.onChange = () => {};
  }

  async open(name, bytes) {
    this.name = name;
    this.original = bytes.slice();
    this.id = this.lab.load(name, bytes);
    this.edited = false;
    this.refresh();
  }

  refresh() {
    this.bytes = this.lab.bytes(this.id);
    const s = this.lab.structure(this.id);
    if (s.ok) {
      this.structure = s.tree;
      this.tree.render(s.tree);
      this.hex.render(this.bytes, regionsFrom(s.tree));
    } else {
      this.structure = null;
      this.tree.showError(s.error);
      this.hex.render(this.bytes, []);
    }
    this.legend.innerHTML =
      '<span class="key r-magic">magic</span><span class="key r-pagehead col0">page header</span>' +
      '<span class="key r-body col0">values</span><span class="key r-footer">footer</span>' +
      '<span class="key r-length">footer length</span>' +
      (this.dimmed ? '<span class="key unfetched">never requested</span>' : "");
    this.onChange();
  }

  edit(offset, value) {
    this.lab.setByte(this.id, offset, value);
    this.edited = true;
    this.refresh();
    this.hex.select(offset);
  }

  restore() {
    for (let i = 0; i < this.original.length; i++) {
      if (this.bytes[i] !== this.original[i]) this.lab.setByte(this.id, i, this.original[i]);
    }
    this.edited = false;
    this.refresh();
  }

  #selected(sel) {
    this.#inspect(sel, true);
  }

  #inspect(span, fromBytes) {
    const [a, b] = span;
    const info = this.lab.interpret(this.id, a);
    const path = this.structure ? pathTo(this.structure, a) : [];
    if (fromBytes && this.structure) this.tree.reveal(a);
    this.inspector.show({ selection: [a, Math.max(b, a + 1)], info, path, bytes: this.bytes, edited: this.edited });
  }
}

export function mountAnatomy(root, lab, files, initial) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const views = new FileViews(root, lab, { withTrace: false });
  const choose = fileChooser(head, files, initial, async (name) => views.open(name, await files.get(name)));
  choose();
}

export function mountFooter(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);

  const controls = document.createElement("form");
  controls.className = "controls";
  controls.innerHTML = `
    <fieldset><legend>How the reader learns the file size</legend>
      <label><input type="radio" name="size" value="head" checked> <code>HEAD</code> request</label>
      <label><input type="radio" name="size" value="known"> already known from a listing</label>
      <label><input type="radio" name="size" value="suffix"> suffix range <code>bytes=-n</code></label>
    </fieldset>
    <fieldset><legend>First read from the end</legend>
      <input type="range" name="prefetch" min="0" max="${PREFETCH.length - 1}" value="0" aria-label="Bytes to read from the end">
      <output name="prefetchOut"></output>
    </fieldset>
    <fieldset><legend>Simulated network</legend>
      <label>latency <input type="number" name="latency" min="0" max="1000" step="1" value="20"> ms</label>
      <label>bandwidth <select name="bandwidth">${BANDWIDTH.map(([l, v]) =>
        `<option value="${v}"${v === 1e8 ? " selected" : ""}>${l}</option>`).join("")}</select></label>
    </fieldset>`;
  root.append(controls);
  if (config.prefetch) {
    const i = PREFETCH.indexOf(Number(config.prefetch));
    if (i >= 0) controls.prefetch.value = String(i);
  }
  if (config.size) controls.querySelector(`input[name=size][value=${config.size}]`).checked = true;

  const story = document.createElement("div");
  story.className = "lab-story";
  root.append(story);
  const stepsBox = panel(story, "What the reader did", "p-steps");
  const steps = document.createElement("ol");
  steps.className = "steps";
  stepsBox.append(steps);
  const traceBox = panel(story, "What the object store saw", "p-trace");
  const trace = document.createElement("div");
  traceBox.append(trace);

  const views = new FileViews(root, lab, { withTrace: true });
  views.dimmed = true;

  const options = () => ({
    size: controls.querySelector("input[name=size]:checked").value,
    prefetch: PREFETCH[Number(controls.prefetch.value)],
    latencyUs: Math.max(0, Number(controls.latency.value) || 0) * 1000,
    bandwidth: Number(controls.bandwidth.value),
  });

  const run = () => {
    const o = options();
    controls.prefetchOut.value = `${fmt(o.prefetch)} bytes`;
    const r = lab.footerLab(views.id, o);
    drawSteps(steps, r, o, views);
    drawTrace(trace, r);
    views.hex.dimOutside(r.fetched);
    root.dataset.state = r.ok ? "ok" : "error";
    root.dataset.footerLength = r.ok ? String(r.trailer.footer_length) : "";
    root.dataset.requests = String(r.requests.length);
  };
  views.onChange = run;
  controls.addEventListener("input", run);
  controls.addEventListener("submit", (e) => e.preventDefault());

  steps.addEventListener("click", (e) => {
    const b = e.target.closest("[data-span]");
    if (!b) return;
    const span = JSON.parse(b.dataset.span);
    views.hex.highlight(span);
    views.hex.select(span[0], span[1]);
  });

  const choose = fileChooser(head, files, initial, async (name) => views.open(name, await files.get(name)));
  choose();
}

export function fileChooser(head, files, initial, open) {
  const names = files.names();
  head.innerHTML = `<span class="lab-title">Parquet laboratory</span>` +
    (names.length > 1
      ? `<label>file <select>${names.map((n) => `<option${n === initial ? " selected" : ""}>${escapeHtml(n)}</option>`).join("")}</select></label>`
      : `<code>${escapeHtml(initial)}</code>`) +
    `<span class="lab-note">running the book's Rust reader, compiled to WebAssembly</span>`;
  const select = head.querySelector("select");
  if (select) select.addEventListener("change", () => open(select.value));
  return () => open(initial);
}

function spanButton(span, text) {
  return `<button type="button" class="span" data-span="${escapeHtml(JSON.stringify(span))}">${text}</button>`;
}

function drawSteps(ol, r, o, views) {
  const items = [];
  const reqs = r.requests;
  const req = (n) => (reqs[n - 1] ? `request ${n}` : "");
  const size = r.ok ? r.file_size : views.bytes.length;
  // 1. The size.
  const sizeFrom = o.size === "head" ? `${SIZE_LABELS.head} (${req(1)})`
    : o.size === "known" ? SIZE_LABELS.known
    : `${SIZE_LABELS.suffix} (${req(1)}'s <code>Content-Range</code>)`;
  items.push(`<li><b>File size</b> ${fmt(size)} bytes, from ${sizeFrom}.</li>`);
  if (!r.ok) {
    items.push(`<li class="failed"><b>Stopped</b> ${escapeHtml(r.error)}</li>`);
    ol.innerHTML = items.join("");
    return;
  }
  const t = r.trailer;
  const tailReq = o.size === "head" ? 2 : 1;
  const tailRange = reqs[tailReq - 1].range;
  items.push(`<li><b>Tail</b> <code>GET ${escapeHtml(tailRange)}</code> returned ` +
    `${spanButton(r.tail, `bytes [${r.tail[0]}, ${r.tail[1]})`)}: ${fmt(r.tail[1] - r.tail[0])} bytes, ` +
    `of which the last eight are the trailer.</li>`);
  items.push(`<li><b>Magic</b> ${spanButton(t.magic_span, t.bytes.slice(4).map(hex2).join(" "))} ` +
    `is “${escapeHtml(t.magic)}”, so the file claims to be Parquet.</li>`);
  const terms = t.terms.map((x) => `<code>${hex2(x.byte)}</code>×${fmt(x.weight)}`).join(" + ");
  items.push(`<li class="key-step"><b>Footer length</b> ${spanButton(t.length_span, t.bytes.slice(0, 4).map(hex2).join(" "))} ` +
    `read little-endian: ${terms} = <strong>${fmt(t.footer_length)}</strong> bytes.</li>`);
  items.push(`<li><b>Footer position</b> ${fmt(r.file_size)} − 8 − ${fmt(t.footer_length)} = ` +
    `<strong>${fmt(r.footer.span[0])}</strong>, so the footer is ` +
    `${spanButton(r.footer.span, `bytes [${r.footer.span[0]}, ${r.footer.span[1]})`)}.</li>`);
  if (r.footer.prefetched) {
    items.push(`<li><b>Footer fetch</b> none needed: the first read already covered it.</li>`);
  } else {
    const f = reqs[reqs.length - 1];
    items.push(`<li><b>Footer fetch</b> <code>GET ${escapeHtml(f.range)}</code> (${req(f.seq)}), ` +
      `${fmt(f.bytes)} bytes.</li>`);
  }
  const m = r.metadata;
  items.push(`<li><b>FileMetaData</b> decoded: ${fmt(m.num_rows)} rows in ${fmt(m.num_row_groups)} row ` +
    `group${m.num_row_groups === 1 ? "" : "s"}, columns ${m.columns.map((c) =>
      `<code>${escapeHtml(c.name)}</code>`).join(", ")}. Written by ${escapeHtml(m.created_by || "an unnamed writer")}.</li>`);
  ol.innerHTML = items.join("");
}

function drawTrace(box, r) {
  const total = Math.max(1, r.totals.elapsed_us);
  const rows = r.requests.map((q) => {
    const left = (q.start_us / total) * 100;
    const width = Math.max(0.8, ((q.end_us - q.start_us) / total) * 100);
    return `<tr class="${q.status >= 400 ? "err" : ""}"><td>${q.seq}</td><td><code>${q.method}</code></td>` +
      `<td><code>${escapeHtml(q.range || "·")}</code></td><td>${q.status}</td>` +
      `<td class="num">${fmt(q.bytes)}</td>` +
      `<td class="bar"><span style="left:${left}%;width:${width}%"></span></td>` +
      `<td class="why">${escapeHtml(q.why)}</td></tr>`;
  }).join("");
  const useful = r.ok
    ? ` The reader needed ${fmt(r.useful_bytes)} of them (trailer and footer); ${fmt(r.overfetch_bytes)} were read ahead and not used.`
    : "";
  box.innerHTML =
    `<table class="trace"><thead><tr><th>#</th><th>Method</th><th>Range</th><th>Status</th>` +
    `<th class="num">Bytes</th><th>Time</th><th>Why</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<p class="totals"><strong>${r.totals.requests}</strong> request${r.totals.requests === 1 ? "" : "s"}, ` +
    `<strong>${fmt(r.totals.bytes_returned)}</strong> bytes returned, ` +
    `<strong>${ms(r.totals.elapsed_us)}</strong> of simulated time before any data could be read.${useful}</p>`;
}
