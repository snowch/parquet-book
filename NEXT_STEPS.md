# Next steps

The working list. PLAN.md §2 has the phases; this is the order to do them in.

## Done: the first vertical slice

- Reader: byte primitives, trailer, footer range, Thrift compact decoding with spans, the names
  from `parquet.thrift`, typed `FileMetaData`, page-header walking, PLAIN scalars for statistics.
- Simulated object store with `HEAD`, bounded and suffix ranges, S3 semantics, a trace and a
  deterministic cost model; footer discovery with size-from-HEAD, size-from-listing, suffix range,
  and tail prefetch.
- WebAssembly build with a C ABI; the footer, anatomy and layouts laboratories.
- ch01 and ch02 written; problems 1.1, 2.1, 2.2, 2.3 with tests; generated figures.
- Checks: fixture reproducibility, figure staleness, numbers in prose, WASM/native parity, built
  links, headless-browser test of the experiments.

## Done: ch03, the type system

- Reader: full logical types (`logical.rs`) applied to values, the schema tree rebuilt from the
  flat list with maximum levels (`schema.rs`), statistics value spans.
- Fixture: `types.parquet`; every manifest now records pyarrow's reading of each leaf.
- Experiment: the schema panel (flat list, rebuilt tree, statistics read through logical types);
  since replaced by code (below).
- Problems 3.1 to 3.3 with tests; 3.4 about the reader's own schema.

## Done: ch04, nested data

- Reader: the RLE / bit-packing hybrid with runs and spans (`rle.rs`), PLAIN values with spans
  (`plain.rs`), data page v1 bodies split into levels and values (`column.rs`), path levels,
  plain-English explanations of each triple, and record assembly (`nested.rs`), checked against
  pyarrow's rows for every column of every fixture.
- Fixture: `nested.parquet`. Experiment: the levels panel, since replaced by code (below).
  Problems 4.1, 4.2 with tests; 4.3 open.

## Done: ch05, encodings

- Reader: dictionary pages and RLE_DICTIONARY indices, DELTA_BINARY_PACKED, DELTA_LENGTH_BYTE_ARRAY,
  DELTA_BYTE_ARRAY and BYTE_STREAM_SPLIT (`delta.rs`), behind one dispatcher that records every
  decode step with its bytes (`decode.rs`).
- Fixtures: `dictionary.parquet`, `encodings.parquet`. Experiment: the encodings stepper, since
  replaced by code (below).
- Problems 5.1 to 5.3 with tests; 5.4 about the reader's own columns.

## Done: ch06, pages

- Reader: data page v2 bodies, v2 header fields, CRC-32 page checksums, rows per page
  (`column::first_rows`). Fixtures `pages.parquet` and `pages-v2.parquet`. The page walker panel,
  since replaced by code (below).
- Problems 6.1 (walk a chunk) and 6.2 (CRC-32) with tests; 6.3 open.
- The Rust toolchain is pinned in `rust-toolchain.toml`, after a floating `stable` turned CI red.

## Done: ch07, compression

- Reader: Snappy, LZ4_RAW and GZIP (inflate) decompressors that record their tokens
  (`compress.rs`); the column reader decompresses v1 bodies, v2 values sections and dictionary
  pages. ZSTD and Brotli are refused by name (PLAN.md §4).
- Fixtures: `codec-{none,snappy,lz4,gzip,zstd,brotli}.parquet`, `codec-zstd-split.parquet`,
  `pages-v2-snappy.parquet`. Every decodable page matches `codec-none.parquet` byte for byte.
- Experiment: the compression panel (sizes per chunk, tokens stepped against the rebuilt page).
- Problems 7.1 (Snappy) and 7.2 (LZ4) with tests; 7.3 open.

## Done: ch08, metadata and statistics

- Reader: `stats.rs` (a comparator for every type, the mistaken order for each, and `bounds`,
  the rules for which statistics a reader may use); `Statistics` keeps the deprecated `min` and
  `max` apart from `min_value` and `max_value`; `column_orders` and `sorting_columns` decoded.
- Fixture `statistics.parquet`. The reader's orders reproduce pyarrow's bounds for every column
  chunk of every fixture. NaN is written to JSON as `"NaN"` instead of `null`.
- Experiment: the statistics panel, since replaced by code (below). Problems 8.1 (sort orders) and 8.2 (which bounds); 8.3 open.

## Done: ch09, skipping data

