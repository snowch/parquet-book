// Mount every experiment on the page.
//
// A chapter marks an experiment with a fenced block in the language `lab`; tools/render.py turns
// it into <div class="lab" data-experiment=… data-fixture=…>. This script loads the reader once
// per page, fetches the fixtures the experiments name, and hands each mount point to its
// experiment. Paths are resolved from this script's own URL, so the book works wherever it is
// served from, including a GitHub Pages project path.
//
// A panel is a picture, and it is always drawn by the Rust reader compiled to WebAssembly
// (wasm.js). The Python reader runs in the page too, in the walkthrough steps, the Run buttons and
// the problems workbench, all in one worker (runner.js); tests/test_python.py holds the two
// readers to the same JSON natively.
//
// A chapter's problems workbench (workbench.js) mounts here too, and so do the Run buttons on
// the Python commands a page prints (commands.js).

import { Lab } from "./wasm.js";
import { mountAnatomy } from "./footer.js";
import { mountCompression } from "./compression.js";
import { mountScan } from "./scan.js";
import { mountEncryption } from "./encryption.js";
import { mountTable } from "./table.js";
import { mountChanges } from "./changes.js";
import { mountWorkbench } from "./workbench.js";
import { mountCommands } from "./commands.js";

const EXPERIMENTS = {
  anatomy: mountAnatomy,
  compression: mountCompression,
  scan: mountScan,
  encryption: mountEncryption,
  table: mountTable,
  changes: mountChanges,
};

class Fixtures {
  constructor(names) {
    this.list = names;
    this.cache = new Map();
  }
  names() {
    return this.list;
  }
  async get(name) {
    if (!this.cache.has(name)) {
      const url = new URL(`../fixtures/${name}`, import.meta.url);
      this.cache.set(name, fetch(url).then(async (r) => {
        if (!r.ok) throw new Error(`could not fetch ${name}: ${r.status}`);
        return new Uint8Array(await r.arrayBuffer());
      }));
    }
    return this.cache.get(name);
  }
}

let loading = null;
function loadReader() {
  loading ||= Lab.fromUrl(new URL("parquet_lab.wasm", import.meta.url));
  return loading;
}

async function mount(el) {
  // What the page asked for, before the experiment writes its results into the same attributes.
  const config = { ...el.dataset };
  const run = EXPERIMENTS[config.experiment];
  el.dataset.ready = "loading";
  el.innerHTML = '<p class="lab-loading">Loading the reader…</p>';
  try {
    const lab = await loadReader();
    const names = (config.fixtures || config.fixture || "").split(",").map((s) => s.trim()).filter(Boolean);
    const files = new Fixtures(names);
    el.innerHTML = "";
    await run(el, lab, files, config.fixture || names[0], config);
    el.dataset.ready = "true";
  } catch (error) {
    const message = document.createElement("p");
    message.className = "lab-error";
    message.textContent = `The experiment could not start: ${String(error.message || error)}`;
    el.replaceChildren(message);
    el.dataset.ready = "error";
    throw error;
  }
}

for (const el of document.querySelectorAll(".lab[data-experiment]")) mount(el);
for (const el of document.querySelectorAll(".workbench[data-chapter]")) {
  mountWorkbench(el).catch((error) => {
    const message = document.createElement("p");
    message.className = "lab-error";
    message.textContent = `The workbench could not start: ${String(error.message || error)}`;
    el.replaceChildren(message);
    el.dataset.ready = "error";
  });
}
mountCommands();
