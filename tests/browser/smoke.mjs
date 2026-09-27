// Drive the built book in a headless browser and check that the experiments are views of the
// reader, not pictures of one.
//
//     node tests/browser/smoke.mjs _build/html [--screenshots DIR]
//
// It serves the site from a local HTTP server, opens the chapters, and compares what the page
// shows with what the Rust reader computes natively (`cargo run -p pqlab -- footer … --json`).
// The browser and the command line must agree to the byte, because they run the same code.

import { createServer } from "node:http";
import { readFile, readdir, stat, mkdir } from "node:fs/promises";
import { execFileSync, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";

const root = path.resolve(process.argv[2] || "_build/html");
const shotsAt = process.argv.indexOf("--screenshots");
const shots = shotsAt > 0 ? process.argv[shotsAt + 1] : null;

// Playwright from the project, or from the global install if the project has none.
function loadPlaywright() {
  const here = createRequire(import.meta.url);
  try {
    return here("playwright");
  } catch {
    const globalRoot = execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim();
    return createRequire(path.join(globalRoot, "noop.js"))("playwright");
  }
}
const { chromium } = loadPlaywright();

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".wasm": "application/wasm", ".svg": "image/svg+xml", ".parquet": "application/octet-stream" };

const server = createServer(async (req, res) => {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (p.endsWith("/")) p += "index.html";
  const file = path.join(root, p);
  try {
    if (!file.startsWith(root) || !(await stat(file)).isFile()) throw new Error("no");
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    res.end(await readFile(file));
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}/`;

const native = (args) => JSON.parse(execFileSync("cargo",
  ["run", "--quiet", "-p", "pqlab", "--", ...args], { encoding: "utf8" }));

let failures = 0;
const check = (ok, what) => {
  console.log(`${ok ? "  ok  " : "  FAIL"} ${what}`);
  if (!ok) failures += 1;
};

const launch = { headless: true };
if (process.env.PLAYWRIGHT_BROWSERS_PATH === undefined) {
  // Nothing to do: Playwright finds its own browsers.
}
const browser = await chromium.launch(launch);
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
// Pyodide, for the labs' Python engine, comes from a public CDN. Fetch it through Node, which
// trusts the same certificates as the rest of the toolchain (a proxy's included), and hand
// Chromium the bytes: they are the same bytes either way.
// Each file is fetched once per run and kept, and a failed fetch is tried again: a CI runner's
// connection to the CDN sometimes times out, and that is not something the book can fix.
const cdn = new Map();
async function fromCdn(url) {
  for (let attempt = 1; ; attempt++) {
    try {
      const r = await fetch(url);
      return { status: r.status, type: r.headers.get("content-type") || "application/octet-stream",
        body: Buffer.from(await r.arrayBuffer()) };
    } catch (error) {
      if (attempt === 4) throw error;
      await new Promise((r) => setTimeout(r, 2000 * 2 ** (attempt - 1)));
    }
  }
}
await page.context().route("https://cdn.jsdelivr.net/**", async (route) => {
  const url = route.request().url();
  if (!cdn.has(url)) cdn.set(url, fromCdn(url));
  try {
    const r = await cdn.get(url);
    await route.fulfill({ status: r.status, headers: { "content-type": r.type, "access-control-allow-origin": "*" },
      body: r.body });
  } catch (error) {
    cdn.delete(url);
    console.log(`  (the CDN did not answer for ${url}: ${error.cause?.code || error.message})`);
    await route.abort();
  }
});
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
if (shots) await mkdir(shots, { recursive: true });

// ch02: the whole file, as the reader parsed it, with the bytes it never asked for dimmed.
await page.goto(base + "anatomy-of-a-parquet-file.html");
const expected = native(["footer", "fixtures/tiny.parquet", "--json"]);
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="anatomy"]')?.dataset.state === "ok");
const whole = page.locator('.lab[data-experiment="anatomy"]');
check(await whole.getAttribute("data-footer-length") === String(expected.trailer.footer_length),
  `the byte map's reader finds the footer length the native reader does (${expected.trailer.footer_length})`);
const dim = await whole.locator(".hex .b.unfetched").count();
check(dim === expected.file_size - expected.totals.bytes_returned,
  `${dim} bytes dimmed: the ones the reader never asked for when it opened the file`);
// Damage the closing magic: the reader refuses the file, and nothing is dimmed; restore it.
await whole.locator(`.hex .b[data-o="${expected.file_size - 1}"]`).click();
await whole.locator('.inspector input[name="byte"]').fill("32");
await whole.locator(".inspector form.edit button[type=submit]").click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="anatomy"]').dataset.state === "error");
check(await whole.locator(".hex .b.unfetched").count() === 0, "a damaged file dims nothing: the reader refused it");
await whole.locator(".inspector .restore").click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="anatomy"]').dataset.state === "ok");