- Reader: `prune.rs` (conditions judged against bounds, plans over statistics, Bloom filters and
  the page index, and the bytes of every column a plan reads); `page_index.rs` (ColumnIndex and
  OffsetIndex); `bloom.rs` (xxHash64 and split block Bloom filters). Indexes and filters appear
  in the structure view.
- Fixtures `pruning-sorted.parquet` and `pruning-shuffled.parquet`. Tests: the OffsetIndex
  matches the walked pages, the ColumnIndex matches each page's decoded values, every value
  passes its filter, and no plan skips a matching row, over hundreds of conditions.
- Experiment: the skipping panel, since replaced by code (below). Problems 9.1 (can this be skipped?) and 9.2 (probe a filter);
  9.3 open.

## Done: ch10, how readers read

- Reader: `scan.rs` (a query run in phases: footer, indexes, data; ranges coalesced within a gap
  or never; only fetched bytes decoded). `TracingStore` has connections and phases, and
  `ObjectStore::next_phase` marks dependent requests. `column::read_column_pages` reads chosen
  pages where the OffsetIndex puts them. Indexes are fetched only for row groups the statistics
  keep.
- Tests: over two hundred fixture, condition and strategy combinations, a scan's rows equal a
  plain read's; removing a fetch makes the test fail.
- Experiment: the read-path panel with a request timeline. Problems 10.1 (merge ranges) and 10.2
  (time the requests); 10.3 open.

## Done: ch11, writing Parquet well

- Fixtures `writing-*.parquet`: the same 800 orders written seven ways (baseline, one row group,
  small row groups, sorted by country, shuffled, no dictionary, no page index). Their manifests
  share the baseline's rows by `order_id`, and every manifest now writes one row per line.
- The read path never fetches a byte twice; the scan test asserts it.
- Experiment: one query against every file. Figures: the files, lookups per row group, five
  queries' costs. Problems 11.1 and 11.2 with tests; 11.3 open.

## Done: ch12, a tiny query engine

- Reader: `engine.rs` (a tokeniser and parser for a small SQL; a scan that skips row groups by
  every condition's statistics; filter, aggregate, project, sort and limit, each recording its
  rows). `fixtures/queries.json` holds pyarrow's answers to twelve queries, and the engine must
  match them.
- Experiment: a query box with every stage shown, since replaced by code (below). Problems 12.1 (hash aggregate) and 12.2 (top n)
  graded against pyarrow; 12.3 open.

## Done: ch13, modular encryption

- Fixtures `plaintext-footer.parquet` and `encrypted-footer.parquet`, written by pyarrow through a
  toy key service with published test keys; written once and checked by decryption (PLAN.md §4).
- Reader: `crypto.rs` (modules by their lengths; an encrypted footer's crypto metadata and
  module); signed plaintext footers; column crypto metadata; encrypted columns refused by name;
  the structure view shows modules, signatures and `PARE` files.
- Experiment: what a reader without keys can and cannot see, since slimmed to its byte map and
  column table (below). Problems 13.1 and 13.2; 13.3 open.

## Done: ch14, lakehouse and beyond

- Fixtures: `fixtures/table/`, the ch11 orders written by pyarrow's dataset writer into
  Hive-style `country=` directories with at most a hundred rows a file, and a Delta-style log
  beside them; `fixtures/table.json` lists the objects. pyarrow's answers to five table queries
  are in `fixtures/queries.json`.
- Reader: `table.rs` (partition values from paths; the log's `add` and `remove` actions with their
  statistics; files ruled out by path and by statistics; the survivors fetched whole and queried
  together by the ch12 engine, with partition columns from the paths). The object store gained
  `LIST` and whole-object reads.
- Experiment: a query over the table with the files found by listing, by listing and pruning by
  path, or by the log, since replaced by code (below). Problems 14.1 (partition values) and 14.2 (plan from the log); 14.3 open.

## Done: the Python reader

The reader exists in Python as well as Rust (PLAN.md §4), for every chapter.

- `python/parquet_lab`: every module of the Rust reader, with the same names, errors and JSON.
  `report` and `browser` answer every call the labs make; `python -m parquet_lab` prints what
  `pqlab` prints.
- `tests/test_python.py`: identical JSON from both readers for every lab call, on every fixture
  and on damaged copies, and from both command lines. `python/tests`: the Rust unit and fixture
  tests, in Python.
- The page: excerpts in Python and Rust tabs (Python first, remembered); a switch on every lab to
  run the Python reader under Pyodide; every problem in Python, graded by pytest.

