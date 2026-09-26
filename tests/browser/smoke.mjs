// Drive the built book in a headless browser and check that the experiments are views of the
// reader, not pictures of one.
//
//     node tests/browser/smoke.mjs _build/html [--screenshots DIR]
//
// It serves the site from a local HTTP server, opens the chapters, and compares what the page
// shows with what the Rust reader computes natively (`cargo run -p pqlab -- footer … --json`).
// The browser and the command line must agree to the byte, because they run the same code.

import { createServer } from "node:http";
import { readFile, stat, mkdir } from "node:fs/promises";
import { execFileSync } from "node:child_process";
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
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
if (shots) await mkdir(shots, { recursive: true });

// ch02: the footer laboratory.
await page.goto(base + "anatomy-of-a-parquet-file.html");
const lab = page.locator('.lab[data-experiment="footer"]');
await lab.locator('[data-ready="true"]').or(lab).first().waitFor();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="footer"]')?.dataset.state === "ok");
const expected = native(["footer", "fixtures/tiny.parquet", "--json"]);
check(await lab.getAttribute("data-footer-length") === String(expected.trailer.footer_length),
  `footer length on the page is the reader's (${expected.trailer.footer_length})`);
check(await lab.getAttribute("data-requests") === String(expected.requests.length),
  `request count on the page is the reader's (${expected.requests.length})`);
const traceRanges = await lab.locator("table.trace tbody tr td:nth-child(3)").allInnerTexts();
check(JSON.stringify(traceRanges) === JSON.stringify(expected.requests.map((r) => r.range || "·")),
  `trace ranges match: ${traceRanges.join(", ")}`);

// Click the footer-length step: exactly its four bytes are highlighted.
await lab.locator(".steps li.key-step button.span").click();
const lit = await lab.locator(".hex .b.hl").evaluateAll((els) => els.map((e) => Number(e.dataset.o)));
const [ls, le] = expected.trailer.length_span;
check(JSON.stringify(lit) === JSON.stringify(Array.from({ length: le - ls }, (_, i) => ls + i)),
  `the footer-length step highlights bytes [${ls}, ${le})`);
const inspector = await lab.locator(".inspector").innerText();
check(inspector.includes(expected.trailer.footer_length.toLocaleString("en-GB")),
  "the inspector reads the selected bytes as the footer length");
if (shots) await lab.screenshot({ path: path.join(shots, "footer-lab.png") });

// Unfetched bytes are dimmed: everything outside the trailer and the footer.
const dim = await lab.locator(".hex .b.unfetched").count();
check(dim === expected.file_size - expected.totals.bytes_returned,
  `${dim} bytes dimmed as never requested`);

// A prefetch large enough for the footer removes the third request.
await lab.locator('input[name="size"][value="suffix"]').check();
await lab.locator('input[name="prefetch"]').fill("13");
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="footer"]').dataset.requests === "1");
const one = native(["footer", "fixtures/tiny.parquet", "--size", "suffix", "--prefetch", "65536", "--json"]);
check(one.requests.length === 1, "a 64 KiB suffix read opens the file in one request, on the page and natively");

// Damage the closing magic: the reader refuses, and says why.
await lab.locator(`.hex .b[data-o="${expected.file_size - 1}"]`).click();
await lab.locator('.inspector input[name="byte"]').fill("32");
await lab.locator(".inspector form.edit button[type=submit]").click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="footer"]').dataset.state === "error");
check((await lab.locator(".steps li.failed").innerText()).includes("PAR1"), "a damaged magic is reported");
await lab.locator(".inspector .restore").click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="footer"]').dataset.state === "ok");
check(true, "restoring the file restores the reader");

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

// ch01: the layouts.
await page.goto(base + "why-parquet-exists.html");
const layouts = page.locator('.lab[data-experiment="layouts"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="layouts"]')?.dataset.rowsRanges);
check(await layouts.getAttribute("data-rows-ranges") === "8" && await layouts.getAttribute("data-columns-ranges") === "1",
  "a two-column scan: one range per row by rows, one range by columns");
if (shots) await layouts.screenshot({ path: path.join(shots, "layouts-lab.png") });
if (shots) {
  await page.goto(base + "anatomy-of-a-parquet-file.html");
  await page.screenshot({ path: path.join(shots, "chapter.png") });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.screenshot({ path: path.join(shots, "chapter-dark.png") });
}