// The anatomy panel maps the whole file.
const anatomy = page.locator('.lab[data-experiment="anatomy"]');
await anatomy.locator(".tree .node-row").first().waitFor();
const labels = await anatomy.locator(".tree ul.root > li > ul > li > .node-row .node-label").allInnerTexts();
check(JSON.stringify(labels) === JSON.stringify(["Header", "Row group 0", "Footer", "Trailer"]),
  `anatomy regions: ${labels.join(", ")}`);
if (shots) {
  await anatomy.locator(".hex .b[data-o=\"20\"]").click();
  await anatomy.screenshot({ path: path.join(shots, "anatomy-lab.png") });
}

// The code tabs: Python first, one choice for every excerpt, remembered across pages. (ch01 is
// an introduction and quotes no reader code, so this starts on ch03.)
await page.goto(base + "the-type-system.html");
check(await page.evaluate(() => document.documentElement.dataset.code) === "python", "code is shown in Python by default");
const visible = () => page.locator(".tab-panel").evaluateAll((els) =>
  els.filter((e) => e.offsetParent !== null).map((e) => e.dataset.code));
check((await visible()).every((c) => c === "python") && (await visible()).length > 0, "only the Python excerpts are visible");
await page.locator('.tab-bar button[data-code="rust"]').first().click();
check((await visible()).every((c) => c === "rust"), "one click shows every excerpt in Rust");
await page.goto(base + "anatomy-of-a-parquet-file.html");
check(await page.evaluate(() => document.documentElement.dataset.code) === "rust", "and the choice holds on the next page");
await page.locator('.tab-bar button[data-code="python"]').first().click();

// The same labs on the Python engine: the book's Python reader, run by Pyodide, must show what
// the Rust reader computes natively.
const pyAnatomy = page.locator('.lab[data-experiment="anatomy"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="anatomy"]')?.dataset.state === "ok");
await pyAnatomy.locator('.engine-bar button[data-engine="python"]').click();
await page.waitForFunction(() => {
  const el = document.querySelector('.lab[data-experiment="anatomy"]');
  return el.dataset.engine === "python" && el.dataset.state === "ok";
}, null, { timeout: 180000 });
await pyAnatomy.locator(".tree .node-row").first().waitFor();
const pyLabels = await pyAnatomy.locator(".tree ul.root > li > ul > li > .node-row .node-label").allInnerTexts();
check(JSON.stringify(pyLabels) === JSON.stringify(labels) &&
  await pyAnatomy.getAttribute("data-footer-length") === String(expected.trailer.footer_length) &&
  await pyAnatomy.locator(".hex .b.unfetched").count() === dim,
  "on the Python engine, the byte map shows the same regions, footer length and unfetched bytes");
