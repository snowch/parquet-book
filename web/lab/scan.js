// The read-path laboratory (ch10): a query run through the simulated object store under a
// strategy the reader chooses, with every request on a timeline by connection.
//
// Everything shown is `report::scan`: the Rust reader issued these requests, the simulated store
// timed them, and the rows are what the reader decoded from the bytes it fetched.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const ms = (us) => `${(us / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} ms`;
const span = (s) => escapeHtml(JSON.stringify(s));
const OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];

const CHOICES = {
  footer: [["head", "HEAD, then the tail"], ["suffix", "a suffix range"]],
  prefetch: [[8, "8 bytes"], [1024, "1 KiB"], [8192, "8 KiB"], [65536, "64 KiB"]],
  connections: [[1, "1"], [2, "2"], [4, "4"], [8, "8"]],
  gap: [["never", "never"], [0, "that touch"], [256, "within 256 bytes"], [1024, "within 1 KiB"], [4096, "within 4 KiB"], [65536, "within 64 KiB"]],
  latencyUs: [[1000, "1 ms"], [20000, "20 ms"], [100000, "100 ms"]],
  bandwidth: [[10000000, "10 MB/s"], [100000000, "100 MB/s"], [1000000000, "1 GB/s"]],
};

const select = (name, label, current) =>
  `<label>${label} <select name="${name}">${CHOICES[name].map(([v, t]) =>
    `<option value="${v}"${String(v) === String(current) ? " selected" : ""}>${escapeHtml(t)}</option>`).join("")}</select></label>`;

export function mountScan(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const form = document.createElement("form");
  form.className = "controls scan-form";
  form.innerHTML = `
    <div class="row"><strong>SELECT *</strong>
      <label>where <select name="column"><option value="-1">no condition</option></select></label>
      <select name="op" aria-label="comparison">${OPS.map((o) => `<option>${escapeHtml(o)}</option>`).join("")}</select>
      <input name="value" size="10" aria-label="value"> <button type="submit">Run</button></div>
    <div class="row">${select("footer", "Find the footer with", "head")} ${select("prefetch", "reading", 8)}
      ${select("connections", "Connections", 1)} ${select("gap", "Merge ranges", "never")}</div>
    <div class="row"><label><input type="checkbox" name="statistics" checked> statistics</label>
      <label><input type="checkbox" name="bloom" checked> Bloom filters</label>
      <label><input type="checkbox" name="pageIndex" checked> page index</label>
      <label><input type="checkbox" name="wholeChunks"> whole column chunks</label>
      ${select("latencyUs", "Latency", 20000)} ${select("bandwidth", "Bandwidth", 100000000)}</div>`;
  root.append(form);
  const grid = document.createElement("div");
  grid.className = "scan-grid";
  grid.innerHTML = `
    <section class="panel p-scan-sum"><h4>The cost</h4><div class="scan-sum"></div></section>
    <section class="panel p-scan-time"><h4>Requests over time, by connection</h4><div class="timeline"></div></section>
    <section class="panel p-scan-reqs"><h4>Every request</h4><div class="scan-reqs"></div></section>
    <section class="panel p-scan-rows"><h4>The result</h4><div class="scan-rows"></div></section>`;
  root.append(grid);
  const views = new FileViews(root, lab, { withTrace: false });

  let whereColumn = Number(config.column ?? -1);
  form.elements.op.value = config.op || "=";
  form.elements.value.value = config.value || "";

  const run = () => {
    const f = form.elements;
    const op = f.op.value;
    f.value.disabled = op.startsWith("is ");
    const where = whereColumn >= 0 ? { column: whereColumn, op, value: f.value.value } : null;
    const s = {
      footer: f.footer.value, prefetch: Number(f.prefetch.value), connections: Number(f.connections.value),
      gap: f.gap.value === "never" ? null : Number(f.gap.value), statistics: f.statistics.checked, bloom: f.bloom.checked,
      pageIndex: f.pageIndex.checked, wholeChunks: f.wholeChunks.checked,
      latencyUs: Number(f.latencyUs.value), bandwidth: Number(f.bandwidth.value),
    };
    const r = lab.scan(views.id, [], where, s);
    if (r.columns) {
      f.column.innerHTML = '<option value="-1">no condition</option>' + r.columns.map((c) =>
        `<option value="${c.column}"${c.column === whereColumn ? " selected" : ""}>${escapeHtml(c.path)}</option>`).join("");
    }
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".scan-sum").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      for (const k of [".timeline", ".scan-reqs", ".scan-rows"]) grid.querySelector(k).innerHTML = "";
      return;
    }
    root.dataset.requests = String(r.totals.requests);
    root.dataset.elapsed = String(r.totals.elapsed_us);
    root.dataset.matching = String(r.totals.rows_matching);
    drawSummary(grid.querySelector(".scan-sum"), r);
    drawTimeline(grid.querySelector(".timeline"), r);
    drawRequests(grid.querySelector(".scan-reqs"), r);
    drawRows(grid.querySelector(".scan-rows"), r);
  };
  views.onChange = run;
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