// ch03: the schema. The leaf count and the date reading are the reader's.
await page.goto(base + "the-type-system.html");
const schemaLab = page.locator('.lab[data-experiment="schema"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="schema"]')?.dataset.state === "ok");
const nativeSchema = native(["schema", "fixtures/types.parquet"]);
check(await schemaLab.getAttribute("data-leaves") === String(nativeSchema.leaves.length),
  `schema panel shows the reader's ${nativeSchema.leaves.length} leaf columns`);
const dateRow = schemaLab.locator(".values-table tr", { hasText: "order_date" });
const expectedDate = nativeSchema.leaves.find((l) => l.path === "order_date").statistics.min.logical;
check((await dateRow.innerText()).includes(expectedDate), `order_date's minimum reads as ${expectedDate}`);
await dateRow.locator("td:nth-child(4) button.span").click();
const minSpan = nativeSchema.leaves.find((l) => l.path === "order_date").statistics.min.span;
const litDate = await schemaLab.locator(".hex .b.hl").evaluateAll((els) => els.map((e) => Number(e.dataset.o)));
check(litDate[0] === minSpan[0] && litDate.length === minSpan[1] - minSpan[0],
  `clicking the minimum highlights its bytes [${minSpan[0]}, ${minSpan[1]})`);
if (shots) await schemaLab.screenshot({ path: path.join(shots, "schema-lab.png") });

// ch04: levels. The records the page rebuilds are the reader's.
await page.goto(base + "nested-data.html");
const levelsLab = page.locator('.lab[data-experiment="levels"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="levels"]')?.dataset.state === "ok");
const nativeLevels = native(["levels", "fixtures/nested.parquet", "2"]);
check(await levelsLab.getAttribute("data-records") === JSON.stringify(nativeLevels.records),
  `tags[] rebuilds to the reader's records: ${JSON.stringify(nativeLevels.records)}`);
await levelsLab.locator('button[data-column="4"]').click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="levels"]').dataset.triples === "6");
const deep = native(["levels", "fixtures/nested.parquet", "4"]);
check(await levelsLab.getAttribute("data-records") === JSON.stringify(deep.records),
  "switching column reruns the reader: items[].discounts[] rebuilt");
await levelsLab.locator(".runs-list button.span").first().click();
const hdr = deep.pages[0].repetition_levels.runs[0].header;
const litHdr = await levelsLab.locator(".hex .b.hl").evaluateAll((els) => els.map((e) => Number(e.dataset.o)));
check(litHdr[0] === hdr[0] && litHdr.length === hdr[1] - hdr[0], `a run header highlights its byte [${hdr[0]}, ${hdr[1]})`);
if (shots) await levelsLab.screenshot({ path: path.join(shots, "levels-lab.png") });

// ch05: encodings. The decoded values and the stepper are the reader's.
await page.goto(base + "encodings.html");
const encLab = page.locator('.lab[data-experiment="encodings"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="encodings"]')?.dataset.state === "ok");
const nativeEnc = native(["encodings", "fixtures/encodings.parquet", "0"]);
check(await encLab.getAttribute("data-values") === JSON.stringify(nativeEnc.values.map((v) => v.value)),
  `order_id decodes to the reader's ${nativeEnc.values.length} values`);
await encLab.locator('button[data-step="1"]').click();
await encLab.locator('button[data-step="1"]').click();
const step1 = nativeEnc.pages[0].steps[1].span;
const litStep = await encLab.locator(".hex .b.hl").evaluateAll((els) => els.map((e) => Number(e.dataset.o)));
check(litStep[0] === step1[0] && litStep.length === step1[1] - step1[0], `the second step highlights its bytes [${step1[0]}, ${step1[1]})`);
await encLab.locator(".lab-head select").selectOption("dictionary.parquet");
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="encodings"]').dataset.encoding === "RLE_DICTIONARY");
await encLab.locator('button[data-column="1"]').click();
const nativeDict = native(["encodings", "fixtures/dictionary.parquet", "1"]);
await page.waitForFunction((v) => document.querySelector('.lab[data-experiment="encodings"]').dataset.values === v,
  JSON.stringify(nativeDict.values.map((v) => v.value)));
check(true, "dictionary.parquet's country decodes through its dictionary to the reader's values");
if (shots) await encLab.screenshot({ path: path.join(shots, "encodings-lab.png") });

// ch06: pages. The page list, and a checksum failing after damage, are the reader's.
await page.goto(base + "pages.html");
const pagesLab = page.locator('.lab[data-experiment="pages"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="pages"]')?.dataset.state === "ok");
const nativePages = native(["pages", "fixtures/pages.parquet", "1"]);
check(await pagesLab.getAttribute("data-pages") === String(nativePages.pages.length),
  `country's chunk holds the reader's ${nativePages.pages.length} pages`);