await page.goto(base + "compression.html");
await page.waitForFunction(() => {
  const el = document.querySelector('.lab[data-experiment="compression"]');
  return el?.dataset.engine === "python" && el.dataset.ready === "true";
}, null, { timeout: 180000 });
check(true, "the engine choice holds on another page");
await page.locator('.lab[data-experiment="compression"] .engine-bar button[data-engine="rust"]').click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="compression"]').dataset.engine === "rust");
// ch01 is an introduction, with code and no panels.
await page.goto(base + "why-parquet-exists.html");
check(await page.locator(".lab").count() === 0, "ch01 has no panels: its pictures come from code");
{
  // ch01 opens on code: the CSV file read a row at a time, in the page, reads every byte.
  const step = page.locator('figure.walkthrough[data-file$="read_a_csv.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  const box = step.locator(".runnable");
  await box.and(page.locator('[data-state="running"]')).waitFor({ timeout: 10000 }).catch(() => {});
  await box.and(page.locator('[data-state="idle"]')).waitFor({ timeout: 300000 });
  const out = await step.locator(".run-output").innerText();
  const csvSize = (await stat("fixtures/formats/orders.csv")).size;
  check(out.includes(`read ${csvSize} of ${csvSize} bytes`), `ch01's CSV step runs in the page and reads all ${csvSize} bytes`);
  // And the two layouts, drawn by code: the query's two columns are one run when stored by columns.
  const layouts = page.locator('figure.walkthrough[data-file$="two_layouts.py"]');
  await layouts.locator(".run-button:not(.edit-button)").click();
  await layouts.locator(".run-output").filter({ hasText: "by columns" }).waitFor({ timeout: 60000 });
  const drawn = await layouts.locator(".run-output").innerText();
  check(/^by rows, 8 runs:\n[.#]+$/m.test(drawn) && /^by columns, 1 run:\n[.#]+$/m.test(drawn), "ch01's layouts step draws both layouts in the page");
}
await page.evaluate(() => localStorage.setItem("lab-engine", "rust"));
if (shots) {
  await page.goto(base + "anatomy-of-a-parquet-file.html");
  await page.screenshot({ path: path.join(shots, "chapter.png") });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.screenshot({ path: path.join(shots, "chapter-dark.png") });
}

// ch03: the schema, rebuilt by hand in the page. The walk's levels and the count of columns the
// book's reader finds are the native reader's.
{
  await page.goto(base + "the-type-system.html");
  check(await page.locator(".lab").count() === 0, "ch03 has no panels: its steps print the schema");
  const nativeSchema = native(["schema", "fixtures/types.parquet"]);
  const step = page.locator('figure.walkthrough[data-file$="rebuild_the_tree.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  await step.locator(".run-output").filter({ hasText: "columns" }).waitFor({ timeout: 300000 });
  const out = await step.locator(".run-output").innerText();
  const city = nativeSchema.leaves.find((l) => l.path === "shipping.city");
  check(out.includes(`finds ${nativeSchema.leaves.length} columns`) &&
    out.includes(`city  max levels: definition ${city.max_definition_level}, repetition ${city.max_repetition_level}`),
    `ch03's tree is rebuilt in the page: ${nativeSchema.leaves.length} columns, shipping.city's levels as the reader counts them`);
}

// ch04: the levels of tags[], read by the book's Python reader in the page. The triples and the
// records it prints are the native reader's.
{
  await page.goto(base + "nested-data.html");
  check(await page.locator(".lab").count() === 0, "ch04 has no panels: its steps print the levels");
  const nativeLevels = native(["levels", "fixtures/nested.parquet", "2"]);
  const step = page.locator('figure.walkthrough[data-file$="levels_of_a_column.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  await step.locator(".run-output").filter({ hasText: "r d value" }).waitFor({ timeout: 300000 });
  const out = await step.locator(".run-output").innerText();
  const rows = nativeLevels.triples.map((t) => `${t.rep} ${t.def} ${JSON.stringify(t.value)}`);
  const flat = out.replace(/\s/g, "");
  check(rows.every((row) => out.split("\n").includes(row)) &&
    nativeLevels.records.every((r) => flat.includes(JSON.stringify(r))),
    `ch04's tags[] levels are read in the page: ${rows.length} triples and ${nativeLevels.records.length} records, as the reader reads them`);
}

// ch05: url's DELTA_BYTE_ARRAY page, decoded by the book's Python reader in the page. Every step
// it prints, and the values, are the native reader's.
{
  await page.goto(base + "encodings.html");
  check(await page.locator(".lab").count() === 0, "ch05 has no panels: its steps print the decoding");
  const nativeUrl = native(["encodings", "fixtures/encodings.parquet", "3"]);
  const step = page.locator('figure.walkthrough[data-file$="decode_a_column.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  await step.locator(".run-output").filter({ hasText: "values:" }).waitFor({ timeout: 300000 });
  const out = await step.locator(".run-output").innerText();
  const steps = nativeUrl.pages.flatMap((p) => p.steps);
  const lines = out.split("\n").map((l) => l.trim());
  check(steps.every((s) => lines.some((l) => l.startsWith(`${s.label}:`)) && lines.includes(s.detail)) &&
    nativeUrl.values.slice(0, 4).every((v) => out.includes(JSON.stringify(v.value))),
    `ch05's url column is decoded in the page: ${steps.length} steps and its values, as the reader decodes them`);
}

// ch06: pages. The book's Python reader walks country's pages in the page, and after one bit of
// the last page's body is flipped, only that page's checksum fails, as the native reader finds.
{
  await page.goto(base + "pages.html");
  check(await page.locator(".lab").count() === 0, "ch06 has no panels: its steps walk the pages");
  const nativePages = native(["pages", "fixtures/pages-v2.parquet", "1"]);
  const step = page.locator('figure.walkthrough[data-file$="damage_a_page.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  await step.locator(".run-output").filter({ hasText: "the reader's walk:" }).waitFor({ timeout: 300000 });
  const out = await step.locator(".run-output").innerText();
  const walked = nativePages.pages.map((p, i) => (i === nativePages.pages.length - 1 ? "False" : "True"));
  check(nativePages.pages.every((p) => p.crc_ok === true) && out.includes(`the reader's walk: [${walked.join(", ")}]`) &&
    out.includes("matches the header: True") && out.includes("matches the header: False"),
    `ch06's damaged page is found in the page: the last of ${nativePages.pages.length} checksums fails`);
}

// ch07: compression. The tokens and the rebuilt page are the Rust decompressor's.
await page.goto(base + "compression.html");
const compLab = page.locator('.lab[data-experiment="compression"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="compression"]')?.dataset.state === "ok");
const snappy = native(["compression", "fixtures/codec-snappy.parquet", "1"]);
check(await compLab.getAttribute("data-tokens") === String(snappy.decompressed.tokens.length),
  `country's Snappy page decompresses in the reader's ${snappy.decompressed.tokens.length} tokens`);
check(await compLab.getAttribute("data-decompressed") === String(snappy.pages[snappy.page].uncompressed_page_size),
  "the decompressed page is as long as its header says");
await compLab.locator('button[data-step="1"]').click();
await compLab.locator('button[data-step="1"]').click();
await compLab.locator('button[data-step="1"]').click();
const copy = snappy.decompressed.tokens[2];
check(await compLab.locator(".out-bytes i.out").count() === 2 * (copy.output[1] - copy.output[0]),
  "stepping to the first copy marks the bytes it wrote");
check(await compLab.locator(".out-bytes i.src").count() === 2 * (copy.output[1] - copy.output[0]),
  "and outlines the earlier bytes it copied");
await compLab.locator(".lab-head select").selectOption("codec-zstd.parquet");
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="compression"]').dataset.decompressed === "none");
check((await compLab.locator(".out-bytes").innerText()).includes("does not decompress ZSTD"),
  "a ZSTD page is reported as one the reader cannot decompress");
if (shots) {
  await compLab.locator(".lab-head select").selectOption("codec-snappy.parquet");
  await page.waitForFunction(() => document.querySelector('.lab[data-experiment="compression"]').dataset.codec === "SNAPPY");
  await compLab.screenshot({ path: path.join(shots, "compression-lab.png") });
}

// ch08: statistics. The book's Python reader decides in the page which bounds it may use for
// every column chunk, and each range it prints, or refuses, is the native reader's.
{
  await page.goto(base + "metadata-and-statistics.html");
  check(await page.locator(".lab").count() === 0, "ch08 has no panels: its steps print the bounds");
  const nativeStats = native(["statistics", "fixtures/statistics.parquet", "0", "0"]);
  const step = page.locator('figure.walkthrough[data-file$="the_reader_decides.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  const last = nativeStats.columns.at(-1);
  await step.locator(".run-output").filter({ hasText: `${last.path}, compared as` }).waitFor({ timeout: 300000 });
  const lines = (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  const chunks = nativeStats.columns.flatMap((c) => c.chunks);
  const printed = (c) => c.usable
    ? lines.includes(`row group ${c.row_group}: ${c.min} to ${c.max}, from ${c.source}`)
    : lines.some((l) => l.startsWith(`row group ${c.row_group}: refused`) || l === `row group ${c.row_group}: no statistics`);
  check(nativeStats.columns.every((c) => lines.includes(`${c.path}, compared as ${c.comparator}:`)) &&
    chunks.every(printed) && chunks.some((c) => c.usable) && chunks.some((c) => !c.usable),
    `ch08's bounds are decided in the page: ${chunks.filter((c) => c.usable).length} of ${chunks.length} chunks usable, as the reader decides`);
}

// ch09: skipping. The book's Python reader plans `order_id = 431` in the page, and every row
// group's verdict, its kept rows and the bytes it reads are the native reader's. The library step
// runs pyarrow's dataset module in the page, and keeps the row groups the statistics keep.
{
  await page.goto(base + "skipping-data.html");
  check(await page.locator(".lab").count() === 0, "ch09 has no panels: its steps print the plans");
  const runStep = async (name, until) => {
    const step = page.locator(`figure.walkthrough[data-file$="${name}.py"]`);
    await step.locator(".run-button:not(.edit-button)").click();
    await step.locator(".run-output").filter({ hasText: until }).waitFor({ timeout: 300000 });
    return (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  };
  const plan = native(["skipping", "fixtures/pruning-sorted.parquet", "0", "=", "431"]);
  const lines = await runStep("plan_a_read", "to decide");
  const verdict = (g) => g.skipped
    ? `row group ${g.index}: skip`
    : `row group ${g.index}: read rows [${g.rows.map(([a, b]) => `(${a}, ${b})`).join(", ")}]`;
  check(plan.row_groups.every((g) => lines.includes(verdict(g))) &&
    lines.includes(`${plan.totals.bytes_read} bytes of column chunks, ${plan.totals.index_bytes} to decide`),
    `ch09's plan is made in the page: ${plan.row_groups.filter((g) => g.skipped).length} row groups skipped and ${plan.totals.bytes_read} bytes read, as the reader plans`);
  const byStatistics = native(["skipping", "fixtures/pruning-sorted.parquet", "0", "=", "431", "--use", "statistics"]);
  const kept = byStatistics.row_groups.filter((g) => !g.skipped).map((g) => g.index);
  const library = await runStep("skipping_with_a_library", "an offset index");
  check(library.includes(`order_id = 431: kept row groups [${kept.join(", ")}]`),
    `pyarrow's dataset module runs in the page and keeps row groups [${kept}], as the reader's statistics do`);
}

// ch10: the read path. Requests and times are the reader's and the simulated store's.
await page.goto(base + "how-readers-read.html");
const scanLab = page.locator('.lab[data-experiment="scan"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="scan"]')?.dataset.state === "ok");
const scan1 = native(["scan", "fixtures/pruning-sorted.parquet", "--where", "0", "=", "431", "--size", "head", "--prefetch", "8"]);
check(await scanLab.getAttribute("data-requests") === String(scan1.totals.requests) &&
  await scanLab.getAttribute("data-elapsed") === String(scan1.totals.elapsed_us),
  `order_id = 431 takes the reader's ${scan1.totals.requests} requests and ${scan1.totals.elapsed_us / 1000} ms`);
check(await scanLab.getAttribute("data-matching") === "1", "and returns one row");
await scanLab.locator('select[name="connections"]').selectOption("4");
const scan4 = native(["scan", "fixtures/pruning-sorted.parquet", "--where", "0", "=", "431", "--size", "head", "--prefetch", "8", "--connections", "4"]);
await page.waitForFunction((t) => document.querySelector('.lab[data-experiment="scan"]').dataset.elapsed === String(t), scan4.totals.elapsed_us);
check(true, `four connections: ${scan4.totals.elapsed_us / 1000} ms`);
check(await scanLab.locator(".timeline .lane").count() === 4, "the timeline has a lane per connection");
if (shots) await scanLab.screenshot({ path: path.join(shots, "scan-lab.png") });

// ch11: writer settings. Every file's cost is the reader's.
await page.goto(base + "writing-parquet-well.html");
const writeLab = page.locator('.lab[data-experiment="writing"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="writing"]')?.dataset.state === "ok", null, { timeout: 60000 });
const baseline = native(["scan", "fixtures/writing-baseline.parquet", "--where", "0", "=", "431", "--size", "head", "--prefetch", "8", "--gap", "0"]);
check((await writeLab.getAttribute("data-bytes")).split(",")[0] === String(baseline.totals.bytes_after_footer),
  `order_id = 431 reads the reader's ${baseline.totals.bytes_after_footer} bytes after the footer of the baseline`);
check((await writeLab.getAttribute("data-bytes")).split(",").length === 7, "and the query runs against all seven files");
if (shots) await writeLab.screenshot({ path: path.join(shots, "writing-lab.png") });

// ch12: the query engine. The answer is the engine's.
await page.goto(base + "a-tiny-query-engine.html");
const engineLab = page.locator('.lab[data-experiment="engine"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="engine"]')?.dataset.state === "ok");
const byCountry = native(["query", "fixtures/writing-baseline.parquet", "SELECT country, count(*) FROM orders GROUP BY country ORDER BY country"]);
check(await engineLab.getAttribute("data-answer") === JSON.stringify(byCountry.rows), "the first example answers as the engine does natively");
await engineLab.locator('textarea[name="sql"]').fill("SELECT order_id FROM orders WHERE order_id >= 431 AND order_id < 434");
await engineLab.locator('button[type="submit"]').click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="engine"]').dataset.rows === "3");
check(await engineLab.locator(".pipeline li").count() === 3, "a filtered projection has three stages: scan, filter, project");
await engineLab.locator('textarea[name="sql"]').fill("SELECT FROM");
await engineLab.locator('button[type="submit"]').click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="engine"]').dataset.state === "error");
check(true, "a malformed query is reported, not guessed at");
if (shots) {
  await engineLab.locator('button[data-example="1"]').click();
  await engineLab.screenshot({ path: path.join(shots, "engine-lab.png") });
}

// ch13: encryption. What is visible is what the reader could read.
await page.goto(base + "modular-encryption.html");
const cryptLab = page.locator('.lab[data-experiment="encryption"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="encryption"]')?.dataset.state === "ok");
const plain = native(["encryption", "fixtures/plaintext-footer.parquet"]);
check(await cryptLab.getAttribute("data-mode") === "plaintext footer" &&
  await cryptLab.getAttribute("data-hidden") === String(plain.hidden.length),
  `a plaintext footer hides the reader's ${plain.hidden.length} items`);
await cryptLab.locator(".lab-head select").selectOption("encrypted-footer.parquet");
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="encryption"]').dataset.mode === "encrypted footer");
check((await cryptLab.locator(".p-tree").innerText()).includes("Encrypted FileMetaData"), "the structure view shows the encrypted footer as one module");
if (shots) await cryptLab.screenshot({ path: path.join(shots, "encryption-lab.png") });

// ch14: a table of files. What is read is what the reader's plan kept.
await page.goto(base + "lakehouse-and-beyond.html");
const tableLab = page.locator('.lab[data-experiment="table"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="table"]')?.dataset.state === "ok", null, { timeout: 60000 });
const ukSql = "SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200";
const byLog = native(["table", "fixtures/table.json", ukSql, "--discovery", "log"]);
check(await tableLab.getAttribute("data-files-read") === String(byLog.totals.files_read) &&
  await tableLab.getAttribute("data-answer") === JSON.stringify(byLog.rows),
  `reading the log, the reader reads ${byLog.totals.files_read} of ${byLog.totals.files} files and answers ${JSON.stringify(byLog.rows)}`);
