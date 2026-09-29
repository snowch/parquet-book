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
// Pyodide, for the Python the page runs (walkthrough steps, Run buttons, the workbench), comes
// from a public CDN. Fetch it through Node, which
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
// A panel is a picture drawn by the Rust reader: no choice of engine, and no editor of the reader.
check(await anatomy.locator(".engine-bar, button[data-engine], button[data-edit]").count() === 0 &&
  await page.getByRole("button", { name: "Edit the code" }).count() === 0 &&
  (await anatomy.locator(".lab-note").innerText()).includes("Rust reader, compiled to WebAssembly"),
  "the byte map offers no engine choice and no Edit the code: it runs on the Rust reader in WebAssembly");
if (shots) {
  await anatomy.locator(".hex .b[data-o=\"20\"]").click();
  await anatomy.screenshot({ path: path.join(shots, "anatomy-lab.png") });
}

// The code tabs: Python first, one choice for every excerpt, remembered across pages. (ch01 is
// an explainer and quotes no reader code, so this starts on ch03.)
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

// ch01 explains and builds nothing: code and no panels.
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
// The panel offers the files whose tokens it can draw, and no table of sizes: the steps and the
// generated tables print those.
const offered = await compLab.locator(".lab-head select option").allInnerTexts();
check(offered.join(",") === "codec-snappy.parquet,codec-lz4.parquet,codec-gzip.parquet,pages-v2-snappy.parquet",
  `the compression panel offers the four files it can draw: ${offered.join(", ")}`);
check(await compLab.locator(".comp-grid table").count() === 0, "and draws no table of column chunk sizes");
const gzip = native(["compression", "fixtures/codec-gzip.parquet", "1"]);
await compLab.locator(".lab-head select").selectOption("codec-gzip.parquet");
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="compression"]').dataset.codec === "GZIP");
check(await compLab.getAttribute("data-tokens") === String(gzip.decompressed.tokens.length),
  `country's GZIP page decompresses in the reader's ${gzip.decompressed.tokens.length} tokens`);
{
  // The book's Python reader decompresses the page under each codec in the page, as at a desk.
  const step = page.locator('figure.walkthrough[data-file$="every_codec_one_page.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  await step.locator(".run-output").filter({ hasText: "GZIP:" }).waitFor({ timeout: 300000 });
  const out = await step.locator(".run-output").innerText();
  const pages = [snappy, native(["compression", "fixtures/codec-lz4.parquet", "1"]), gzip];
  check(pages.every((r) => out.includes(`${r.codec}: ${r.pages[r.page].compressed_page_size} bytes become ` +
    `${r.pages[r.page].uncompressed_page_size} in ${r.decompressed.tokens.length} tokens, the same: True`)),
    "ch07's second step decompresses each codec's page in the page as the native reader does");
}
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

// ch10: the read path. Requests and times are the reader's and the simulated store's, and the
// panel's strategies are the rows of the chapter's table of them.
await page.goto(base + "how-readers-read.html");
const scanLab = page.locator('.lab[data-experiment="scan"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="scan"]')?.dataset.state === "ok");
const scan1 = native(["scan", "fixtures/pruning-sorted.parquet", "--where", "0", "=", "431", "--size", "head", "--prefetch", "8"]);
check(await scanLab.getAttribute("data-requests") === String(scan1.totals.requests) &&
  await scanLab.getAttribute("data-elapsed") === String(scan1.totals.elapsed_us),
  `order_id = 431 takes the reader's ${scan1.totals.requests} requests and ${scan1.totals.elapsed_us / 1000} ms`);