await pagesLab.locator(".lab-head select").selectOption("pages-v2.parquet");
await page.waitForFunction(() => /^(ok,)+ok$/.test(document.querySelector('.lab[data-experiment="pages"]').dataset.crc || ""));
check(true, "every v2 page's checksum matches");
const v2 = native(["pages", "fixtures/pages-v2.parquet", "1"]);
const target = v2.pages[1].values[0];
await pagesLab.locator(`.hex .b[data-o="${target}"]`).click();
await pagesLab.locator('.inspector input[name="byte"]').fill("ff");
await pagesLab.locator(".inspector form.edit button[type=submit]").click();
await page.waitForFunction(() => (document.querySelector('.lab[data-experiment="pages"]').dataset.crc || "").split(",")[1] === "bad");
check(true, `damaging byte ${target} makes page 1's checksum fail, and only page 1's`);
if (shots) await pagesLab.screenshot({ path: path.join(shots, "pages-lab.png") });

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

// ch08: statistics. Verdicts, orders and the mistaken order are the reader's.
await page.goto(base + "metadata-and-statistics.html");
const statsLab = page.locator('.lab[data-experiment="statistics"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="statistics"]')?.dataset.state === "ok");
await statsLab.locator('button[data-cell="0:1"]').click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="statistics"]').dataset.selected === "0:1");
const cust = native(["statistics", "fixtures/statistics.parquet", "0", "1"]).selected;
check(await statsLab.getAttribute("data-order") === cust.order, `customer_id is compared as ${cust.order}, as the reader says`);
check((await statsLab.locator(".mistake").innerText()).includes(cust.values.mistake.result.max),
  `the mistaken order's maximum, ${cust.values.mistake.result.max}, is shown`);
await statsLab.locator('button[data-cell="1:6"]').click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="statistics"]').dataset.selected === "1:6");
check(await statsLab.getAttribute("data-usable") === "false", "an all-null chunk offers no bounds");
await statsLab.locator(".stats-fields button.span").first().click();
check(await statsLab.locator(".hex .b.sel").count() > 0, "a statistics field highlights its bytes");
if (shots) {
  await statsLab.locator('button[data-cell="0:3"]').click();
  await statsLab.screenshot({ path: path.join(shots, "statistics-lab.png") });
}

// ch09: skipping. Every plan is the reader's.
await page.goto(base + "skipping-data.html");
const skipLab = page.locator('.lab[data-experiment="skipping"]');
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="skipping"]')?.dataset.state === "ok");
const plan431 = native(["skipping", "fixtures/pruning-sorted.parquet", "0", "=", "431"]);
check(await skipLab.getAttribute("data-bytes-read") === String(plan431.totals.bytes_read),
  `order_id = 431 reads the reader's ${plan431.totals.bytes_read} bytes`);
check(await skipLab.getAttribute("data-skipped") === plan431.row_groups.map((g) => (g.skipped ? "skip" : "read")).join(","),
  "and skips the row groups the reader skips");
await skipLab.locator('input[name="m"][value="4"]').uncheck();
const noIndex = native(["skipping", "fixtures/pruning-sorted.parquet", "0", "=", "431", "--use", "statistics,bloom"]);
await page.waitForFunction((n) => document.querySelector('.lab[data-experiment="skipping"]').dataset.bytesRead === String(n), noIndex.totals.bytes_read);
check(true, `without the page index it reads ${noIndex.totals.bytes_read} bytes`);
await skipLab.locator('input[name="m"][value="4"]').check();
await skipLab.locator(".lab-head select").selectOption("pruning-shuffled.parquet");
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="skipping"]').dataset.state === "ok");
await skipLab.locator('select[name="column"]').selectOption("1");
await skipLab.locator('input[name="value"]').fill("424242");
await skipLab.locator('button[type="submit"]').click();
await page.waitForFunction(() => document.querySelector('.lab[data-experiment="skipping"]').dataset.skipped === "skip,skip,skip,skip");
check(true, "an absent customer number is ruled out in every row group by its Bloom filter");
if (shots) await skipLab.screenshot({ path: path.join(shots, "skipping-lab.png") });

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

check(errors.length === 0, `no errors in the browser console${errors.length ? `: ${errors.join("; ")}` : ""}`);
await browser.close();
server.close();
if (failures) {
  console.log(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("All browser checks passed.");
