// The changing-table laboratory (ch15): one snapshot of a table that has been changed by
// copy-on-write, by position delete files and by small appends, then compacted. Scan it, look up
// one order, or plan a compaction, and see every file and every request.
//
// Everything is `report::changes`: the reader read the snapshots, chose the files, fetched them
// through the simulated store, applied the deletes and planned the compaction. This file draws.

import { escapeHtml } from "./hexview.js";

const fmt = (n) => Number(n).toLocaleString("en-GB");
const ms = (us) => `${(us / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })} ms`;
const cell = (v) => escapeHtml(v === null ? "null" : String(v));

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
      <label>Connections <select name="connections"><option>1</option><option>2</option><option selected>4</option><option>8</option></select></label></div>
    <div class="row"><fieldset class="mechanisms"><legend>Operation</legend>
      <label><input type="radio" name="op" value="scan"> scan every row</label>
      <label><input type="radio" name="op" value="lookup" checked> find order <input name="key" type="number" min="0" max="99999" value="300" aria-label="order_id"></label>
      <label><input type="radio" name="op" value="compact"> plan a compaction: files of
        <input name="target" type="number" min="1" max="100000" value="200" aria-label="target rows"> rows, small under
        <input name="small" type="number" min="0" max="100000" value="100" aria-label="small file rows"></label></fieldset>
      <label>Tail read first <select name="prefetch"><option value="0" selected>the trailer</option><option value="16384">16 KiB</option><option value="65536">64 KiB</option></select></label></div>`;
  root.append(form);
  const grid = document.createElement("div");
  grid.className = "changes-grid";
  grid.innerHTML = `
    <section class="panel c-files"><h4>The snapshot's files</h4><div class="c-files-body"></div></section>
    <section class="panel c-answer"><h4>The answer</h4><div class="c-answer-body"></div></section>
    <section class="panel c-time"><h4>Requests over time, by connection</h4><div class="timeline"></div></section>
    <section class="panel c-reqs"><h4>Requests</h4><div class="c-reqs-body"></div></section>`;
  root.append(grid);
  const $ = (k) => grid.querySelector(k);

  const run = () => {
    const f = form.elements;
    const r = lab.changes(ids, f.snapshot.value, f.op.value, {
      key: Math.max(0, Number(f.key.value) || 0),
      targetRows: Math.max(1, Number(f.target.value) || 1),
      smallRows: Math.max(0, Number(f.small.value) || 0),
      prefetch: Number(f.prefetch.value),
      connections: Number(f.connections.value),
    });
    root.dataset.state = r.ok ? "ok" : "error";
    if (!r.ok) {
      $(".c-files-body").innerHTML = `<p class="lab-error">${escapeHtml(r.error)}</p>`;
      for (const k of [".c-answer-body", ".timeline", ".c-reqs-body"]) $(k).innerHTML = "";
      return;
    }
    const t = r.totals;
    root.dataset.requests = String(t.requests);
    root.dataset.roundTrips = String(t.round_trips);
    const read = r.files.filter((x) => x.read).length;
    $(".c-files-body").innerHTML = `<p class="note"><code>${escapeHtml(r.snapshot.id)}</code>: ${escapeHtml(r.snapshot.summary)}. ` +
      `${r.operation === "compact" ? "Rewrites" : "Reads"} ${read} of ${r.files.length} files.</p>` +
      `<div class="table-wrap"><table class="pages-list"><thead><tr><th>File</th><th class="num">Bytes</th><th class="num">Rows</th><th>Decision</th></tr></thead><tbody>` +
      r.files.map((x) => `<tr class="${x.read ? "" : "skipped"} ${x.kind}"><td><code>${escapeHtml(x.path)}</code></td><td class="num">${fmt(x.size)}</td>` +
        `<td class="num">${fmt(x.rows)}</td><td>${escapeHtml(x.why)}</td></tr>`).join("") + "</tbody></table></div>";
    $(".c-answer-body").innerHTML = answer(r);
    root.dataset.answer = r.operation === "scan" ? String(r.answer.live_rows)
      : r.operation === "lookup" ? (r.row.length ? "found" : r.deleted_by ? "deleted" : "absent") : String(r.groups.length);
    drawTimeline($(".timeline"), r);
    $(".c-reqs-body").innerHTML = `<p class="note">${fmt(t.requests)} requests in ${fmt(t.round_trips)} round trips, ${fmt(t.bytes_fetched)} bytes, ${ms(t.elapsed_us)} simulated.</p>` +
      `<div class="table-wrap"><table class="pages-list"><thead><tr><th>#</th><th>Round trip</th><th>Request</th><th class="num">Bytes</th><th class="num">End</th><th>Why</th></tr></thead><tbody>` +
      r.requests.map((q) => `<tr><td>${q.seq}</td><td>${q.phase + 1}</td><td><code>${escapeHtml(q.method)} ${escapeHtml(q.key.replace(/^changes\//, ""))}${q.range ? ` ${escapeHtml(q.range)}` : ""}</code></td>` +
        `<td class="num">${fmt(q.bytes)}</td><td class="num">${ms(q.end_us)}</td><td>${escapeHtml(q.why)}</td></tr>`).join("") + "</tbody></table></div>";
  };

  function answer(r) {
    const t = r.totals;
    if (r.operation === "scan") {
      return `<dl class="scan-costs"><dt>Rows in the table</dt><dd>${fmt(r.answer.live_rows)}</dd>` +
        `<dt>Rows decoded</dt><dd>${fmt(t.rows_decoded)}</dd>` +
        `<dt>sum(amount_cents)</dt><dd>${fmt(r.answer.sum_amount_cents)}</dd>` +
        `<dt>Time</dt><dd>${ms(t.elapsed_us)} <small>${fmt(t.requests)} requests</small></dd></dl>`;
    }
    if (r.operation === "lookup") {
      const where = r.found ? `<code>${escapeHtml(r.found.path)}</code>, row ${fmt(r.found.position)}` : "no file holds it";
      const row = r.row.length
        ? `<div class="table-wrap"><table class="pages-list"><tbody>${r.row.map((c) => `<tr><th>${escapeHtml(c.column)}</th><td>${cell(c.value)}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="note">${r.deleted_by ? `Found in ${where}, but <code>${escapeHtml(r.deleted_by)}</code> deletes it.` : `Order ${fmt(r.key)}: ${where}.`}</p>`;
      return `<dl class="scan-costs"><dt>This table</dt><dd>${ms(t.elapsed_us)} <small>${fmt(t.round_trips)} round trips, ${fmt(t.bytes_fetched)} bytes</small></dd>` +
        `<dt>A key-value store</dt><dd>${ms(r.key_value.elapsed_us)} <small>1 request, ${fmt(r.key_value.bytes)} bytes</small></dd></dl>` +
        (r.row.length ? `<p class="note">Order ${fmt(r.key)}, in ${where}:</p>` : "") + row;
    }
    return (r.groups.length
      ? `<ol class="pipeline">${r.groups.map((g) => `<li><strong>${g.data_files.length} data file${g.data_files.length === 1 ? "" : "s"}</strong>` +
          `${g.delete_files.length ? ` and ${g.delete_files.length} delete file${g.delete_files.length === 1 ? "" : "s"}` : ""}` +
          ` <span class="flow">${fmt(g.rows_in)} rows in, ${fmt(g.rows_out)} out, ${fmt(g.bytes_in)} bytes to read</span>` +
          `<p class="detail">${g.data_files.map((p) => `<code>${escapeHtml(p)}</code>`).join(" ")}</p></li>`).join("")}</ol>`
      : '<p class="note">Nothing to compact: no file has deletes, and no group of small files has more than one.</p>') +
      `<p class="note">${fmt(r.bytes_in)} bytes to read, then write back as ${fmt(r.groups.length)} file${r.groups.length === 1 ? "" : "s"}.</p>`;
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
          const kind = q.key.includes("/deletes/") || q.key.endsWith(".json") ? "idx" : q.why.includes("pages") || q.why.includes("data file") ? "data" : "foot";
          return `<span class="req ${kind}" style="left:${left}%;width:${width}%" title="${escapeHtml(`#${q.seq} ${q.method} ${q.key} ${q.range || ""}: ${q.why}`)}">${q.seq}</span>`;
        }).join("") + "</div></div>";
    }
    box.innerHTML = html + `<p class="note">0 to ${ms(end)}. Orange reads the snapshots and delete files, grey a data file's footer and indexes, blue its data. A request that needs an earlier one's answer waits for it.</p>`;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    run();
  });
  form.addEventListener("change", run);
  run();
}