await tableLab.locator('input[name="discovery"][value="list"]').check();
const byList = native(["table", "fixtures/table.json", ukSql, "--discovery", "list"]);
await page.waitForFunction((n) => document.querySelector('.lab[data-experiment="table"]').dataset.filesRead === String(n), byList.totals.files_read);
check(await tableLab.getAttribute("data-answer") === JSON.stringify(byLog.rows),
  `listing, it reads all ${byList.totals.files_read} files and answers the same`);
if (shots) await tableLab.screenshot({ path: path.join(shots, "table-lab.png") });

// ch15: a changing table. A lookup's chain of requests is the native reader's, and a scan of
// every snapshot counts the rows the native reader counts.
await page.goto(base + "changing-a-table.html");
const changesLab = page.locator('.lab[data-experiment="changes"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="changes"]')?.dataset.state === "ok", null, { timeout: 60000 });
const lookup = native(["changes", "fixtures/changes.json", "--snapshot", "after-a-day", "--lookup", "300"]);
check(await changesLab.getAttribute("data-requests") === String(lookup.totals.requests) &&
  await changesLab.getAttribute("data-round-trips") === String(lookup.totals.round_trips) &&
  await changesLab.getAttribute("data-answer") === "found",
  `finding order 300 takes ${lookup.totals.requests} requests in ${lookup.totals.round_trips} round trips, as the native reader's lookup does`);
