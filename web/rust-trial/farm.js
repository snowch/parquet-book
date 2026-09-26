// The trial's filesystem: a WASIFarm, which every rustc thread reads and writes through, so the
// threads see one filesystem as they would on a desk.
//
//   /sysroot   rubrc's wasm32-wasip1 standard library, from wasm32-wasip1.tar.gz
//   /          the sources (hello.rs, reader.rs) and whatever rustc writes (-o /x.wasm)
//   /tmp       rustc's temporary files
//
// It stays responsive (the farm answers the other workers' requests from this thread's event
// loop), and answers the page: {read: "x.wasm"} returns a file, {take: true} what was printed.

import { Directory, Fd, File, OpenFile, PreopenDirectory } from "./vendor/wasi/index.js";
import { WASIFarm, wait_async_polyfill } from "./vendor/threads/browser-wasi-shim-threads.es.js";

wait_async_polyfill();

class Capture extends Fd {
  constructor() {
    super();
    this.chunks = [];
  }
  fd_write(data) {
    this.chunks.push(data.slice());
    return { ret: 0, nwritten: data.byteLength };
  }
  take() {
    const all = new Uint8Array(this.chunks.reduce((n, c) => n + c.length, 0));
    let at = 0;
    for (const c of this.chunks) {
      all.set(c, at);
      at += c.length;
    }
    this.chunks = [];
    return new TextDecoder().decode(all);
  }
}

/** Files in a POSIX tar: 512-byte headers, each followed by its data padded to 512 bytes. */
function untar(tar) {
  const files = new Map();
  const text = (a, b) => new TextDecoder().decode(tar.subarray(a, b)).replace(/\0.*$/s, "");
  for (let at = 0; at + 512 <= tar.length;) {
    const name = text(at, at + 100);
    if (!name) break;
    const size = parseInt(text(at + 124, at + 136).trim() || "0", 8);
    const type = String.fromCharCode(tar[at + 156]);
    const prefix = text(at + 345, at + 500);
    if (type === "0" || type === "\0") files.set((prefix ? `${prefix}/` : "") + name, tar.slice(at + 512, at + 512 + size));
    at += 512 + Math.ceil(size / 512) * 512;
  }
  return files;
}

/** A directory tree from paths: "self-contained/libc.a" becomes nested Directory objects. */
function tree(files) {
  const root = new Map();
  for (const [path, data] of files) {
    const parts = path.split("/").filter(Boolean);
    let dir = root;
    for (const part of parts.slice(0, -1)) {
      if (!dir.has(part)) dir.set(part, new Directory(new Map()));
      dir = dir.get(part).contents;
    }
    dir.set(parts.at(-1), new File(data));
  }
  return root;
}

let root;
const stdout = new Capture();
const stderr = new Capture();

onmessage = async ({ data }) => {
  if (data.init) {
    const t0 = performance.now();
    const r = await fetch(new URL("wasm32-wasip1.tar.gz", import.meta.url));
    if (!r.ok) throw new Error(`wasm32-wasip1.tar.gz: ${r.status}`);
    const compressed = Number(r.headers.get("content-length")) || 0;
    const tar = new Uint8Array(await new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer());
    const libs = untar(tar);
    const t1 = performance.now();
    const sysroot = new PreopenDirectory("/sysroot", new Map([["lib", new Directory(new Map([["rustlib", new Directory(new Map([
      ["wasm32-wasip1", new Directory(new Map([["lib", new Directory(tree(libs))]]))],
    ]))]]))]]));
    root = new PreopenDirectory("/", new Map(Object.entries(data.sources).map(([n, t]) => [n, new File(new TextEncoder().encode(t))])));
    const farm = new WASIFarm(new OpenFile(new File(new Uint8Array())), stdout, stderr, [sysroot, new PreopenDirectory("/tmp", new Map()), root],
      { allocator_size: 256 * 1024 * 1024 });
    postMessage({ ready: true, ref: await farm.get_ref(), sysroot: { compressed, bytes: tar.length, files: libs.size, ms: t1 - t0 } });
  } else if (data.read) {
    const entry = root.dir.contents.get(data.read);
    const bytes = entry ? entry.data.slice() : null;
    postMessage({ file: data.read, bytes }, bytes ? [bytes.buffer] : []);
  } else if (data.take) {
    postMessage({ stdout: stdout.take(), stderr: stderr.take() });
  }
};
