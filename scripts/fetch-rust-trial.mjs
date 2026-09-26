// Fetch the toolchain for the hidden Rust-in-the-browser trial page (web/rust-trial/) into the
// built site. It is too large to keep in git, so the deploy workflow fetches it, pinned and
// checked, at build time:
//
//     node scripts/fetch-rust-trial.mjs _build/html/rust-trial
//
// - rubrc's rustc, compiled to WebAssembly with threads (github.com/oligamiq/rubrc, MIT OR
//   Apache-2.0), gzipped, since the page decompresses it with the browser's own
//   DecompressionStream.
// - The wasm32-wasip1 standard library built by that same rustc (oligamiq/rust_wasm), repacked
//   from brotli to gzip for the same reason.
// - The WASI shims the page runs it with: @oligami/browser_wasi_shim-threads and
//   @bjorn3/browser_wasi_shim, from npm.
//
// Every download is checked against the hash it had when the trial was written, so the page
// cannot silently change under the numbers it reports.

import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { gzipSync, brotliDecompressSync, gunzipSync } from "node:zlib";
import { tmpdir } from "node:os";
import path from "node:path";

const out = process.argv[2];
if (!out) throw new Error("usage: node scripts/fetch-rust-trial.mjs OUT_DIR");

const RUBRC = "807ace9e9cf266b1b1004372abdefc2152785d69";
const FILES = [
  {
    url: `https://raw.githubusercontent.com/oligamiq/rubrc/${RUBRC}/crates/vfs/rustc_opt.wasm`,
    sha256: "c6dccf3e5f01631b942a0a008b9f2f5312987e7d8590f8c61024cd00687a5791",
    to: "rustc_opt.wasm.gz",
    convert: (b) => gzipSync(b, { level: 9 }),
  },
  {
    url: "https://oligamiq.github.io/rust_wasm/v0.2.0/wasm32-wasip1.tar.br",
    sha256: "5c579477e831574ce3fa6abddaa1b9c29543625cd961b298883b5bdeed4191cd",
    to: "wasm32-wasip1.tar.gz",
    convert: (b) => gzipSync(brotliDecompressSync(b), { level: 9 }),
  },
];
const PACKAGES = [
  {
    url: "https://registry.npmjs.org/@oligami/browser_wasi_shim-threads/-/browser_wasi_shim-threads-0.5.0.tgz",
    sha256: "97d638f5754f712dbbf2a3857c3d62969c53b5a0c2be2ffebc0ed4179e6e9125",
    take: ["dist/browser-wasi-shim-threads.es.js", "dist/worker_background_worker.min.js", "LICENSE-MIT", "LICENSE-APACHE"],
    to: "vendor/threads",
  },
  {
    url: "https://registry.npmjs.org/@bjorn3/browser_wasi_shim/-/browser_wasi_shim-0.4.2.tgz",
    sha256: "9c0281520d0e99f027ec7c1c79b4036c0f8168ed9bf98aba19db4737a1333782",
    take: ["dist/*.js", "LICENSE-MIT", "LICENSE-APACHE"],
    to: "vendor/wasi",
  },
];

// RUST_TRIAL_CACHE names a directory of files already downloaded, by their URL's last part,
// for machines that reach these hosts by other means. They are checked like any download.
async function download(url, sha256) {
  const cached = process.env.RUST_TRIAL_CACHE && path.join(process.env.RUST_TRIAL_CACHE, url.split("/").pop());
  let body;
  if (cached && existsSync(cached)) {
    body = readFileSync(cached);
  } else {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    body = Buffer.from(await r.arrayBuffer());
  }
  const got = createHash("sha256").update(body).digest("hex");
  if (got !== sha256) throw new Error(`${url}: sha256 ${got}, expected ${sha256}`);
  return body;
}

mkdirSync(out, { recursive: true });
for (const f of FILES) {
  const body = f.convert(await download(f.url, f.sha256));
  writeFileSync(path.join(out, f.to), body);
  console.log(`${f.to}: ${(body.length / 1e6).toFixed(1)} MB`);
}
for (const p of PACKAGES) {
  const dir = mkdtempSync(path.join(tmpdir(), "rust-trial-"));
  writeFileSync(path.join(dir, "p.tar"), gunzipSync(await download(p.url, p.sha256)));
  execFileSync("tar", ["-xf", "p.tar"], { cwd: dir });
  const to = path.join(out, p.to);
  mkdirSync(to, { recursive: true });
  for (const want of p.take) {
    const [sub, name] = want.includes("/") ? want.split("/") : ["", want];
    const from = path.join(dir, "package", sub);
    const names = name === "*.js"
      ? readdirSync(from).filter((n) => n.endsWith(".js"))
      : [name].filter((n) => { try { return statSync(path.join(from, n)).isFile(); } catch { return false; } });
    for (const n of names) copyFileSync(path.join(from, n), path.join(to, n));
  }
  console.log(`${p.to}: ${readdirSync(to).join(", ")}`);
}
// Not needed at run time, but keeps the source of every file in the directory next to it.
writeFileSync(path.join(out, "vendor", "SOURCES.txt"), [...FILES, ...PACKAGES].map((f) => `${f.url}\n  sha256 ${f.sha256}`).join("\n") + "\n");