The figures stay generated by the Rust reader: the parity test is what makes them the Python
reader's numbers too.

## Done: editing and running the code online

- Every chapter's Problems section ends with a workbench: the Python stub in an editor, kept in
  the browser, and "Run the tests", which runs the chapter's pytest graders under Pyodide in a
  web worker, on the repository's own files. One chapter's saved answers are there for another's
  problems, as at a desk.
- On the Python engine, "Edit the code" opens any module of the Python reader; running puts the
  edits in place and remounts every lab. A broken edit shows Python's traceback in the labs.
- Every command a page prints that the page can run has a Run button: the Python reader's tests,
  a problem's tests and its command line in the Python worker, and `cargo run -p pqlab` on the
  Rust reader compiled to WebAssembly (`pl_cli` runs `pqlab::cli`, byte for byte the binary's
  output). The whole of `python/tests` runs in the page in about fifteen seconds. Commands that
  need a compiler get Open in Codespaces, and so does "Edit the code" on the Rust engine.
- `.devcontainer/` makes the repository a Codespace, for the Rust reader and its problems.
- The browser test runs a workbench against native pytest and checks an edit and its restore.

## Done: walking through the bytes by hand (ch02)

ch02's experiment now opens with "Read the bytes yourself": five steps, in Python and Rust
(`walkthroughs/`), that read the magic at both ends, the footer length and where the footer
starts, then damage the length. In the page each Python step can be edited and run; each Rust
step opens a Codespace.

## Done: code first, for data engineers (ch01, ch02)

The book's readers are data engineers, and code is their interface, so the method is now: read
the structure by hand, build it into the reader, then ask a library (PLAN.md, section 1).