check(await scanLab.getAttribute("data-matching") === "1", "and returns one row");
{
  // The step prints every request, so the panel offers one choice, of the table's strategies, and
  // draws no table of requests or rows and no byte view.
  const table = await readFile(new URL("../../chapters/_generated/scan-strategies.md", import.meta.url), "utf8");
  const rows = table.split("\n").filter((l) => l.startsWith("| ") && !l.startsWith("| Strategy"))
    .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()));
  const offered = await scanLab.locator('select[name="strategy"] option').allInnerTexts();
  check(offered.join("\n") === rows.map((r) => r[0]).join("\n"),
    `the panel offers the ${rows.length} strategies of the chapter's table, in its order`);
  check(await scanLab.locator("select, input").count() === 1 && await scanLab.locator("table, .hex").count() === 0,
    "and nothing else: no condition, no network, no table of requests or rows, no byte view");
  for (const [i, [label, requests, , time]] of rows.entries()) {
    await scanLab.locator('select[name="strategy"]').selectOption(String(i));
    const drawn = Number(await scanLab.getAttribute("data-requests"));
    const ms = `${Math.round(Number(await scanLab.getAttribute("data-elapsed")) / 1000)} ms`;
    const bars = await scanLab.locator(".timeline .req").count();
    check(`${drawn}` === requests && ms === time && bars === drawn,
      `${label}: ${drawn} requests on the timeline in ${ms}, as the table says`);
    if (label.includes("four connections")) {
      check(await scanLab.locator(".timeline .lane").count() === 4, "the timeline has a lane per connection");
      if (shots) await scanLab.screenshot({ path: path.join(shots, "scan-lab.png") });
    }
  }
  // pyarrow, in the page, reads row group 2 a column chunk at a time. The WebAssembly build the
  // page loads does so with pre_buffer too, where pyarrow at a desk merges the chunks into one
  // read (tests/test_walkthroughs.py checks that); the chapter says so.
  const step = page.locator('figure.walkthrough[data-file$="reads_with_a_library.py"]');
  await step.locator(".run-button:not(.edit-button)").click();
  await step.locator(".run-output").filter({ hasText: "pre_buffer=True" }).filter({ hasText: /rows\s*$/ })
    .waitFor({ timeout: 300000 });
  const out = (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  const reads = (from) => {
    const at = out.indexOf("read row group 2:", out.indexOf(from));
    let n = 0;
    while (out[at + 1 + n]?.startsWith("read ")) n += 1;
    return n;
  };
  check(out.includes(`read ${scan1.file_size} bytes at 0`) && reads("open, pre_buffer=False:") === scan1.columns.length &&
    reads("open, pre_buffer=True:") === scan1.columns.length,
    `pyarrow runs in the page: it opens the file in one read, and reads row group 2 in ${scan1.columns.length}, with or without pre_buffer`);
}

