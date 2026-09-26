// Edit the Python reader, and run the page's labs on your edit.
//
// The labs' Python engine offers "Edit the code". The panel opens below that lab with the module
// the lab's chapter builds, and any other module of the reader a reader picks. "Run the labs on
// this code" puts the edits in place of the book's files, imports the reader again and remounts
// every lab on the page, so what the labs show is what the edited code computes. An edit that
// breaks the reader shows Python's error here and in every lab. The edits stay in this browser,
// and every lab's engine bar says so while they are in use.
//
// On the Rust engine, "Edit the code" says where the Rust reader can be edited and run: a
// Codespace, since the page cannot compile Rust.

import { KEYS, codeArea } from "./code.js";
import { saveEdits } from "./python.js";
import { CODESPACES } from "./workbench.js";

/** The module each lab's chapter builds, which the editor opens first. */
const MODULE = {
  layouts: "layout.py", footer: "reader.py", anatomy: "metadata.py", schema: "schema.py",
  levels: "column.py", encodings: "decode.py", pages: "pages.py", compression: "compress.py",
  statistics: "stats.py", skipping: "prune.py", scan: "scan.py", writing: "prune.py",
  engine: "engine.py", encryption: "crypto.py", table: "table.py",
};

let panel = null;
let rustPanel = null;

const REPO = "https://github.com/snowch/parquet-book/blob/main/";

/**
 * "Edit the code" on the Rust engine. Rust needs a compiler, which the page does not have, so the
 * edit happens in a Codespace, where `make` rebuilds the WebAssembly module from your edit and
 * `make serve` shows the book with every lab on it. The panel says so, names the file, and offers
 * the Python reader, which the page can edit.
 */
export function openRustEditor(labEl, usePython) {
  const file = `crates/parquet-lab/src/${(MODULE[labEl.dataset.experiment] || "report.py").replace(/\.py$/, ".rs")}`;
  rustPanel ||= document.createElement("section");
  const el = rustPanel;
  el.className = "reader-editor";
  el.setAttribute("aria-label", "Edit the Rust reader");
  el.innerHTML = `
    <div class="lab-head"><span class="lab-title">Edit the Rust reader</span>
      <span class="lab-note">Rust compiles in a Codespace, not in the page</span>
      <button type="button" data-act="close" aria-label="Close">Close</button></div>
    <ol class="rust-steps">
      <li><a href="${CODESPACES}" target="_blank" rel="noopener">Open the repository in GitHub Codespaces</a>:
        the pinned Rust toolchain and an editor, in your browser.</li>
      <li>Edit <a href="${REPO}${file}" target="_blank" rel="noopener"><code>${file}</code></a>, the code
        this lab runs.</li>
      <li>In its terminal, run <code>make &amp;&amp; make serve</code>. The book opens on port 8000, and
        every lab runs your edited reader. <code>cargo test -p parquet-lab</code> checks your edit
        against what pyarrow wrote.</li>
    </ol>
    <div class="workbench-bar"><button type="button" class="primary" data-act="python">Edit the Python reader here instead</button></div>`;
  el.onclick = (e) => {
    const act = e.target.closest("button[data-act]")?.dataset.act;
    if (act === "close") el.remove();
    if (act === "python") {
      el.remove();
      usePython();
    }
  };
  labEl.after(el);
  el.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

/** Open the editor below `labEl`, for the Python engine `lab`; `remount` reruns every lab. */
export function openEditor(labEl, lab, remount) {
  if (!panel) panel = build(lab, remount);
  labEl.after(panel.el);
  panel.show(MODULE[labEl.dataset.experiment] || "report.py");
  panel.el.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function build(lab, remount) {
  const el = document.createElement("section");
  el.className = "reader-editor";
  el.setAttribute("aria-label", "The Python reader, editable");
  const names = Object.keys(lab.book).sort();
  el.innerHTML = `
    <div class="lab-head"><span class="lab-title">Edit the Python reader</span>
      <label>File <select name="module">${names.map((n) => `<option value="${n}">parquet_lab/${n}</option>`).join("")}</select></label>
      <span class="lab-note">Your edits stay in this browser</span>
      <button type="button" data-act="close" aria-label="Close the editor">Close</button></div>
    <div class="workbench-bar">
      <button type="button" class="primary" data-act="run">Run the labs on this code</button>
      <button type="button" data-act="restore">Restore the book's version</button>
      <span class="status" role="status"></span>
    </div>
    <pre class="editor-error" hidden></pre>
    <p class="workbench-note">${KEYS}. Every lab on this page runs on the edited reader until you
      restore it. To edit and run the Rust reader online, open the repository in
      <a href="${CODESPACES}" target="_blank" rel="noopener">GitHub Codespaces</a>.</p>`;
  const select = el.querySelector("select");
  const status = el.querySelector(".status");
  const error = el.querySelector(".editor-error");
  // What the text area holds for each file, edited or not: switching files keeps the drafts.
  const drafts = { ...lab.edits };
  const text = (name) => drafts[name] ?? lab.book[name];
  let current = null;
  const area = codeArea("", {
    label: "The Python reader's source",
    onRun: () => apply(),
    onInput: (value) => {
      drafts[current] = value;
      mark();
    },
  });
  area.rows = 24;
  el.querySelector(".workbench-bar").before(area);

  function mark() {
    for (const o of select.options) {
      o.textContent = `parquet_lab/${o.value}${text(o.value) !== lab.book[o.value] ? " (edited)" : ""}`;
    }
  }

  function show(name) {
    current = name;
    select.value = name;
    area.value = text(name);
    mark();
  }

  function apply() {
    for (const [name, value] of Object.entries(drafts)) if (value === lab.book[name]) delete drafts[name];
    const failed = lab.use(drafts);
    saveEdits(lab.edits);
    error.hidden = !failed;
    error.textContent = failed || "";
    const edited = Object.keys(lab.edits);
    status.textContent = failed
      ? "The edited reader does not import; the labs show why."
      : edited.length ? `The labs run on your edits to ${edited.join(", ")}.` : "The labs run on the book's reader.";
    el.dataset.state = failed ? "error" : "ok";
    remount();
  }

  select.addEventListener("change", () => show(select.value));
  el.addEventListener("click", (e) => {
    const act = e.target.closest("button[data-act]")?.dataset.act;
    if (act === "run") apply();
    if (act === "restore") {
      delete drafts[current];
      area.value = lab.book[current];
      apply();
    }
    if (act === "close") el.remove();
  });
  return { el, show };
}