await changesLab.locator('input[name="op"][value="scan"]').check();
await changesLab.locator('select[name="snapshot"]').selectOption("merge-on-read-8");
const mor = native(["changes", "fixtures/changes.json", "--snapshot", "merge-on-read-8"]);
await page.waitForFunction((n) => document.querySelector('.lab[data-experiment="changes"]').dataset.answer === String(n), mor.answer.live_rows);
check(await changesLab.getAttribute("data-requests") === String(mor.totals.requests),
  `a scan of merge-on-read-8 applies its delete files: ${mor.answer.live_rows} rows in ${mor.totals.requests} requests`);
if (shots) await changesLab.screenshot({ path: path.join(shots, "changes-lab.png") });

// Every lab the Python engine can run shows the same numbers on both engines: the data
// attributes each experiment writes, on every page where it appears.
{
  const { experiments } = JSON.parse(await readFile(path.join(root, "lab", "py", "package.json"), "utf8"));
  const pages = [];
  for (const f of (await readdir(root)).filter((n) => n.endsWith(".html")).sort()) {
    const html = await readFile(path.join(root, f), "utf8");
    const used = [...html.matchAll(/data-experiment="([a-z]+)"/g)].map((m) => m[1]);
    if (used.some((e) => experiments.includes(e))) pages.push(f);
  }
  const settled = async (engine) => {
    await page.evaluate((e) => localStorage.setItem("lab-engine", e), engine);
    await page.reload();
    await page.waitForFunction(() => [...document.querySelectorAll(".lab[data-experiment]")]
      .every((el) => el.dataset.ready === "true" || el.dataset.ready === "error"), null, { timeout: 180000 });
    await page.waitForTimeout(1500);
    return page.evaluate(() => [...document.querySelectorAll(".lab[data-experiment]")].map((el) => {
      const d = { ...el.dataset };
      delete d.engine;
      return d;
    }));
  };
  for (const f of pages) {
    await page.goto(base + f);
    const rust = await settled("rust");
    const python = await settled("python");
    for (const [i, r] of rust.entries()) {
      if (!experiments.includes(r.experiment)) continue;
      check(JSON.stringify(python[i]) === JSON.stringify(r),
        `${f}: the ${r.experiment} lab shows the same on the Python engine${JSON.stringify(python[i]) === JSON.stringify(r) ? "" : `: ${JSON.stringify(python[i])} vs ${JSON.stringify(r)}`}`);
    }
  }
  await page.evaluate(() => localStorage.setItem("lab-engine", "rust"));
}

