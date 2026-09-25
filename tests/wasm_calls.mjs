// Run a list of calls against the WebAssembly reader and print the results as JSON.
//
//     node tests/wasm_calls.mjs WASM CALLS_JSON
//
// tests/test_wasm.py makes the same calls natively, through `pqlab`, and requires the answers to
// be identical. This file is how the browser's half of that comparison runs without a browser:
// it loads web/lab/wasm.js, the loader the pages use, unchanged.

import { readFileSync } from "node:fs";
import { Lab } from "../web/lab/wasm.js";

const [wasmPath, callsPath] = process.argv.slice(2);
const lab = await Lab.fromBytes(readFileSync(wasmPath));
const calls = JSON.parse(readFileSync(callsPath, "utf8"));
const ids = new Map();
const id = (file) => {
  if (!ids.has(file)) ids.set(file, lab.load(file.split("/").pop(), readFileSync(file)));
  return ids.get(file);
};
const out = calls.map((c) => {
  switch (c.call) {
    case "footer": return lab.footerLab(id(c.file), c.options);
    case "structure": return lab.structure(id(c.file));
    case "interpret": return lab.interpret(id(c.file), c.offset);
    case "layouts": return lab.layouts(c.options);
    default: throw new Error(`unknown call ${c.call}`);
  }
});
process.stdout.write(JSON.stringify(out));
