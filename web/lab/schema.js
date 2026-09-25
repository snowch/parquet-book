// The schema laboratory (ch03): the schema as the footer stores it, as the reader rebuilds it,
// and what each column's bytes mean once its logical type is applied.
//
// Everything comes from `report::schema` in Rust. The flat list is the footer's own order; the
// tree is the reader's reconstruction from `num_children`; the readings of each statistic are
// the reader's, physical and logical. Selecting anything highlights the bytes it came from.

import { FileViews, fileChooser } from "./footer.js";
import { escapeHtml } from "./hexview.js";

export function mountSchema(root, lab, files, initial) {
  const head = document.createElement("div");
  head.className = "lab-head";
  root.append(head);

  const top = document.createElement("div");
  top.className = "schema-grid";
  top.innerHTML = `
    <section class="panel p-flat"><h4>As stored: a flat list in the footer</h4><div class="flat"></div></section>
    <section class="panel p-rebuilt"><h4>As rebuilt: a tree</h4><pre class="schema-text"></pre></section>`;
  root.append(top);
  const valuesBox = document.createElement("section");
  valuesBox.className = "panel p-values";
  valuesBox.innerHTML = "<h4>What each column's statistics mean</h4><div class=\"values\"></div>";
  root.append(valuesBox);

  const views = new FileViews(root, lab, { withTrace: false });

  const show = (span) => {
    views.hex.highlight(span);
    views.hex.select(span[0], span[1]);
  };
  root.addEventListener("click", (e) => {
    const t = e.target.closest("[data-span]");
    if (!t || !root.contains(t) || t.closest(".p-hex, .p-tree, .p-inspect")) return;
    for (const m of root.querySelectorAll(".schema-picked")) m.classList.remove("schema-picked");
    const el = t.dataset.element;
    if (el !== undefined) {
      for (const m of root.querySelectorAll(`[data-element="${el}"]`)) m.classList.add("schema-picked");
    }
    show(JSON.parse(t.dataset.span));
  });

  views.onChange = () => {
    const s = lab.schema(views.id);
    root.dataset.state = s.ok ? "ok" : "error";
    if (!s.ok) {
      top.querySelector(".flat").innerHTML = `<p class="lab-error">${escapeHtml(s.error)}</p>`;
      top.querySelector(".schema-text").textContent = "";
      valuesBox.querySelector(".values").innerHTML = "";
      return;
    }
    root.dataset.leaves = String(s.leaves.length);
    drawFlat(top.querySelector(".flat"), s);
    drawTree(top.querySelector(".schema-text"), s);
    drawValues(valuesBox.querySelector(".values"), s);
  };

  const choose = fileChooser(head, files, initial, async (name) => views.open(name, await files.get(name)));
  choose();
}

const span = (s) => escapeHtml(JSON.stringify(s));

function drawFlat(box, s) {
  box.innerHTML = `<table class="flat-list"><thead><tr><th>#</th><th>Name</th><th>Children</th>` +
    `<th>Repetition</th><th>Physical type</th><th>Bytes</th></tr></thead><tbody>` +
    s.elements.map((e) => {
      const type = e.physical_type ? `${e.physical_type}${e.type_length ? `(${e.type_length})` : ""}` : "(group)";
      return `<tr data-element="${e.index}" data-span="${span(e.span)}"><td>${e.index}</td>` +
        `<td><code>${escapeHtml(e.name)}</code></td><td>${e.num_children ?? ""}</td>` +
        `<td>${escapeHtml((e.repetition || "").toLowerCase())}</td><td>${type}</td>` +
        `<td class="num">[${e.span[0]}, ${e.span[1]})</td></tr>`;
    }).join("") + "</tbody></table>";
}

// The textual notation, a line per element, each line pointing at its element's bytes.
function drawTree(pre, s) {
  const lines = [];
  const leaves = new Map(s.leaves.map((l) => [l.element, l]));
  const element = (i) => s.elements[i];
  const walk = (node, depth) => {
    const e = element(node.element);
    const pad = "  ".repeat(depth);
    const note = e.logical_type ? ` (${escapeHtml(e.logical_type)})` : "";
    const attrs = `data-element="${node.element}" data-span="${span(node.span)}"`;
    if (node.children.length) {
      const opener = depth === 0 ? `message ${escapeHtml(node.name)}` : `${node.repetition} group ${escapeHtml(node.name)}${note}`;
      lines.push(`<span class="line" ${attrs}>${pad}${opener} {</span>`);
      for (const c of node.children) walk(c, depth + 1);
      lines.push(`<span class="line">${pad}}</span>`);
    } else {
      const t = { byte_array: "binary", fixed_len_byte_array: `fixed_len_byte_array(${e.type_length})` }[
        e.physical_type.toLowerCase()] || e.physical_type.toLowerCase();
      const leaf = leaves.get(node.element);
      const levels = leaf ? `<span class="levels">def ≤ ${leaf.max_definition_level}, rep ≤ ${leaf.max_repetition_level}</span>` : "";
      lines.push(`<span class="line" ${attrs}>${pad}${node.repetition} ${t} ${escapeHtml(node.name)}${note};${levels}</span>`);
    }
  };
  walk(s.tree, 0);
  pre.innerHTML = lines.join("");
}

function reading(r) {
  if (!r) return "<td></td><td></td><td></td>";
  return `<td><button type="button" class="span" data-span="${span(r.span)}">${escapeHtml(r.hex)}</button></td>` +
    `<td>${escapeHtml(r.physical ?? "")}</td>` +
    `<td class="${r.logical ? "logical" : "same"}">${escapeHtml(r.logical ?? "·")}</td>`;
}

function drawValues(box, s) {
  box.innerHTML = `<div class="table-wrap"><table class="values-table"><thead><tr><th>Column</th>` +
    `<th>Physical</th><th>Logical</th><th>Minimum's bytes</th><th>Read as physical</th><th>Read as logical</th>` +
    `</tr></thead><tbody>` +
    s.leaves.map((l) => `<tr data-element="${l.element}"><td><button type="button" class="span" data-element="${l.element}" ` +
      `data-span="${span(l.chunk || [0, 0])}">${escapeHtml(l.path)}</button></td>` +
      `<td>${l.physical_type}</td><td>${escapeHtml(l.logical_type ?? "")}</td>` +
      reading(l.statistics && l.statistics.min) + "</tr>").join("") +
    "</tbody></table></div>";
}