// ch11: writer settings. The page runs the reader's query on every file, and pyarrow writes the
// baseline again, to the byte.
await page.goto(base + "writing-parquet-well.html");
{
  const runStep = async (name, until) => {
    const step = page.locator(`figure.walkthrough[data-file$="${name}.py"]`);
    await step.locator(".run-button:not(.edit-button)").click();
    await step.locator(".run-output").filter({ hasText: until }).waitFor({ timeout: 300000 });
    return (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  };
  const baseline = native(["scan", "fixtures/writing-baseline.parquet", "--where", "0", "=", "431", "--size", "head", "--prefetch", "8", "--gap", "0"]);
  const lines = await runStep("query_every_file", "writing-no-index:");
  const { bytes_after_footer: bytes, requests_after_footer: requests } = baseline.totals;
  check(lines.some((l) => l.startsWith(`writing-baseline: ${bytes} bytes in ${requests} requests, `)) &&
    lines.filter((l) => l.startsWith("writing-")).length === 7,
    `order_id = 431 reads the reader's ${bytes} bytes in ${requests} requests after the baseline's footer, and runs on all seven files`);
  const size = (await readFile(new URL("../../fixtures/writing-baseline.parquet", import.meta.url))).length;
  const library = await runStep("writing_with_a_library", "the sort declared");
  check(library.some((l) => l.startsWith(`the baseline: ${size} bytes,`)),
    `pyarrow writes Snappy in the page, and rebuilds writing-baseline.parquet to the byte: ${size} bytes`);
}

// ch12 explains what a query engine does and builds nothing: no panels and no workbench. The book's
// Python reader answers the chapter's query in the page, stage by stage, as the native engine
// does; pyarrow's dataset module answers it too, in the page.
{
  await page.goto(base + "what-a-query-engine-does.html");
  check(await page.locator(".lab, .workbench").count() === 0, "ch12 has no panels and no workbench: its problems are questions");
  const runStep = async (name, until) => {
    const step = page.locator(`figure.walkthrough[data-file$="${name}.py"]`);
    await step.locator(".run-button:not(.edit-button)").click();
    await step.locator(".run-output").filter({ hasText: until }).waitFor({ timeout: 300000 });
    return (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  };
  const sql = "SELECT country, count(*) FROM orders WHERE order_id < 300 GROUP BY country ORDER BY country";
  const answer = native(["query", "fixtures/writing-baseline.parquet", sql]);
  const rows = answer.rows.map((r) => r.join(" "));
  const last = rows[rows.length - 1];
  const lines = await runStep("run_a_query", last);
  check(answer.stages.every((s) => lines.includes(`${s.name}: ${s.rows_in} rows in, ${s.rows_out} out`)) &&
    rows.every((r) => lines.includes(r)),
    `the engine runs in the page: ${answer.stages.length} stages and ${rows.length} rows, as it answers natively`);
  const kept = [...Array(answer.row_groups_read).keys()];
  const library = await runStep("query_with_a_library", last);
  check(library.includes(`row groups kept: [${kept.join(", ")}]`) && rows.every((r) => library.includes(r)),
    `pyarrow groups in the page: it keeps row groups [${kept}] and counts as the engine does`);
}

// ch13: encryption. The panel's columns are what the reader could read. pyarrow, without keys,
// reads the plain columns in the page and refuses the encrypted ones with an error, never by
// stopping the worker; the next step still runs after it.
{
  await page.goto(base + "modular-encryption.html");
  const cryptLab = page.locator('.lab[data-experiment="encryption"]');
  await page.waitForFunction(() => document.querySelector('.lab[data-experiment="encryption"]')?.dataset.state === "ok");
  const plain = native(["encryption", "fixtures/plaintext-footer.parquet"]);
  const encrypted = plain.columns.filter((c) => c.encrypted);
  check(await cryptLab.getAttribute("data-mode") === "plaintext footer" &&
    await cryptLab.getAttribute("data-encrypted") === String(encrypted.length) &&
    await cryptLab.locator(".crypt-cols tbody tr").count() === plain.columns.length,
    `the column table lists ${plain.columns.length} columns, ${encrypted.length} encrypted, as the native reader does`);
  await cryptLab.locator(".crypt-cols button.span", { hasText: "email" }).click();
  const email = plain.columns.find((c) => c.path === "email");
  check(await cryptLab.locator(".hex .b.hl").count() === email.span[1] - email.span[0],
    `selecting email marks its column chunk, bytes ${email.span[0]} to ${email.span[1]}`);
  await cryptLab.locator(".lab-head select").selectOption("encrypted-footer.parquet");
  await page.waitForFunction(() => document.querySelector('.lab[data-experiment="encryption"]').dataset.mode === "encrypted footer");
  check((await cryptLab.locator(".p-tree").innerText()).includes("Encrypted FileMetaData"), "the structure view shows the encrypted footer as one module");
  if (shots) await cryptLab.screenshot({ path: path.join(shots, "encryption-lab.png") });

  const runStep = async (name, until) => {
    const step = page.locator(`figure.walkthrough[data-file$="${name}.py"]`);
    await step.locator(".run-button:not(.edit-button)").click();
    await step.locator(".run-output").filter({ hasText: until }).waitFor({ timeout: 300000 });
    return (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  };
  const { num_rows: rows } = JSON.parse(await readFile("fixtures/plaintext-footer.json", "utf8"));
  const library = await runStep("encryption_with_a_library", "encrypted-footer.parquet:");
  check(library.includes(`plaintext-footer.parquet: ${rows} rows`) &&
    library.includes(`read ['order_id', 'country']: ${rows} rows`) &&
    library.some((l) => l.startsWith("read ['email']: Cannot decrypt")),
    "pyarrow without keys in the page reads the plain columns and refuses email with an error");
  const length = (await readFile("fixtures/plaintext-footer.parquet")).readUInt32LE(email.span[0]);
  const module = await runStep("one_module", "next module");
  check(module.includes(`a module at byte ${email.span[0]}: length ${length}`),
    "the worker outlives pyarrow's refusal: the next step runs, and reads email's first module");
}

// ch14: a table of files. The book's Python reader plans the chapter's query in the page, file by
// file, as the native reader does; pyarrow's dataset module reads the partitioned directory too.
{
  await page.goto(base + "lakehouse-and-beyond.html");
  check(await page.locator(".lab").count() === 0, "ch14 has no panels: its steps print each file's fate");
  const runStep = async (name, until) => {
    const step = page.locator(`figure.walkthrough[data-file$="${name}.py"]`);
    await step.locator(".run-button:not(.edit-button)").click();
    await step.locator(".run-output").filter({ hasText: until }).waitFor({ timeout: 300000 });
    return (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  };
  const ukSql = "SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200";
  const byLog = native(["table", "fixtures/table.json", ukSql, "--discovery", "log"]);
  const count = String(byLog.rows[0][0]);
  const lines = await runStep("query_the_table", "count(*)");
  check(byLog.files.every((f) => lines.includes(`${f.key}: ${f.why}`)) && lines.filter(Boolean).at(-1) === count,
    `reading the log in the page, the reader reads ${byLog.totals.files_read} of ${byLog.totals.files} files and counts ${count}, as it does natively`);
  const library = await runStep("table_with_a_library", "rows:");
  check(library.some((l) => l.includes("country: string")) && library.includes(`rows: ${count}`) &&
    byLog.files.filter((f) => f.partition.includes("country=UK")).every((f) =>
      library.some((l) => l.startsWith(`fixtures/table/${f.key}: `) && l.endsWith(f.read ? "kept [0]" : "kept []"))),
    "pyarrow's dataset in the page reads the partition from the paths, and keeps the file the log keeps");
}

// ch15: a changing table. The panel is a lookup, and its chain of requests is the native reader's;
// the steps print the same chain in the page, and pyarrow applies the deletes there too.
{
  await page.goto(base + "changing-a-table.html");
  const changesLab = page.locator('.lab[data-experiment="changes"]');
  await page.waitForFunction(() => document.querySelector('.lab[data-experiment="changes"]')?.dataset.state === "ok", null, { timeout: 60000 });
  const lookup = native(["changes", "fixtures/changes.json", "--snapshot", "after-a-day", "--lookup", "300"]);
  check(await changesLab.getAttribute("data-requests") === String(lookup.totals.requests) &&
    await changesLab.getAttribute("data-round-trips") === String(lookup.totals.round_trips) &&
    await changesLab.getAttribute("data-answer") === "found" &&
    await changesLab.locator(".timeline .req").count() === lookup.totals.requests,
    `finding order 300 draws ${lookup.totals.requests} requests in ${lookup.totals.round_trips} round trips, as the native reader's lookup makes`);
  check(await changesLab.locator(".timeline .lane").count() === 4, "the timeline has a lane per connection");
  check(await changesLab.locator("select, input").count() === 2 && await changesLab.locator("table").count() === 0,
    "the panel asks for a snapshot and an order, and nothing else: no scan, no compaction, no tables");
  await changesLab.locator('input[name="key"]').fill("250");
  await changesLab.locator('input[name="key"]').dispatchEvent("change");
  const gone = native(["changes", "fixtures/changes.json", "--snapshot", "after-a-day", "--lookup", "250"]);
  await page.waitForFunction(() => document.querySelector('.lab[data-experiment="changes"]').dataset.answer === "deleted");
  check(await changesLab.getAttribute("data-requests") === String(gone.totals.requests),
    `order 250 is found and then deleted by ${gone.deleted_by}, in ${gone.totals.requests} requests`);
  if (shots) await changesLab.screenshot({ path: path.join(shots, "changes-lab.png") });

  const runStep = async (name, until) => {
    const step = page.locator(`figure.walkthrough[data-file$="${name}.py"]`);
    await step.locator(".run-button:not(.edit-button)").click();
    await step.locator(".run-output").filter({ hasText: until }).waitFor({ timeout: 300000 });
    return (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  };
  const t = lookup.totals;
  const lines = await runStep("look_up_an_order", "requests,");
  check(lines.includes(`${t.requests} requests, ${t.bytes_fetched} bytes, ${Math.floor(t.elapsed_us / 1000)} ms`) &&
    lines.filter((l) => l.startsWith("round trip ")).length === t.round_trips,
    "the Python reader in the page makes the lookup the panel draws, round trip for round trip");
  const plan = native(["changes", "fixtures/changes.json", "--snapshot", "after-a-day", "--compact"]);
  const part = plan.groups.find((g) => g.data_files.includes("data/part-1.parquet"));
  const library = await runStep("deletes_with_a_library", "their amounts");
  check(library.includes(`data/part-1.parquet holds ${part.rows_in} rows; ${part.rows_in - part.rows_out} are deleted; ${part.rows_out} are live`),
    "pyarrow's compute functions run in the page and take out the rows the delete files name");
}

// ch16 explains what Iceberg adds and builds nothing: no panels and no workbench. The book's
// Python reader reads a ch15 data file's field ids in the page, as the native reader decodes them,
// and resolves the table's columns by id to the values the native engine reads; pyarrow reads the
// same ids in the page.
{
  await page.goto(base + "what-iceberg-adds.html");
  check(await page.locator(".lab, .workbench").count() === 0, "ch16 has no panels and no workbench: its problems are questions");
  const runStep = async (name, until) => {
    const step = page.locator(`figure.walkthrough[data-file$="${name}.py"]`);
    await step.locator(".run-button:not(.edit-button)").click();
    await step.locator(".run-output").filter({ hasText: until }).waitFor({ timeout: 300000 });
    return (await step.locator(".run-output").innerText()).split("\n").map((l) => l.trim());
  };
  const file = "fixtures/changes/data/part-0.parquet";
  const ids = native(["schema", file]).elements.filter((e) => e.field_id !== null);
  const [first] = native(["query", file, "SELECT order_id, country, amount_cents FROM orders"]).rows;
  const lines = await runStep("field_ids_by_hand", "by name, the file has no");
  check(ids.length > 0 && ids.every((e) => lines.includes(`field id ${e.field_id}: ${e.name}`)),
    `the Python reader in the page reads ${ids.length} field ids from the footer, as the native reader decodes them`);
  check(lines.includes(`order_number (id 1) <- order_id: ${first[0]}`) &&
    lines.includes(`country (id 4) <- country: ${first[1]}`) &&
    lines.includes(`amount_cents (id 6) <- amount_cents: ${first[2]}`) &&
    lines.includes("channel (id 7) <- no column: None") &&
    lines.includes("by name, the file has no order_number, channel"),
    "the renamed column reads the file's order_id by id, and the added one reads as missing");
  const library = await runStep("field_ids_with_a_library", "id 1 <-");
  check(ids.every((e) => library.includes(`field id ${e.field_id}: ${e.name}`)) &&
    library.includes(`id 1 <- order_id: ${first[0]}`),
    "pyarrow in the page reads the same field ids, and id 1 from order_id");
}

// Every panel is a picture drawn by the Rust reader in WebAssembly, on every page that has one:
// it draws, and offers no choice of engine and no editor of the reader.
{
  const pages = [];
  for (const f of (await readdir(root)).filter((n) => n.endsWith(".html")).sort()) {
    if ((await readFile(path.join(root, f), "utf8")).includes("data-experiment=")) pages.push(f);
  }
  for (const f of pages) {
    await page.goto(base + f);
    await page.waitForFunction(() => [...document.querySelectorAll(".lab[data-experiment]")]
      .every((el) => el.dataset.ready === "true"), null, { timeout: 60000 });
    const labs = page.locator(".lab[data-experiment]");
    check(await labs.count() > 0 &&
      await labs.locator(".engine-bar, button[data-engine], button[data-edit]").count() === 0 &&
      await page.getByRole("button", { name: "Edit the code" }).count() === 0 &&
      await page.locator(".reader-editor").count() === 0,
      `${f}: its panels draw on the Rust reader, with no engine choice and no Edit the code`);
  }
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

// The layout. Code or a table that would be cut off at the prose's measure takes the wide column,
// and whatever that still cuts off has an Expand button, which gives it the window and gives it
// back; the outline makes way when it would crowd the chapter; each rail closes from the top bar
// and stays closed; and a phone never scrolls sideways.
{
  const settle = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  const blocks = () => page.evaluate(() => [...document.querySelectorAll("#main pre, #main textarea.code-area")]
    .filter((e) => e.offsetParent !== null && !e.closest(".lab, .workbench, .run-result, .results"))
    .map((e) => {
      const box = e.closest("figure.quoted, .wide-block");
      const button = box && box.querySelector(".expand");
      return { cut: e.scrollWidth > e.clientWidth + 1, expand: !!button && !button.hidden,
        width: e.getBoundingClientRect().width };
    }));
  const shown = (selector) => page.locator(selector).evaluate((e) => getComputedStyle(e).display !== "none");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + "skipping-data.html");
  await settle();
  const prose = await page.locator("#main .page > p:not(.builds)").first().evaluate((e) => e.getBoundingClientRect().width);
  let seen = await blocks();
  check(seen.length > 0 && seen.some((b) => b.width > prose + 40) && seen.every((b) => !b.cut || b.expand),
    `at 1440px code wider than the ${Math.round(prose)}px prose takes the wide column (up to ${Math.round(Math.max(...seen.map((b) => b.width)))}px), and none is cut off without Expand`);
  await page.goto(base + "anatomy-of-a-parquet-file.html");
  await settle();
  seen = await blocks();
  check(seen.every((b) => !b.cut || b.expand), `ch02: ${seen.filter((b) => b.cut).length} of ${seen.length} blocks still cut off at 1440px, each with an Expand button`);
  {
    const button = page.locator("#main .expand:visible").first();
    await button.scrollIntoViewIfNeeded();
    const y = await page.evaluate(() => scrollY);
    await button.click();
    const full = await page.locator("#main .expanded").evaluate((e) => {
      const r = e.getBoundingClientRect();
      return r.left === 0 && r.top === 0 && r.width === innerWidth && r.height === innerHeight;
    });
    check(full && (await button.getAttribute("aria-expanded")) === "true", "Expand gives the block the whole window");
    await page.keyboard.press("Escape");
    await settle();
    check(await page.locator("#main .expanded").count() === 0 && Math.abs(await page.evaluate(() => scrollY) - y) < 2,
      "Escape closes it, back where the reader was");
    await button.click();
    await page.goBack();
    await page.waitForFunction(() => !document.querySelector("#main .expanded"));
    check(page.url().endsWith("anatomy-of-a-parquet-file.html") && Math.abs(await page.evaluate(() => scrollY) - y) < 2,
      "and Back closes it without leaving the chapter");
  }

  // At 1280px the outline beside the chapter list would leave the chapter narrower than its prose.
  await page.goto(base + "skipping-data.html");
  await page.setViewportSize({ width: 1280, height: 1000 });
  await settle();
  check(!(await shown(".toc")) && await page.locator("#outline").isHidden(),
    "at 1280px the outline makes way for the chapter, and so does its button");
  await page.locator("#menu").click();
  await settle();
  check(!(await shown(".nav")) && await shown(".toc") && (await page.locator("#menu").getAttribute("aria-expanded")) === "false",
    "closing the chapter list gives the chapter its room, and the outline comes back");
  await page.reload();
  await settle();
  check(!(await shown(".nav")) && await shown(".toc"), "the closed chapter list stays closed when the page loads again");
  await page.locator("#menu").focus();
  await page.keyboard.press("Enter");
  await settle();
  check(await shown(".nav") && !(await shown(".toc")) && (await page.locator("#menu").getAttribute("aria-expanded")) === "true",
    "and the keyboard opens it again");

  // Where there is room for both rails, the outline has a button of its own, remembered too.
  await page.setViewportSize({ width: 1920, height: 1000 });
  await settle();
  const outline = page.locator("#outline");
  check(await shown(".toc") && await outline.isVisible() && (await outline.getAttribute("aria-expanded")) === "true",
    "at 1920px both rails show, and the outline's button says it is open");
  await outline.click();
  await settle();
  check(!(await shown(".toc")) && (await outline.getAttribute("aria-expanded")) === "false", "the outline's button closes it");
  await page.goto(base + "encodings.html");
  await settle();
  check(!(await shown(".toc")), "and it stays closed on the next page");
  await outline.click();
  await settle();
  check(await shown(".toc") && await page.evaluate(() => localStorage.getItem("toc")) === null, "and opens again");

  // A phone: nothing wider than the screen, and the Chapters button opens the list over the page.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const name of ["skipping-data.html", "what-a-query-engine-does.html", "anatomy-of-a-parquet-file.html", "nested-data.html"]) {
    await page.goto(base + name);
    await settle();
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(over <= 0, `at 390px ${name} does not scroll sideways`);
  }
  await page.locator("#menu").click();
  check(await page.locator(".nav").isVisible() && (await page.locator("#menu").getAttribute("aria-expanded")) === "true",
    "on a phone the Chapters button opens the list");
  const first = await page.evaluate(() => {
    const a = document.querySelector("#nav a");
    return { text: a.textContent, top: a.getBoundingClientRect().top,
             bar: document.querySelector(".top").getBoundingClientRect().bottom };
  });
  check(first.text === "Cover" && first.top >= first.bar,
    `and its first entry, ${first.text}, shows below the top bar (${Math.round(first.top)}px, bar ends at ${Math.round(first.bar)}px)`);
  const end = await page.evaluate(() => {
    const nav = document.querySelector("#nav"), links = nav.querySelectorAll("a");
    nav.scrollTop = nav.scrollHeight;
    return { fits: nav.getBoundingClientRect().bottom <= innerHeight + 1,
             last: links[links.length - 1].getBoundingClientRect().bottom <= innerHeight + 1 };
  });
  check(end.fits && end.last, "and the list fits the screen and scrolls to its last entry");
  const here = page.url();
  await page.goBack();
  await page.waitForTimeout(300);
  check(await page.locator(".nav").isHidden() && page.url() === here, "Back closes the list and stays on the page");
  await page.locator("#menu").click();
  await page.locator("#menu").click();
  check(await page.locator(".nav").isHidden(), "and the button closes it too");
  await page.setViewportSize({ width: 1440, height: 1000 });
}

// The site opens on the cover: the book's title, its picture of a file, and the way in, which is
// the preface, published as preface.html.
{
  await page.goto(base);
  check((await page.locator("article.page h1").textContent()) === "Parquet, byte by byte", "the site opens on the cover");
  const hero = page.locator("article.cover > img");
  const drawn = await hero.evaluate(async (img) => { await img.decode().catch(() => {}); return img.complete && img.naturalWidth > 0; });
  check(drawn && (await hero.getAttribute("src")) === "cover-hero.svg" && ((await hero.getAttribute("alt")) || "").includes("PAR1"),
    "the cover shows its picture of a file, with alt text");
  check((await page.locator(".nav a").first().textContent()) === "Cover"
    && (await page.locator(".nav a").nth(1).getAttribute("href")) === "preface.html", "the chapter list starts at the cover, then the preface");
  await page.getByRole("link", { name: "Start with the Preface" }).click();
  const opened = await page.waitForURL(/preface\.html$/, { timeout: 10000 }).then(() => true, () => false);
  check(opened && (await page.locator("article.page h1").textContent()) === "Preface", "the cover's link opens the preface");
  check((await page.locator(".prevnext .prev").getAttribute("href")) === "index.html", "and the preface's previous page is the cover");
  const foot = page.locator("footer.colophon");
  check((await foot.count()) === 1 && (await foot.textContent()).includes("Chris Snow")
    && (await foot.locator("a").evaluateAll((a) => a.map((x) => x.textContent))).join(",") === "CC BY-NC 4.0,Apache 2.0",
    "every page but the cover ends with its author and licences");
}

// Opened from a home screen, the book starts at the cover, index.html?resume, and goes back to the
// page the reader was on, as far down as they were; the cover offers the same way back. The
// preface is a page like any other, so it is remembered too; the cover never is.
{
  await page.goto(base + "encodings.html");
  await page.mouse.wheel(0, 2000);
  await page.waitForTimeout(1000);
  const y = await page.evaluate(() => scrollY);
  // A launch is a new session: the book resumes once a session, not on every visit to the start.
  await page.evaluate(() => sessionStorage.clear());
  const launched = page;
  await launched.goto(base + "index.html?resume");
  await launched.waitForURL(/encodings\.html$/);
  const back = await launched.waitForFunction((want) => Math.abs(scrollY - want) < 5, y, { timeout: 10000 }).then(() => true, () => false);
  check(back, `the home-screen start goes back to the last page, scrolled to ${y}`);
  await launched.goto(base + "index.html?resume");
  await launched.waitForTimeout(500);
  check(launched.url().endsWith("index.html?resume"), "and within that session the start shows the cover, so Back does not bounce forward");
  await page.goto(base + "index.html");
  check((await page.locator(".resume a").getAttribute("href")) === "encodings.html", "the cover links back to the last page");
  await page.goto(base + "preface.html");
  await page.waitForTimeout(500);
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(base + "index.html?resume");
  const toPreface = await page.waitForURL(/preface\.html$/, { timeout: 10000 }).then(() => true, () => false);
  check(toPreface, "the home-screen start goes back to the preface when that was the last page");
  await page.goto(base);
  check((await page.locator(".resume a").getAttribute("href")) === "preface.html", "and the cover links back to it");
}

// Installed on a phone, the book runs as an app whose links within the book carry no referrer
// (Android). The cover's link must open the cover, not be taken for a launch and sent back to the
// last page read.
{
  const app = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await app.addInitScript(() => {
    const real = window.matchMedia.bind(window);
    window.matchMedia = (q) => (q.includes("display-mode: standalone")
      ? { matches: true, media: q, addEventListener() {}, removeEventListener() {} } : real(q));
    Object.defineProperty(document, "referrer", { get: () => "" });
  });
  const tab = await app.newPage();
  await tab.goto(base + "index.html?resume");
  await tab.goto(base + "preface.html");
  await tab.waitForTimeout(500);
  await tab.locator(".prevnext .prev").click();
  await tab.waitForURL(/index\.html$/);
  await tab.waitForTimeout(500);
  check(tab.url().endsWith("index.html") && (await tab.locator("article.page h1").textContent()) === "Parquet, byte by byte",
    "in an installed book with no referrer, the cover's link opens the cover");
  const launch = await app.newPage();
  await launch.goto(base + "index.html");
  const resumed = await launch.waitForURL(/preface\.html$/, { timeout: 10000 }).then(() => true, () => false);
  check(resumed, "and a new launch of it still goes back to the last page read");
  await app.close();
}

check(errors.length === 0, `no errors in the browser console${errors.length ? `: ${errors.join("; ")}` : ""}`);
await browser.close();
server.close();
if (failures) {
  console.log(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("All browser checks passed.");
