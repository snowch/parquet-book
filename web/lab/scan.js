// The read-path laboratory (ch10): one query run through the simulated object store under a
// strategy picked from a list, with every request on a timeline by connection.
//
// Everything shown is `report::scan`: the Rust reader issued these requests, the simulated store
// timed them, and the totals are what it counted. The strategies are the rows of the chapter's
// table of strategies, in its order and with its labels, so the picture and the table agree; the
// browser test holds each one to its row. The chapter's first step prints every request, so the
// panel draws only what a printout cannot: which requests wait for which.

import { fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const ms = (us) => `${(us / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} ms`;

// The row groups' statistics and the page index; the Bloom filters play no part in a condition
// on order_id, and the table leaves them out.
const stats = { statistics: true, bloom: false, pageIndex: false, wholeChunks: true };
const pages = { statistics: true, bloom: false, pageIndex: true, wholeChunks: false };
const STRATEGIES = [
  ["HEAD, trailer, footer; every column chunk",
    { footer: "head", prefetch: 8, connections: 1, gap: null, statistics: false, bloom: false, pageIndex: false, wholeChunks: true }],
  ["… skipping row groups by statistics", { footer: "head", prefetch: 8, connections: 1, gap: null, ...stats }],
  ["… and pages by the page index", { footer: "head", prefetch: 8, connections: 1, gap: null, ...pages }],
  ["… with an 8 KiB suffix read for the footer", { footer: "suffix", prefetch: 8192, connections: 1, gap: null, ...pages }],
  ["… merging ranges within 4 KiB", { footer: "suffix", prefetch: 8192, connections: 1, gap: 4096, ...pages }],
  ["… on four connections, without merging", { footer: "suffix", prefetch: 8192, connections: 4, gap: null, ...pages }],
  ["One suffix read of 64 KiB: the whole file", { footer: "suffix", prefetch: 65536, connections: 1, gap: null, ...pages }],
];
// The network the table assumes: the simulated store's default.
const NETWORK = { latencyUs: 20000, bandwidth: 100000000 };

export async function mountScan(root, lab, files, initial, config) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);
  const form = document.createElement("form");
  form.className = "controls scan-pick";
  form.innerHTML = `<div class="row"><label>Strategy <select name="strategy">${STRATEGIES.map(([label], i) =>
    `<option value="${i}"${i === 2 ? " selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label></div>`;
  root.append(form);
  const grid = document.createElement("div");
  grid.className = "scan-grid";
  grid.innerHTML = `
    <section class="panel p-scan-sum"><h4>The cost</h4><div class="scan-sum"></div></section>
    <section class="panel p-scan-time"><h4>Requests over time, by connection</h4><div class="timeline"></div></section>`;
  root.append(grid);

  const where = { column: Number(config.column ?? 0), op: config.op || "=", value: config.value || "" };
  let id = null;
  const run = () => {
    const r = lab.scan(id, [], where, { ...STRATEGIES[Number(form.elements.strategy.value)][1], ...NETWORK });
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      grid.querySelector(".scan-sum").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      grid.querySelector(".timeline").innerHTML = "";
      return;
    }
    root.dataset.requests = String(r.totals.requests);
    root.dataset.elapsed = String(r.totals.elapsed_us);
    root.dataset.matching = String(r.totals.rows_matching);
    drawSummary(grid.querySelector(".scan-sum"), r);
    drawTimeline(grid.querySelector(".timeline"), r);
  };
  form.addEventListener("change", run);
  const choose = fileChooser(head, files, initial, async (name) => {
    id = lab.load(name, await files.get(name));
    run();
  });
  await choose();
}

function drawSummary(box, r) {
  const t = r.totals;
  box.innerHTML = `<dl class="scan-costs">` +
    `<div><dt>Requests</dt><dd>${fmt(t.requests)}</dd></div>` +
    `<div><dt>Time</dt><dd>${ms(t.elapsed_us)}</dd></div>` +
    `<div><dt>Bytes fetched</dt><dd>${fmt(t.bytes_fetched)} <small>of ${fmt(r.file_size)}</small></dd></div>` +
    `<div><dt>Rows matching</dt><dd>${fmt(t.rows_matching)}</dd></div></dl>` +
    `<p class="note">Time is simulated: each request costs the latency, then its bytes over the bandwidth.</p>`;
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
        return `<span class="req ${kind}" style="left:${left}%;width:${width}%"` +
          ` title="${escapeHtml(`#${q.seq} ${q.method} ${q.range || ""}: ${q.why}`)}">${q.seq}</span>`;
      }).join("") + "</div></div>";
  }
  box.innerHTML = html + `<p class="note">0 to ${ms(end)}. Grey finds the footer, orange fetches indexes, blue fetches data. Each request that depends on an earlier one waits for it.</p>`;
}
