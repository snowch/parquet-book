// Run a program rustc compiled for wasm32-wasip1 (no threads), under the plain WASI shim, and
// report what it printed and how long it took.
import { Fd, File, OpenFile, PreopenDirectory, WASI } from "./vendor/wasi/index.js";

class Capture extends Fd {
  constructor(sink) {
    super();
    this.sink = sink;
  }
  fd_write(data) {
    this.sink.push(new TextDecoder().decode(data));
    return { ret: 0, nwritten: data.byteLength };
  }
}

onmessage = async ({ data }) => {
  const out = [];
  const t0 = performance.now();
  try {
    const module = await WebAssembly.compile(data.bytes);
    const fds = [new OpenFile(new File([])), new Capture(out), new Capture(out), new PreopenDirectory("/", new Map())];
    const wasi = new WASI(data.args, [], fds);
    const instance = await WebAssembly.instantiate(module, { wasi_snapshot_preview1: wasi.wasiImport });
    const t1 = performance.now();
    let code;
    try {
      code = wasi.start(instance);
    } catch (error) {
      code = `trapped: ${error.message}`;
    }
    postMessage({ code, output: out.join(""), compileMs: t1 - t0, ms: performance.now() - t1 });
  } catch (error) {
    postMessage({ code: "error", output: out.join("") + String(error), compileMs: 0, ms: performance.now() - t0 });
  }
};
