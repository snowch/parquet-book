// The structure view: the file as the Rust reader parsed it, as a tree of byte ranges.
//
// Every node has a span, so a node and its bytes can always be shown together. Selecting a node
// highlights its bytes; selecting a byte opens the tree down to the deepest node that contains
// it. The tree is `report::structure`'s JSON, drawn as it arrives.

import { escapeHtml } from "./hexview.js";

// Colour classes for the byte view, by the kind of region the reader reported. Column chunks
// take one of four hues in turn, and their pages share their column's hue.
export function regionsFrom(tree) {
  const regions = [];
  let column = -1;
  const visit = (node, colour) => {
    const kind = node.kind;
    if (kind === "column_chunk") {
      column += 1;
      colour = `col${column % 4}`;
    }
    const cls = {
      magic: "r-magic",
      footer: "r-footer",
      footer_length: "r-length",
      page_header: `r-pagehead ${colour}`,
      page_body: `r-body ${colour}`,
    }[kind];
    if (cls) regions.push({ span: node.span, cls, title: node.label });
    // The footer's own Thrift fields are not coloured separately: the footer is one colour,
    // and the tree says which field a byte belongs to.
    if (kind !== "footer") for (const c of node.children || []) visit(c, colour);
  };
  visit(tree, "");
  return regions;
}

// The chain of nodes from the root to the deepest one whose span contains `offset`.
export function pathTo(tree, offset) {
  const path = [];
  let node = tree;
  while (node) {
    path.push(node);
    node = (node.children || []).find((c) => c.span[0] <= offset && offset < c.span[1] && c.span[1] > c.span[0]);
  }
  return path;
}

export class StructureTree {
  constructor(container, { onPick } = {}) {
    this.el = document.createElement("div");
    this.el.className = "tree";
    container.append(this.el);
    this.onPick = onPick || (() => {});
    this.nodes = [];
    this.el.addEventListener("click", (e) => {
      const row = e.target.closest(".node-row");
      if (!row) return;
      const li = row.parentElement;
      if (e.target.closest(".twisty")) {
        li.classList.toggle("open");
        return;
      }
      this.#mark(li);
      li.classList.add("open");
      this.onPick(this.nodes[Number(li.dataset.i)]);
    });
  }

  render(tree, { openKinds = ["file", "row_group", "footer", "trailer"] } = {}) {
    this.nodes = [];
    const draw = (node, depth) => {
      const i = this.nodes.push(node) - 1;
      const kids = node.children || [];
      const open = openKinds.includes(node.kind) && depth < 3 ? " open" : "";
      const value = node.value === null || node.value === undefined ? "" : String(node.value);
      const [a, b] = node.span;
      return `<li data-i="${i}" class="k-${escapeHtml(node.kind)}${kids.length ? " has-kids" : ""}${open}">` +
        `<div class="node-row"><span class="twisty" aria-hidden="true"></span>` +
        `<span class="node-label">${escapeHtml(node.label)}</span>` +
        `<span class="node-span">[${a}, ${b})</span>` +
        (value ? `<span class="node-value">${escapeHtml(value)}</span>` : "") +
        `</div>` +
        (kids.length ? `<ul>${kids.map((c) => draw(c, depth + 1)).join("")}</ul>` : "") +
        `</li>`;
    };
    this.el.innerHTML = `<ul class="root">${draw(tree, 0)}</ul>`;
    this.tree = tree;
  }

  showError(message) {
    this.tree = null;
    this.el.innerHTML = `<p class="lab-error">The reader could not map this file: ${escapeHtml(message)}</p>`;
  }

  // Open the tree down to the deepest node containing `offset`, and mark it.
  reveal(offset) {
    if (!this.tree) return null;
    const path = pathTo(this.tree, offset);
    let li = null;
    for (const node of path) {
      const i = this.nodes.indexOf(node);
      li = this.el.querySelector(`li[data-i="${i}"]`);
      if (li) li.classList.add("open");
    }
    if (li) {
      this.#mark(li);
      const row = li.querySelector(".node-row");
      const box = this.el.getBoundingClientRect();
      const r = row.getBoundingClientRect();
      if (r.top < box.top || r.bottom > box.bottom) {
        this.el.scrollTop += r.top - box.top - box.height / 3;
      }
    }
    return path;
  }

  #mark(li) {
    for (const m of this.el.querySelectorAll(".picked")) m.classList.remove("picked");
    li.classList.add("picked");
  }
}
