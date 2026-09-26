// The Rust-in-the-browser trial: compile and run Rust on this device, and time every step.
//
// Steps: download the standard library and the compiler, compile hello world and run it, then
// compile the book's whole Rust reader with its own unit tests (reader.rs, flattened from
// crates/parquet-lab by the site build) and run them. The numbers are what the page reports
// back, so a reader can say whether "Run" for Rust would be bearable on their device.

const $ = (id) => document.getElementById(id);
const secs = (ms) => (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);
const mb = (bytes) => `${(bytes / 1e6).toFixed(1)} MB`;

// Threads need SharedArrayBuffer, which needs cross-origin isolation, which the service worker
// gives this directory. The first visit registers it and reloads once.
async function isolate() {
  if (globalThis.crossOriginIsolated) return true;
  if (!("serviceWorker" in navigator)) return false;
  if (sessionStorage.getItem("rust-trial-reloaded")) return false;
  await navigator.serviceWorker.register(new URL("sw.js", import.meta.url), { scope: "./" });
  await navigator.serviceWorker.ready;
  sessionStorage.setItem("rust-trial-reloaded", "1");
  location.reload();
  return new Promise(() => {});
}

const env = [
  `cross-origin isolated: ${globalThis.crossOriginIsolated ? "yes" : "no"}`,
  `cores: ${navigator.hardwareConcurrency ?? "?"}`,
  navigator.deviceMemory ? `memory: ${navigator.deviceMemory} GB` : null,
  `Atomics.waitAsync: ${typeof Atomics.waitAsync === "function" ? "yes" : "no (polyfilled)"}`,
].filter(Boolean);

const results = [];
function step(label) {
  const tr = document.createElement("tr");
  tr.className = "running";
  tr.innerHTML = "<td></td><td>…</td>";
  tr.cells[0].textContent = label;
  $("steps").append(tr);
  const started = performance.now();
  const tick = setInterval(() => { tr.cells[1].textContent = `${secs(performance.now() - started)}…`; }, 250);
  return {
    done(value, ok = true) {
      clearInterval(tick);
      tr.className = ok ? "ok" : "failed";
      tr.cells[1].textContent = value;
      results.push(`${ok ? "" : "FAILED "}${label}: ${value}`);
    },
  };
}

function log(text) {
  $("log-box").hidden = false;
  $("log").textContent += `${text}\n`;
}

/** Send a message to a worker and wait for its first reply that `until` accepts. */
function ask(worker, message, until = () => true, transfer = []) {
  return new Promise((resolve, reject) => {
    const listener = ({ data }) => {
      if (data?.error) {
        worker.removeEventListener("message", listener);
        reject(new Error(data.error));
      } else if (until(data)) {
        worker.removeEventListener("message", listener);
        resolve(data);
      }
    };
    worker.addEventListener("message", listener);
    worker.onerror = (e) => reject(new Error(e.message || "worker failed"));
    worker.postMessage(message, transfer);
  });
}

const worker = (name) => new Worker(new URL(name, import.meta.url), { type: "module" });

async function rustc(farm, compiler, label, args) {
  const s = step(label);
  const r = await ask(compiler, { args }, (d) => d.done);
  const { stdout, stderr } = await ask(farm, { take: true }, (d) => "stdout" in d);
  if (stdout || stderr) log(`$ rustc ${args.join(" ")}\n${stdout}${stderr}`);
  s.done(r.code === 0 ? secs(r.ms) : `exit ${r.code} after ${secs(r.ms)}`, r.code === 0);
  return r.code === 0;
}

async function run(farm, file, label, args) {
  const s = step(label);
  const { bytes } = await ask(farm, { read: file }, (d) => d.file === file);
  if (!bytes) {
    s.done(`${file} was not written`, false);
    return null;
  }
  const r = await ask(worker("run.js"), { bytes, args }, (d) => "code" in d, [bytes.buffer]);
  log(`$ ${args.join(" ")}\n${r.output}`);
  s.done(r.code === 0 ? secs(r.ms) : `${r.code} after ${secs(r.ms)}`, r.code === 0);
  return r.output;
}

async function trial() {
  $("go").disabled = true;
  results.length = 0;
  $("steps").textContent = "";
  $("summary").hidden = true;
  const t0 = performance.now();
  try {
    if (!globalThis.crossOriginIsolated) throw new Error("this page is not cross-origin isolated, so threads are unavailable; reload it once");
    const sources = {};
    for (const name of ["hello.rs", "reader.rs"]) {
      const r = await fetch(new URL(name, import.meta.url));
      if (!r.ok) throw new Error(`${name}: ${r.status}`);
      sources[name] = await r.text();
    }
    const farm = worker("farm.js");
    const compiler = worker("rustc.js");

    let s = step("Download and unpack the standard library");
    const f = await ask(farm, { init: true, sources }, (d) => d.ready);
    s.done(`${secs(f.sysroot.ms)} (${mb(f.sysroot.compressed)} → ${mb(f.sysroot.bytes)})`);

    s = step("Download the compiler");
    const c = await ask(compiler, { init: true, refs: [f.ref] }, (d) => d.ready);
    s.done(`${secs(c.rustc.downloadMs)} (${mb(c.rustc.compressed)} → ${mb(c.rustc.bytes)})`);
    step("Compile the compiler (WebAssembly)").done(secs(c.rustc.compileMs));

    const base = ["--sysroot", "/sysroot", "--target", "wasm32-wasip1", "--edition", "2021"];
    if (await rustc(farm, compiler, "Compile hello world", ["/hello.rs", ...base, "-o", "/hello.wasm"])) {
      await run(farm, "hello.wasm", "Run hello world", ["hello"]);
    }
    const lines = sources["reader.rs"].split("\n").length;
    if (await rustc(farm, compiler, `Compile the reader and its unit tests (${lines} lines, opt-level 1)`,
      ["/reader.rs", ...base, "--test", "-Copt-level=1", "-o", "/reader.wasm"])) {
      const output = await run(farm, "reader.wasm", "Run the reader's unit tests", ["reader", "--test-threads=1"]);
      const verdict = output?.match(/test result: .*/)?.[0];
      if (verdict) {
        step("Unit tests").done(verdict.replace(/^test result: /, "").replace(/; 0 measured.*$/, ""), verdict.includes("ok."));
      }
    }
    step("Total").done(secs(performance.now() - t0));
  } catch (error) {
    step("Stopped").done(String(error.message || error), false);
    log(String(error.stack || error));
  }
  $("summary").textContent = [`Rust trial, ${new Date().toISOString().slice(0, 16)}`, navigator.userAgent, env.join(", "), "", ...results].join("\n");
  $("summary").hidden = false;
  $("copy").hidden = false;
  $("go").disabled = false;
}

$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("summary").textContent);
    $("copy").textContent = "Copied";
  } catch {
    getSelection().selectAllChildren($("summary"));
  }
});
$("go").addEventListener("click", trial);

if (await isolate()) {
  env[0] = "cross-origin isolated: yes";
} else {
  $("go").disabled = true;
  step("Cross-origin isolation").done("unavailable in this browser, so threads cannot run", false);
}
$("env").textContent = env.join(" · ");