function drawSummary(box, r) {
  const t = r.totals;
  const waste = Math.max(0, t.bytes_fetched - t.bytes_planned);
  box.innerHTML = `<dl class="scan-costs">` +
    `<div><dt>Requests</dt><dd>${fmt(t.requests)}</dd></div>` +
    `<div><dt>Time</dt><dd>${ms(t.elapsed_us)}</dd></div>` +
    `<div><dt>Bytes fetched</dt><dd>${fmt(t.bytes_fetched)} <small>of ${fmt(r.file_size)}</small></dd></div>` +
    `<div><dt>Rows decoded</dt><dd>${fmt(t.rows_decoded)} <small>${fmt(t.rows_matching)} matching</small></dd></div></dl>` +
    `<p class="note">The plan asked for ${fmt(t.bytes_planned)} bytes of indexes and pages. The other ${fmt(waste)} bytes fetched are ` +
    `the footer, whatever the tail read brought with it, and the gaps between merged ranges. ` +
    `Time is simulated: each request costs the latency, then its bytes over the bandwidth.</p>`;
}

function drawTimeline(box, r) {
  const end = Math.max(1, r.totals.elapsed_us);
  const lanes = Math.max(1, ...r.requests.map((q) => q.connection + 1));
  let html = "";
  for (let lane = 0; lane < lanes; lane++) {
    html += `<div class="lane"><span class="lane-name">${lane + 1}</span><div class="lane-track">` +
      r.requests.filter((q) => q.connection === lane).map((q) => {
        const left = (q.start_us / end) * 100;
        const width = Math.max(0.6, ((q.end_us - q.start_us) / end) * 100);
        const kind = q.why.includes("index") ? "idx" : q.why.includes("pages") ? "data" : "foot";
        return `<button type="button" class="req ${kind}" style="left:${left}%;width:${width}%"` +
          `${q.returned ? ` data-span="${span(q.returned)}"` : ""} title="${escapeHtml(`#${q.seq} ${q.method} ${q.range || ""}: ${q.why}`)}">${q.seq}</button>`;
      }).join("") + "</div></div>";
  }
  box.innerHTML = html + `<p class="note">0 to ${ms(end)}. Grey finds the footer, orange fetches indexes, blue fetches data. Each request that depends on an earlier one waits for it.</p>`;
}

function drawRequests(box, r) {
  box.innerHTML = `<div class="table-wrap"><table class="pages-list"><thead><tr><th>#</th><th>Phase</th><th>Conn.</th><th>Request</th>` +
    `<th class="num">Bytes</th><th class="num">Start</th><th class="num">End</th><th>Why</th></tr></thead><tbody>` +
    r.requests.map((q) => `<tr><td>${q.seq}</td><td>${q.phase}</td><td>${q.connection + 1}</td>` +
      `<td>${q.returned ? `<button type="button" class="span" data-span="${span(q.returned)}">` : ""}<code>${escapeHtml(q.method)} ${escapeHtml(q.range || "")}</code>${q.returned ? "</button>" : ""}</td>` +
      `<td class="num">${fmt(q.bytes)}</td><td class="num">${ms(q.start_us)}</td><td class="num">${ms(q.end_us)}</td>` +
      `<td>${escapeHtml(q.why)}</td></tr>`).join("") + "</tbody></table></div>";
}

function drawRows(box, r) {
  const rows = r.result.rows;
  box.innerHTML = rows.length
    ? `<div class="table-wrap"><table class="pages-list"><thead><tr>${r.result.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead><tbody>` +
      rows.map((row) => `<tr>${row.map((v) => `<td>${escapeHtml(v === null ? "null" : String(v))}</td>`).join("")}</tr>`).join("") +
      `</tbody></table></div>${r.totals.rows_matching > rows.length ? `<p class="note">The first ${rows.length} of ${fmt(r.totals.rows_matching)} rows.</p>` : ""}`
    : '<p class="note">No rows match.</p>';
}
