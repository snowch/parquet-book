// The whole file (ch02): a Parquet file's bytes, the structure the reader parsed from them, and an
// inspector, each view pointing at the others.
//
// The structure is the reader's (`report::structure`), and the dim bytes are the ones the reader
// never asked for when it opened the file (`report::footer_lab`, the trace of a store that logs
// every request). Edit a byte and the reader parses the file again from nothing. How the reader
// opens a file is in the chapter as code to run and change, not as controls here.

import { HexView, escapeHtml } from "./hexview.js";
import { StructureTree, regionsFrom, pathTo } from "./tree.js";
import { Inspector } from "./inspector.js";

// A panel with a title, into which a component draws.
function panel(parent, title, cls) {
  const box = document.createElement("section");
  box.className = `panel ${cls}`;
  box.innerHTML = `<h4>${title}</h4>`;
  parent.append(box);
  return box;
}

// A file loaded into the module, its bytes, its structure, and the three coordinated views over
// them.
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
    // A selection belongs to the file it was made in.
    this.hex.selection = null;
    this.inspector.el.innerHTML = '<p class="hint">Select a byte in the byte view. Shift-click to select a range.</p>';
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
  views.dimmed = true;
  // The bytes the reader never asks for when it opens the file, as the chapter's code step opened
  // it: the reader's own trace (`report::footer_lab`), with nothing dimmed if it refuses the file.
  views.onChange = () => {
    const r = lab.footerLab(views.id);
    if (r.ok) views.hex.dimOutside(r.fetched);
    else views.hex.clearDim();
    root.dataset.state = r.ok ? "ok" : "error";
    root.dataset.footerLength = r.ok ? String(r.trailer.footer_length) : "";
    root.dataset.unfetched = String(r.ok ? r.file_size - r.totals.bytes_returned : 0);
  };
  const choose = fileChooser(head, files, initial, async (name) => views.open(name, await files.get(name)));
  choose();
}

/** What runs this lab, for its heading: the Rust reader or the Python one (see lab.js). */
export function engineNote(el) {
  return el.closest(".lab")?.dataset.engine === "python"
    ? "running the book's Python reader, in your browser through Pyodide"
    : "running the book's Rust reader, compiled to WebAssembly";
}

export function fileChooser(head, files, initial, open) {
  const names = files.names();
  head.innerHTML = `<span class="lab-title">Parquet laboratory</span>` +
    (names.length > 1
      ? `<label>file <select>${names.map((n) => `<option${n === initial ? " selected" : ""}>${escapeHtml(n)}</option>`).join("")}</select></label>`
      : `<code>${escapeHtml(initial)}</code>`) +
    `<span class="lab-note">${engineNote(head)}</span>`;
  const select = head.querySelector("select");
  if (select) select.addEventListener("change", () => open(select.value));
  return () => open(initial);
}