// The problems workbench: pytest, run in the page under Pyodide on the stub as it ships, must
// report what it reports at a desk. The stub is unsolved, so the problems fail and the
// scaffolding passes, in the page as natively.
{
  const desk = spawnSync("python3", ["-m", "pytest", "exercises/python/tests/test_compression.py", "--problems",
    "-q", "-p", "no:cacheprovider"], { encoding: "utf8" }).stdout;
  const count = (word) => Number((desk.match(new RegExp(`(\\d+) ${word}`)) || [0, 0])[1]);
  await page.goto(base + "compression.html");
  const wb = page.locator('.workbench[data-chapter="compression"]');
  await wb.and(page.locator('[data-ready="true"]')).waitFor({ timeout: 30000 });
  await wb.locator('button[data-act="run"]').click();
  await wb.and(page.locator('[data-state="idle"]')).waitFor({ timeout: 300000 });
  const outcomes = await wb.locator(".results li").evaluateAll((els) => els.map((e) => e.className));
  const passed = outcomes.filter((o) => o === "passed").length;
  const failed = outcomes.filter((o) => o === "failed").length;
  check(passed === count("passed") && failed === count("failed") && failed > 0,
    `the workbench runs the chapter's tests in the page as pytest does at a desk: ${failed} failed, ${passed} passed`);
  const first = await wb.locator(".results li.failed pre").first().innerText();
  check(first.includes("NotImplementedError: problem 7.1"), "and says which problem is unsolved");
}

