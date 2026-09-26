// rubrc's rustc: fetched, decompressed and compiled once; each run gets a fresh WASIFarmAnimal,
// so a fresh shared memory (a second run on the first run's memory would find its statics
// already initialised). The rustc main thread and every thread it spawns run in thread.js
// workers; this worker blocks while they do.

import { WASIFarmAnimal, wait_async_polyfill } from "./vendor/threads/browser-wasi-shim-threads.es.js";

wait_async_polyfill();

let module;
let refs;

onmessage = async ({ data }) => {
  try {
    if (data.init) {
      refs = data.refs;
      const t0 = performance.now();
      const r = await fetch(new URL("rustc_opt.wasm.gz", import.meta.url));
      if (!r.ok) throw new Error(`rustc_opt.wasm.gz: ${r.status}`);
      const compressed = Number(r.headers.get("content-length")) || 0;
      const bytes = await new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
      const t1 = performance.now();
      module = await WebAssembly.compile(bytes);
      const t2 = performance.now();
      postMessage({ ready: true, rustc: { compressed, bytes: bytes.byteLength, downloadMs: t1 - t0, compileMs: t2 - t1 } });
    } else if (data.args) {
      const t0 = performance.now();
      const animal = new WASIFarmAnimal(refs, ["rustc", ...data.args], ["RUST_MIN_STACK=16777216"], {
        can_thread_spawn: true,
        thread_spawn_worker_url: new URL("./thread.js", import.meta.url).href,
        thread_spawn_wasm: module,
      });
      await animal.wait_worker_background_worker();
      // rustc asks for at least 399 pages of memory; the shim starts with 256.
      animal.get_share_memory().memory.grow(200);
      const t1 = performance.now();
      const code = animal.block_start_on_thread();
      const t2 = performance.now();
      postMessage({ done: true, code, setupMs: t1 - t0, ms: t2 - t1 });
    }
  } catch (error) {
    postMessage({ error: String(error?.stack || error) });
  }
};
