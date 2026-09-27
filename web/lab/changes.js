// The changing-table laboratory (ch15): look up one order in a snapshot of a table that has been
// changed by copy-on-write, by position delete files and by small appends, then compacted, and
// see its requests over time on each connection.
//
// Everything is `report::changes`: the reader read the snapshots, chose the files, fetched them
// through the simulated store and applied the deletes. This file draws.

import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const ms = (us) => `${(us / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} ms`;

export async function mountChanges(root, lab, files, initial, config) {
  // Load every object into the reader's store, under its key. The reader still has to read the
  // snapshots to learn which of them make up the table.
  const listing = JSON.parse(new TextDecoder().decode(await files.get(initial)));
  const ids = [];
  for (const o of listing.objects) ids.push(lab.load(o.key, await files.get(o.key)));
  const snapshots = Object.keys(listing.snapshots);

  const form = document.createElement("form");
  form.className = "controls";
  form.innerHTML = `
    <div class="row"><label>Snapshot <select name="snapshot">${snapshots.map((s) =>
      `<option${s === (config.snapshot || "after-a-day") ? " selected" : ""}>${escapeHtml(s)}</option>`).join("")}</select></label>
      <label>Find order <input name="key" type="number" min="0" max="99999" value="300" aria-label="order_id"></label></div>`;
  root.append(form);
  const grid = document.createElement("div");
  grid.className = "changes-grid";
  grid.innerHTML = `
    <section class="panel c-answer"><h4>The answer</h4><div class="c-answer-body"></div></section>
    <section class="panel c-time"><h4>Requests over time, by connection</h4><div class="timeline"></div></section>`;
  root.append(grid);
  const $ = (k) => grid.querySelector(k);

  const run = () => {
    const f = form.elements;
    const r = lab.changes(ids, f.snapshot.value, Math.max(0, Number(f.key.value) || 0));
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      $(".c-answer-body").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      $(".timeline").innerHTML = "";
      return;
    }
    const t = r.totals;
    root.dataset.requests = String(t.requests);
    root.dataset.roundTrips = String(t.round_trips);
    root.dataset.answer = r.row.length ? "found" : r.deleted_by ? "deleted" : "absent";
    const where = r.found ? `<code>${escapeHtml(r.found.path)}</code>, row ${fmt(r.found.position)}` : "";
    const found = r.row.length ? `Order ${fmt(r.key)} is in ${where}.`
      : r.deleted_by ? `Order ${fmt(r.key)} is in ${where}, but <code>${escapeHtml(r.deleted_by)}</code> deletes it.`
        : `No file holds order ${fmt(r.key)}.`;
    $(".c-answer-body").innerHTML = `<p class="note">${found}</p>` +
      `<dl class="scan-costs"><dt>This table</dt><dd>${ms(t.elapsed_us)} <small>${fmt(t.round_trips)} round trips, ${fmt(t.requests)} requests, ${fmt(t.bytes_fetched)} bytes</small></dd>` +
      `<dt>A key-value store</dt><dd>${ms(r.key_value.elapsed_us)} <small>1 request, ${fmt(r.key_value.bytes)} bytes</small></dd></dl>`;
    drawTimeline($(".timeline"), r);
  };

  function drawTimeline(box, r) {
    const end = Math.max(1, r.totals.elapsed_us);
    const lanes = Math.max(1, ...r.requests.map((q) => q.connection + 1));
    let html = "";
    for (let lane = 0; lane < lanes; lane++) {
      html += `<div class="lane"><span class="lane-name">${lane + 1}</span><div class="lane-track">` +
        r.requests.filter((q) => q.connection === lane).map((q) => {
          const left = (q.start_us / end) * 100;
          const width = Math.max(0.6, ((q.end_us - q.start_us) / end) * 100);
          const kind = q.key.includes("/deletes/") || q.key.endsWith(".json") ? "idx" : q.why.includes("pages") ? "data" : "foot";
          return `<span class="req ${kind}" style="left:${left}%;width:${width}%" title="${escapeHtml(`#${q.seq} ${q.method} ${q.key} ${q.range || ""}: ${q.why}`)}">${q.seq}</span>`;
        }).join("") + "</div></div>";
    }
    box.innerHTML = html + `<p class="note">0 to ${ms(end)}. Orange reads the snapshots and delete files, grey a data file's trailer, footer and indexes, blue its pages. A request that needs an earlier one's answer waits for it.</p>`;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    run();
  });
  form.addEventListener("change", run);
  run();
}