// Run buttons: a command the page prints in a Python tab runs in the page, and prints what it
// prints at a desk. The reader's command line prints the same JSON; pytest selects and passes the
// same tests.
{
  const runBlock = async (file, text) => {
    await page.goto(base + file);
    const box = page.locator(".runnable", { hasText: text }).first();
    await box.locator(".run-button").click();
    await box.and(page.locator('[data-state="running"]')).waitFor({ timeout: 10000 }).catch(() => {});
    await box.and(page.locator('[data-state="idle"]')).waitFor({ timeout: 300000 });
    return box.locator("xpath=following-sibling::div[1]").locator(".run-output").innerText();
  };
  const cli = await runBlock("lakehouse-and-beyond.html", "SELECT country FROM orders");
  const desk = spawnSync("python3", ["-m", "parquet_lab", "query", "fixtures/table/country=UK/part-0.parquet",
    "SELECT country FROM orders"], { encoding: "utf8", env: { ...process.env, PYTHONPATH: "python" } }).stdout;
  check(JSON.stringify(JSON.parse(cli)) === JSON.stringify(JSON.parse(desk)),
    "Run on ch14's `python3 -m parquet_lab query` prints the JSON it prints at a desk");
  const summary = (text) => (text.trim().split("\n").at(-1).match(/(\d+ passed, \d+ deselected)/) || [])[1];
  const tests = await runBlock("encodings.html", "records_rebuilt");
  const deskTests = spawnSync("python3", ["-m", "pytest", "python/tests", "-k", "records_rebuilt", "-p", "no:cacheprovider"],
    { encoding: "utf8" }).stdout;
  check(summary(tests) && summary(tests) === summary(deskTests),
    `Run on \`pytest python/tests -k records_rebuilt\` selects and passes what it does at a desk: ${summary(tests)}`);
  // A command that needs a compiler gets Open in Codespaces, never Run.
  const cargoTest = page.locator(".runnable", { hasText: "cargo test -p parquet-lab" }).first();
  check(await cargoTest.getAttribute("data-codespace") === "true"
    && await cargoTest.locator(".run-button").innerText() === "Open in Codespaces",
    "a `cargo test` command gets Open in Codespaces, not Run");
  // `cargo run -p pqlab` runs the binary's own command code, compiled to WebAssembly.
  await page.evaluate(() => localStorage.setItem("code-language", "rust"));
  const rust = await runBlock("running-the-lab.html", "cargo run -p pqlab -- inspect");
  await page.evaluate(() => localStorage.setItem("code-language", "python"));
  const deskRust = ["inspect fixtures/tiny.parquet", "footer fixtures/tiny.parquet --json",
    "footer fixtures/tiny.parquet --size suffix --prefetch 65536 --json", "interpret fixtures/tiny.parquet 629"]
    .map((c) => `$ cargo run -p pqlab -- ${c}\n${execFileSync("target/debug/pqlab", c.split(" "), { encoding: "utf8" })}`)
    .join("\n");
  check(rust.trim() === deskRust.trim(), "Run on `cargo run -p pqlab` prints, in the page, what the binary prints");
}

