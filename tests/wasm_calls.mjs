// Run a list of calls against the WebAssembly reader and print the results as JSON.
//
//     node tests/wasm_calls.mjs WASM CALLS_JSON
//
// tests/test_wasm.py makes the same calls natively, through `pqlab`, and requires the answers to
// be identical. This file is how the browser's half of that comparison runs without a browser:
// it loads web/lab/wasm.js, the loader the pages use, unchanged.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { Lab } from "../web/lab/wasm.js";

const [wasmPath, callsPath] = process.argv.slice(2);
const lab = await Lab.fromBytes(readFileSync(wasmPath));
const calls = JSON.parse(readFileSync(callsPath, "utf8"));
const ids = new Map();
const id = (file) => {
  if (!ids.has(file)) ids.set(file, lab.load(file.split("/").pop(), readFileSync(file)));
  return ids.get(file);
};
// For `pqlab` commands: every fixture, under the path a command names it by, as the page loads
// them for its Run buttons.
let everyFixture = false;
const loadEveryFixture = () => {
  if (everyFixture) return;
  const walk = (dir) => readdirSync(dir).forEach((n) => {
    const p = `${dir}/${n}`;
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(parquet|json)$/.test(n)) lab.load(p, readFileSync(p));
  });
  walk("fixtures");
  everyFixture = true;
};
const out = calls.map((c) => {
  switch (c.call) {
    case "footer": return lab.footerLab(id(c.file), c.options);
    case "structure": return lab.structure(id(c.file));
    case "schema": return lab.schema(id(c.file));
    case "levels": return lab.levels(id(c.file), c.column);
    case "encodings": return lab.encodings(id(c.file), c.column);
    case "pages": return lab.pages(id(c.file), c.column);
    case "table": return lab.table(c.keys.map((k) => { if (!ids.has(k)) ids.set(k, lab.load(k, readFileSync(`fixtures/${k}`))); return ids.get(k); }), c.sql, c.discovery, 4);
    case "changes": return lab.changes(c.keys.map((k) => { if (!ids.has(k)) ids.set(k, lab.load(k, readFileSync(`fixtures/${k}`))); return ids.get(k); }), c.snapshot, c.op, c.options);
    case "encryption": return lab.encryption(id(c.file));
    case "query": return lab.query(id(c.file), c.sql);
    case "scan": return lab.scan(id(c.file), c.columns, c.where, c.strategy);
    case "skipping": return lab.skipping(id(c.file), c.column, c.op, c.value, c.mechanisms);
    case "statistics": return lab.statistics(id(c.file), c.row_group, c.column);
    case "compression": return lab.compression(id(c.file), c.column, c.page ?? null);
    case "interpret": return lab.interpret(id(c.file), c.offset);
    case "layouts": return lab.layouts(c.options);
    case "cli": loadEveryFixture(); return lab.cli(c.args);
    default: throw new Error(`unknown call ${c.call}`);
  }
});
process.stdout.write(JSON.stringify(out));
