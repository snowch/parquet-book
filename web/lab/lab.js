// Mount every experiment on the page.
//
// A chapter marks an experiment with a fenced block in the language `lab`; tools/render.py turns
// it into <div class="lab" data-experiment=… data-fixture=…>. This script loads the WebAssembly
// reader once per page, fetches the fixtures the experiments name, and hands each mount point to
// its experiment. Paths are resolved from this script's own URL, so the book works wherever it
// is served from, including a GitHub Pages project path.

import { Lab } from "./wasm.js";
import { mountFooter, mountAnatomy } from "./footer.js";
import { mountLayouts } from "./layouts.js";
import { mountSchema } from "./schema.js";
import { mountLevels } from "./levels.js";
import { mountEncodings } from "./encodings.js";
import { mountPages } from "./pages.js";
import { mountCompression } from "./compression.js";

const EXPERIMENTS = {
  footer: mountFooter, anatomy: mountAnatomy, layouts: mountLayouts, schema: mountSchema, levels: mountLevels,
  encodings: mountEncodings, pages: mountPages, compression: mountCompression,
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

let labPromise = null;
function loadLab() {
  labPromise ||= Lab.fromUrl(new URL("parquet_lab.wasm", import.meta.url));
  return labPromise;
}

async function mount(el) {
  const config = { ...el.dataset };
  const run = EXPERIMENTS[config.experiment];
  el.innerHTML = '<p class="lab-loading">Loading the reader…</p>';
  try {
    const lab = await loadLab();
    const names = (config.fixtures || config.fixture || "").split(",").map((s) => s.trim()).filter(Boolean);
    const files = new Fixtures(names);
    el.innerHTML = "";
    await run(el, lab, files, config.fixture || names[0], config);
    el.dataset.ready = "true";
  } catch (error) {
    el.innerHTML = `<p class="lab-error">The experiment could not start: ${String(error.message || error)}</p>`;
    el.dataset.ready = "error";
    throw error;
  }
}

for (const el of document.querySelectorAll(".lab[data-experiment]")) mount(el);