// ch02's walkthrough: short programs that read the file's bytes by hand, then with a library. A
// Python step runs in the page and prints the footer length the native reader decodes; an edited
// step runs the edit; the library step runs pyarrow; a Rust step offers a Codespace.
{
  await page.goto(base + "anatomy-of-a-parquet-file.html");
  const native = JSON.parse(execFileSync("target/debug/pqlab", ["footer", "fixtures/tiny.parquet", "--json"], { encoding: "utf8" }));
  const runStep = async (step) => {
    const box = step.locator(".runnable");
    await box.locator(".run-button:not(.edit-button)").click();
    await box.and(page.locator('[data-state="running"]')).waitFor({ timeout: 10000 }).catch(() => {});
    await box.and(page.locator('[data-state="idle"]')).waitFor({ timeout: 300000 });
    return step.locator(".run-output").innerText();
  };
  const length = page.locator('figure.walkthrough[data-file$="footer_length.py"]');
  const out = await runStep(length);
  check(out.includes(`read little-endian: ${native.trailer.footer_length}`),
    `the walkthrough reads the footer length by hand in the page: ${native.trailer.footer_length}, as the reader decodes it`);
  const opened = await runStep(page.locator('figure.walkthrough[data-file$="open_with_the_reader.py"]'));
  check(opened.includes(`footer length: ${native.trailer.footer_length}`) && opened.split("\n").filter((l) => l.includes(" -> ")).length === native.requests.length,
    `the book's reader, called in the page, opens the file in ${native.requests.length} requests`);
  const first = page.locator('figure.walkthrough[data-file$="first_bytes.py"]');
  await first.locator(".edit-button").click();
  const area = first.locator("textarea");
  await area.fill((await area.inputValue()).replace("data[:4]", "data[-4:]"));
  const edited = await runStep(first);
  check(edited.includes("PAR1") && (await first.locator(".status").innerText()).includes("your edited version"),
    "an edited walkthrough step runs the edit");
  // The step that asks a library loads pyarrow into the page on its first run.
  const library = await runStep(page.locator('figure.walkthrough[data-file$="footer_with_a_library.py"]'));
  check(library.includes(`footer length: ${native.trailer.footer_length}`),
    `the library step runs pyarrow in the page, and it reports the footer length the reader decodes: ${library.split("\n")[0]}`);
  check(await page.locator('figure.walkthrough[data-file$=".rs"] .runnable[data-codespace]').count()
    === await page.locator('figure.walkthrough[data-file$=".py"]').count(),
    "every Rust walkthrough step offers a Codespace");
}

// The reader editor: an edit to the Python reader reaches every lab on the page, and restoring
// the book's version brings back the reader's answer.
{
  await page.goto(base + "anatomy-of-a-parquet-file.html");
  await page.evaluate(() => localStorage.setItem("lab-engine", "python"));
  await page.reload();
  const footer = page.locator('.lab[data-experiment="anatomy"]');
  await footer.and(page.locator('[data-ready="true"]')).waitFor({ timeout: 180000 });
  const length = await footer.getAttribute("data-footer-length");
  await footer.locator("button[data-edit]").click();
  const editor = page.locator(".reader-editor");
  check(await editor.locator("select").inputValue() === "metadata.py", "Edit the code opens the module the lab's chapter builds");
  const text = await editor.locator("textarea").inputValue();
  await editor.locator("textarea").fill(`${text}\nraise RuntimeError("an edit that breaks the reader")\n`);
  await editor.locator('button[data-act="run"]').click();
  await footer.and(page.locator('[data-ready="error"]')).waitFor({ timeout: 30000 });
  check((await footer.locator(".lab-error").innerText()).includes("RuntimeError: an edit that breaks the reader")
    && (await footer.locator(".engine-bar .edited").innerText()).includes("metadata.py"),
    "an edit that breaks the reader shows Python's error in the lab, which says it runs the edit");
  await editor.locator('button[data-act="restore"]').click();
  await footer.and(page.locator('[data-ready="true"]')).waitFor({ timeout: 30000 });
  check(await footer.getAttribute("data-footer-length") === length
    && await page.evaluate(() => localStorage.getItem("reader-edits")) === null,
    `restoring the book's version brings back the reader's footer length (${length}) and forgets the edit`);
  await page.evaluate(() => localStorage.setItem("lab-engine", "rust"));
}

// Opened from a home screen, the book starts at index.html?resume and goes back to the page the
// reader was on, as far down as they were; the preface offers the same way back.
{
  await page.goto(base + "encodings.html");
  await page.mouse.wheel(0, 2000);
  await page.waitForTimeout(1000);
  const y = await page.evaluate(() => scrollY);
  await page.goto(base + "index.html?resume");
  await page.waitForURL(/encodings\.html$/);
  const back = await page.waitForFunction((want) => Math.abs(scrollY - want) < 5, y, { timeout: 10000 }).then(() => true, () => false);
  check(back, `the home-screen start goes back to the last page, scrolled to ${y}`);
  await page.goto(base + "index.html");
  check((await page.locator(".resume a").getAttribute("href")) === "encodings.html", "the preface links back to the last page");
}

check(errors.length === 0, `no errors in the browser console${errors.length ? `: ${errors.join("; ")}` : ""}`);
await browser.close();
server.close();
if (failures) {
  console.log(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("All browser checks passed.");