- ch01 explains and builds nothing (`tools/outline.EXPLAINERS`): no *Building it*, no coding problems,
  two questions to reason about. It opens on a measurement: two columns read from a CSV file a
  row at a time, and from the Parquet file of the same table with pyarrow and the `parquet` crate,
  each through a file that counts the bytes read (`fixtures/formats/`, pyarrow's defaults). The
  book's reader works out the least a Parquet reader can read; the crate reads exactly that, and
  pyarrow more, for its prefetched tail. The eight-order version shows Parquet losing to a tiny
  CSV. Then `two_layouts` draws the picture of why in text, one character a value: the query's
  columns scattered by rows, one run by columns. ch01 has no panels and uses none of the reader.
- ch02 ends *Building it* with "Ask a library": `footer_with_a_library`, pyarrow's `read_metadata` in
  Python (run in the page, pyarrow loaded under Pyodide on first run) and the `parquet` crate in
  Rust (`walkthroughs/libraries`, a workspace of its own). The test checks both against the
  manifest; the browser test runs the pyarrow step in the page.

## Done: ch15, changing a table

Written in the new shape from the start. `fixtures/changes/` is a pyarrow-written table with
snapshots: written, deleted from by copy-on-write and by Iceberg-shaped position delete files,
appended to in small batches, and compacted. The reader's `changes` module scans a snapshot
applying its deletes, looks up one order through the snapshots, trailer, footer, page index and
pages (ch10's `scan_in` on a shared store), plans a compaction, and checks the plan against the
`compacted` snapshot. Figures measure a lookup against a key-value store's one request, the write
and read amplification of the two ways to delete, scans as deletes and small files pile up, and
how many scans a compaction takes to pay for itself. Walkthroughs read the snapshots and a delete
file by hand; the library step applies the deletes with pyarrow and the `parquet` crate.

Could follow: equality deletes and deletion vectors beside position deletes; snapshot expiry and
what it frees; two writers racing a compaction, with one commit retried.

## Done: ch02's panel of controls, as code

The footer panel's controls (how the size is learned, how much of the tail is read first, bytes
to damage) were parameters of one call, so ch02 now makes the call: `open_with_the_reader` opens
`tiny.parquet` through a store that logs every request and prints the trace, and
`the_reader_refuses` hands it the damaged copy. The byte map stays, as the picture, and dims the
bytes the reader never asked for. The footer lab is gone; `report::footer_lab` still serves the
CLI's `footer` command and the byte map.

## Done: prose fixes from the chapter review

Stale cross-references, typed numbers and factual slips corrected across ch02 to ch15, each
checked against the reader, the fixtures or the writers' sources; ch04 now includes its `email`
levels figure, and ch15's bytes-a-row figure rounds down as its walkthrough step does.

## Done: ch03 in code

ch03 opens on three steps instead of its schema panel: `schema_as_stored` prints the footer's
flat list, `rebuild_the_tree` rebuilds it with a few lines of recursion and the leaves' levels (and
a byte to damage, which the reader's `build` refuses), and `same_bytes_two_ways` reads three
minimums by hand, little- and big-endian. `schema_with_a_library` asks pyarrow and the crate. The
schema panel is gone from every layer; `report::schema` stays for `pqlab schema` and the figures.

## Done: ch04 in code

ch04 opens on two steps instead of its levels panel: `unpack_the_levels` unpacks a page's two
level streams by hand (length, run header, bits lowest first), and `levels_of_a_column` prints the
reader's triples and rebuilt records. `levels_with_a_library` shows pyarrow's offsets and validity
beside the crate's levels. The panel is gone from every layer; `report::levels` stays for `pqlab
levels` and the figures.

## Done: ch05 in code

ch05 opens on three steps instead of its encodings panel: `delta_header` reads `ordered_at`'s
delta header and first block by hand, `dictionary_by_hand` reads `country`'s dictionary page and
indices, and `decode_a_column` prints the reader's decode steps for `url`. `encodings_with_a_library`
asks pyarrow and the crate for each chunk's encodings and the dictionary. The panel is gone from
every layer; `report::encodings` stays for `pqlab encodings` and the figures.

## Done: ch06 in code

ch06 opens on two steps instead of its pages panel: `walk_the_pages` loops `read_page` over
`country`'s column chunk and prints each header, and `damage_a_page` recomputes a body's CRC-32,
flips a bit, and shows the reader's walk failing only that page. `pages_with_a_library` shows
pyarrow reading the damaged file silently and refusing it with `page_checksum_verification`, and
the crate's page reader (now built with `crc`) refusing it too. `report::pages` stays for `pqlab
pages` and the figures.

## Done: ch08 in code

ch08 opens on three steps instead of its statistics panel: `signed_or_unsigned` reads
`customer_id`'s bounds as unsigned and signed, `byte_order` sorts four cities by their bytes both
ways, and `the_reader_decides` asks `stats.bounds` about every column chunk. In
`statistics_with_a_library`, pyarrow's `max_raw` and the crate's `max_opt` both give the negative
maximum, though the crate reports the column order as unsigned. `report::statistics` stays for
`pqlab statistics` and the figures; the grid figure is gone.

## Done: ch09 in code

ch09 opens on four steps instead of its skipping panel: `row_group_bounds` reads `order_id`'s
range per row group by hand, `pages_of_one_group` reads the ColumnIndex and OffsetIndex,
`probe_a_bloom_filter` tests customer 424242's eight bits, and `plan_a_read` calls `prune.plan`
with `Mechanisms`. In `skipping_with_a_library`, pyarrow's dataset fragments keep row groups by
statistics only (it reads no filter or page index), and the crate's predicate, page index and
`Sbbf::check` answer the rest. `report::skipping` stays for `pqlab skipping`, problem 9.3 and the
figures; the page index figure is gone.

## Done: ch07 in code

ch07 opens on two steps: `snappy_by_hand` decodes the `country` page's varint and tags, and
`every_codec_one_page` calls `compress.decompress` on the Snappy, LZ4 and GZIP pages and compares
each with `codec-none`'s. In `compression_with_a_library`, pyarrow names the file's `LZ4_RAW` as
`LZ4`, and the crate's `compression()` adds a GZIP level the file does not store. The token
stepper stays, slimmed to four files and no size table; the Snappy token table is gone, and LZ4
and Huffman sit in a note.

## Done: ch10 in code

ch10 opens on `read_with_a_strategy`, which runs `scan` for `order_id = 431` and prints every
request with its connection and times; the invitations change the tail read, the gap and the
connections. In `reads_with_a_library`, pyarrow reads row group 2 a chunk at a time, then in one
read with `pre_buffer`, and the crate's `ParquetMetaDataReader` asks for the tail it needs with
`NeedMoreData`. The timeline stays, slimmed to one list of the table's strategies.

## Done: ch11 in code

ch11 opens on `row_groups_per_lookup`, which counts the row groups of each `writing-*` file that
could hold `order_id = 431`, and `query_every_file`, which runs `scan` on every file and prints
what it read after the footer. In `writing_with_a_library`, pyarrow rewrites the baseline to the
byte and changes one setting at a time; the crate reads the choices back from each footer. The
writing panel is gone; *Building it* quotes the reader's index fetch and dictionary read.

## Done: ch12 in code

ch12 opens on `a_query_by_hand`, which skips row groups on `order_id`'s minimum, reads two columns
with `read_column` and counts countries, and `run_a_query`, which runs the same SQL through
`engine.run` and prints each stage. In `query_with_a_library`, pyarrow's dataset keeps the same row
groups and groups with `count_all`; the crate keeps them with a predicate and counts its rows. The
engine panel is gone; `pqlab query` stays for the Run buttons.

## Done: ch12 explains what a query engine does

ch12 is now *What a query engine does* (`what_a_query_engine_does`), and, like ch01, explains and
builds nothing: `tools/outline.INTRODUCTIONS` became `EXPLAINERS`, and its test checks that an
explainer quotes no reader code in either language and says what a good answer to each problem
contains. The chapter divides the work between file and engine, recaps what ch08 to ch10 let a
scan skip, keeps `run_a_query` and `query_with_a_library`, and tours projection, filters,
answers from the footer, grouping, sorting with a limit, joins, wide tables and small files. Two
figures replace the answers table: `engine-costs` (what the engine's scan read for nine queries)
and `engine-join` (three build sides' key ranges pushed into a sorted and a shuffled probe side).
`a_query_by_hand`, the engine's quoted code and problems 12.1 and 12.2 are gone; its four
problems are questions. The engine stays in the reader for ch14, ch15, the figures and the tests.

## Done: ch16, what Iceberg adds to Parquet

A last chapter, *What Iceberg adds to Parquet* (`what_iceberg_adds`), explains and builds
nothing. It maps Iceberg's features to the chapters that show them, describes the metadata tree,
hidden partitioning, sort orders and commits, and compares Delta Lake and Apache Hudi. Its step
`field_ids_by_hand` reads the field ids ch15's data files now carry (the generator sets
`PARQUET:field_id`) and resolves a renamed and an added column by id; `field_ids_with_a_library`
reads the ids with pyarrow and the `parquet` crate. The schema report gained `field_id`.

## Done: ch13 in code

ch13 opens on `footer_modes` (`PAR1` or `PARE` at both ends), `keys_by_name` (the key metadata's
JSON found in the raw bytes: three keys in the clear with a plaintext footer, the footer key alone
with an encrypted one) and `one_module` (email's first module: length, nonce, ciphertext, tag). In
`encryption_with_a_library`, pyarrow and the crate open the plaintext footer without keys and fail
on email; the step never asks pyarrow for an encrypted column's metadata, which aborts the process.
The panel keeps its byte map and column table; its see and cannot-see lists are gone.

## Done: ch14 in code

ch14 opens on `list_the_table` (each file's partition and size, from the directories),
`read_the_log` (each `add` and the `order_id` range its statistics record, parsed twice) and
`query_the_table` (`table.query` from the log, each file's decision and every request). In
`table_with_a_library`, pyarrow's hive dataset rules out by path and then by each footer's
statistics, since it does not read Delta logs; the crate walks the directories and reads each
footer. The table panel is gone; `pqlab table` and `pqlab query` stay. The discovery table is one
small table per query.

## Done: ch15's costs in code

ch15 adds `look_up_an_order` (the reader's `changes.lookup`, every request grouped by round trip,
with the snapshot, order and prefetch in the call) and `plan_a_compaction` (`plan_compaction`'s
groups for `after-a-day`). The panel is a lookup (snapshot and order) and its request timeline;
scan, compaction, connections and the tail-read setting are gone from it and from `pl_changes`.
The lookup and scan tables are four columns; the compaction figure keeps only its cost table.

## Done: the problems editor first

- Every Problems section opens with its workbench, where a reader on a phone meets it, rather than
  ending with it several screens below. The per-problem commands are gone: the workbench runs every
  problem and says which fail, and one pair of commands at the end runs them at a desk, in Python
  and in Rust.

## Done: a panel is a picture

- Panels always run on the Rust reader compiled to WebAssembly; the engine choice and "Edit the
  code" are gone, with `web/lab/python.js`, `editor.js` and `python/parquet_lab/browser.py`. The
  Python reader runs in the page in the walkthrough steps, the Run buttons and the workbench.
  `tests/test_python.py` still compares every report and every command through both readers, and
  fails if one is added without a comparison.

## Done: a layout sized by the book

- Ported from the reference book: code or a table that would be cut off at the prose's measure
  takes a 72rem wide column (measured in the page), and what that still cuts off gets an Expand
  button (Back and Escape close it). The outline hides itself when it would crowd the chapter,
  both rails close from the top bar and stay closed, the rails show from 58rem and 72rem, and on
  wide windows they grow into the spare width instead of leaving margins.

## Done: a cover

- `cover.md` is published as index.html (title, tagline, what the book is, a picture of a file's
  bytes in `web/cover-hero.svg`, byline and licences, held to myst.yml by a test); the preface
  moves to preface.html. Resuming from the home screen and the Continue reading link start at the
  cover, and the preface is now remembered like any other page.

## Now: every chapter in the new shape

Where a panel is mainly controls (ch09's mechanisms, ch10's strategies, ch11's writer settings,
ch12's SQL box), make it a code step with the parameters in the call, as ch02 did; keep panels
whose value is a picture (ch02's byte map, ch07's tokens, the request timelines of ch10 and
ch15).

Every chapter from ch01 to ch15 now has its walkthrough by hand and its "Ask a library" step, in
both languages, tested against the manifest. What remains: a query in DuckDB or DataFusion for
ch14, only if it adds something the reader cannot show.

## Trying: Rust compiled in the page

So that a Run button could run the Rust problems' tests on a reader's own Rust.

- **Miri in WebAssembly** ([Rubri](https://github.com/lyonsyonii/rubri), which interprets instead of
  compiling): ruled out. It type-checks the whole reader in about six seconds, but runs it far
  too slowly: chapter 2's problem tests, a second or so natively, had not finished after twenty
  minutes.
- **rustc in WebAssembly** ([rubrc](https://github.com/oligamiq/rubrc), with threads): works.
  With the reader flattened into one file, it compiles the reader and a chapter's real tests,
  and they pass. In headless Chromium on four cores: the reader and its unit tests compile in
  about twenty seconds at opt-level 1, after a download of about sixty megabytes. Under Node,
  the same compiles take about eight to twelve seconds.
- **The trial page**, `rust-trial/` on the published site and linked from nowhere, times every
  step on the reader's own device (`web/rust-trial/`; its toolchain is fetched at deploy time by
  `scripts/fetch-rust-trial.mjs`). Phones are the open question: memory, and whether their
  browsers allow the threads rustc needs.

First result from a phone (Samsung S22 Ultra, Firefox on Android, eight cores): cross-origin
isolation and threads work; the downloads and compiling rustc take about ten seconds on first
visit; hello world compiles in 1.7 s; the whole reader and its unit tests compile in 25 s, and
the 80 tests pass.

To consider, measuring each on the trial page before building it:

- **A Rust Run button for the problems.** Compile the reader once, at deploy time, with rubrc's
  rustc, so a Run compiles only the reader's answer and the chapter's tests against it. Hello
  world's time suggests a few seconds on a phone.
- **Editing the Rust reader in the page**: recompile the reader and the labs' crate (for
  wasm32-wasip1, the page supplying its few WASI calls, checked for the same JSON as the real
  module), swap it into the panels, and show what
  `eprintln!` and `dbg!` print, so a reader can add debugging and watch it. Measure a full
  compile at opt-level 0, and a recompile after a one-line edit with `-C incremental`, the cache
  kept in the page's filesystem between runs.
- **Checking the reader's browser before offering any of it.** Compiling needs cross-origin
  isolation, `SharedArrayBuffer`, `Atomics`, several cores and close to a gigabyte of memory.
  Test what the browser offers (`crossOriginIsolated`, `navigator.hardwareConcurrency`,
  `navigator.deviceMemory` where it exists, `performance.measureUserAgentSpecificMemory()` where
  it exists, and whether a large shared `WebAssembly.Memory` can be allocated and grown) and
  offer in-page Rust only where it can work, with Codespaces otherwise. The trial page should
  record the same checks, and the peak memory a compile used, so the thresholds come from real
  devices.
- **What the Python editor prints.** `print()` in an edited Python reader goes to the browser's
  developer console, which a reader never sees, least of all on a phone. Show it under the
  editor and the lab.

Until then, Rust runs online in a Codespace, and in the page as the prebuilt WebAssembly reader
(`pqlab` Run buttons).

## Then

- A multi-version log with a checkpoint, and time travel between versions.
- Decryption with the published test keys, so ch13's reader can go past where it stops.
- Caching in the ch10 scan model.

## Book infrastructure

- Search across pages (the reference book has one; this one does not yet).
- A figure of the file layout drawn as SVG by code, for readers without JavaScript.
- Hex view virtualisation for fixtures larger than a few kilobytes.
