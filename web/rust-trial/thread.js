// One rustc thread: the shim sends the module, the shared memory and the thread's start argument.
import { thread_spawn_on_worker, wait_async_polyfill } from "./vendor/threads/browser-wasi-shim-threads.es.js";

wait_async_polyfill();

onmessage = async (event) => {
  await thread_spawn_on_worker(event.data);
};
