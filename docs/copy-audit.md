# Parquet learner wording and interface review

## Opening check

The review starts from the release built from `078a2fd` on the publishing branch `main`.
Its course manifest lists 116 learner routes. It includes 56 core lessons, 16 module indexes,
16 module notes, 13 build labs, 10 navigation and reference pages, three practice pages and two
comparison pages. The two old lesson-list addresses redirect to module indexes. The unlinked
Rust compiler trial is a developer experiment outside the course.

The preface asks readers to recognise tables, rows and columns and follow a small SQL query.
The core course therefore needs visible explanations, worked evidence and reasoning practice
before it refers to byte encodings, implementation code or compiler tooling. The optional
code path adds familiarity with Python or Rust. Local Python and Rust build instructions
belong where the reader chooses to use that toolchain.

Review each route's purpose, question, prepared inputs, action, evidence, interpretation and next
step. Read headings, instructions, captions, examples and feedback in the order learners see them.
Check the controls and precise edits against the working interface. Keep core evidence visible
and group optional source, diagnostics and further inspection under descriptive controls. Check
that execution errors, successful changed results and understanding checks remain distinct.
Follow the original and changed examples, test small and large screens in both colour schemes
and use the keyboard. Preserve drafts kept by previous versions. Report functional evidence
separately from any evidence that learners understood the material.

## Route review

On each core route I traced the outcome and preparation from the page introduction to its worked
example, fresh question and next lesson. I read the optional code, library, build and reference
paths separately. The fixture code, saved results and captions provided checks on factual claims.
On module indexes I checked the lesson descriptions and support links against their destinations.
For each build lab, I checked that the Python editor, Rust source, task statements, runnable
commands and displayed tests refer to the same exercise. For each notes page and comparison I
checked that the preparation links lead to the relevant evidence and that limitations stay next
to central claims on the core route.

| Module and supporting pages | Core pages | Wording and evidence checked |
|---|---|---|
| Why Parquet exists (`why-parquet-exists-notes`, `why-parquet-exists-practice`) | `read-fewer-columns`, `choose-a-table-layout` | CSV and Parquet byte counts use the same UK total. The layout schematic separates contiguous runs from real storage reads. The new column-selection edit retains all fixture rows. |
| Anatomy of a Parquet file (`build-footer-reader`, `anatomy-of-a-parquet-file-notes`) | `recognise-parquet`, `locate-the-footer`, `read-the-footer-map`, `trace-footer-requests`, `choose-a-tail-read` | Opening signature and zero-based offsets lead to the trailer calculation, byte grid and dependent requests. The trace stops at the footer. The request explorer names its controls and fits beside a single no-script comparison table. |
| The type system (`build-schema-reader`, `the-type-system-notes`) | `follow-schema-paths`, `interpret-logical-types`, `count-schema-levels` | Physical and logical types precede their use. The annotated decimal comparison names the changed line, and the malformed schema edit distinguishes a partial traversal from a reader refusal. |
| Nested data (`build-nested-reader`, `nested-data-notes`) | `nullable-values`, `one-list`, `nested-lists`, `stored-levels` | One nullable value precedes null lists, empty lists and nested repeats. The level-stream edit names the column and the `rep` and `def` outputs. |
| Encodings (`build-encoding-readers`, `encodings-notes`) | `dictionary-values`, `integer-differences`, `string-prefixes`, `split-byte-positions`, `choose-an-encoding` | Dictionary indices, delta values, string byte prefixes, byte splitting and size claims each use the actual encoded example or a labelled schematic. Python edits identify the exact selection or decoder input. |
| Pages (`build-page-reader`, `pages-notes`) | `walk-page-boundaries`, `compare-page-versions`, `check-page-corruption` | Page headers and their body lengths precede the V1/V2 comparison. Both changed inputs have named evidence. Intentional corruption reports checksum evidence separately from Python execution status. |
| Compression (`build-decompressors`, `compression-notes`) | `follow-literals-and-copies`, `compare-codec-patterns`, `weigh-compression-costs` | Token order, compressed input, reconstructed bytes and codec limits are visible. The token controls and both compressed and decoded results show where the explanation comes from. |
| Metadata and statistics (`build-statistics-reader`, `metadata-and-statistics-notes`) | `compare-typed-values`, `decide-usable-bounds`, `handle-null-and-float-statistics`, `account-for-footer-cost` | Typed bounds are distinct from null counts and from the absence of statistics. The exact legacy-field and missing-order edits identify the `refused` evidence. |
| Skipping data (`build-pruning-planner`, `skipping-data-notes`) | `rule-out-row-groups`, `map-pages-to-rows`, `test-bloom-membership`, `compose-a-pruning-plan` | The sorted and shuffled fixtures isolate ordering. Candidate groups are distinct from confirmed matches. The Bloom false-positive and page-index examples name actual outputs. |
| How readers read (`build-scan-planner`, `how-readers-read-notes`) | `trace-a-complete-scan`, `choose-a-read-strategy` | The edited scan fixes the query and isolates tail size, merging and concurrency. Byte totals, simulated time and zero-based matching positions have explicit labels and explanations. |
| Writing Parquet well (`inspect-writer-settings`, `writing-parquet-well-notes`) | `compare-writer-layouts`, `choose-writer-settings` | Controlled writer settings keep rows and query fixed. Changed filter tuples compare bytes and requests across layouts, and the comparison distinguishes footer and data cost. |
| What a query engine does (`what-a-query-engine-does-notes`, `what-a-query-engine-does-practice`, `what-a-query-engine-does-comparison`) | `separate-scan-and-filter`, `answer-from-metadata`, `group-dictionary-values`, `limit-a-sorted-query`, `use-join-derived-filters` | Scan and Filter act on different evidence. The metadata count, grouping, sorted limits and join filter cases distinguish candidate rows from answers. |
| Modular encryption (`build-encryption-inspector`, `modular-encryption-notes`) | `read-encryption-modes`, `distinguish-key-names-and-keys`, `inspect-protected-modules` | The plaintext-footer and encrypted-footer views describe the boundaries a keyless reader can inspect. The library edit requests a protected column using a handled table read. |
| Lakehouse and beyond (`build-table-reader`, `lakehouse-and-beyond-notes`) | `read-partition-paths`, `prune-files-before-footers`, `resolve-table-membership` | Path predicates and log statistics account for separate decisions. Named edits compare the file request lines, count and simulated completion time. |
| Changing a table (`build-snapshot-reader`, `changing-a-table-notes`) | `follow-snapshots-and-deletes`, `trace-a-table-lookup`, `compare-update-costs`, `decide-when-to-compact` | Snapshot membership, deletes and compacted files are distinguished. The lookup and compaction edits say which control or input determines the result and which output to compare. |
| What Iceberg adds to Parquet (`what-iceberg-adds-notes`, `what-iceberg-adds-practice`, `what-iceberg-adds-comparison`) | `follow-iceberg-metadata`, `keep-column-identity`, `evolve-partition-specs`, `commit-a-table-change` | The Iceberg metadata and commit examples state their scope as schematics or specification examples. The field ID experiment contrasts the file’s fields with the table view. |

The remaining learner routes are the cover, preface, five part introductions, Running the lab,
The fixtures and Glossary. The cover and preface establish the two reading paths. The part
introductions link to the questions they prepare. Running the lab names the browser controls,
result locations, saved drafts and local command entry points. The fixtures and glossary help
readers resolve unfamiliar file names and terms. The old aliases and the technical trial URL are
included in built link checks.

## Closing check

The core explanations, initial worked results and next lesson links remain visible with the code
closed. The visible experiment guidance identifies the prepared input, controls, changes and
result fields. Core questions ask learners to interpret evidence. Answers and diagnostics open
when useful. The read path also works without scripting. In the optional editor path, a successful
modified run keeps its own result label. A later execution error leaves the previous result
visible. The workbench says which source it checked, and a separate warning reports when the
browser cannot save an edit. Older exercise drafts still load and restoring a starter retains a
recovery copy. The Stop control cancels the run attached to it, including when another run has
already started.

### Functional evidence

The browser sweep follows ordinary lesson routes and opens the code using the keyboard. It ran
all 61 original Python walkthroughs in Chromium. The browser results matched the saved desktop
output except for three expected pyarrow differences. The browser fetched a different number of
bytes in the column scan while reporting the same total, printed the same UTC timestamp under a
different timezone label, and issued individual chunk reads where the desktop library could merge
them. The relevant lessons now describe those differences beside the result.

Exact input variations were also run with native Python and the browser's Python runtime.
Examples include the V2 page layout, a change from country to amount, false-positive Bloom
membership, missing sort-order information, two sizes for a simulated tail read, a deleted order
and a field ID reused for a different column name. These actions produce evidence readers can
compare with the original outputs. The WebAssembly panels come from the same reader the native
checks exercise. For Rust walkthroughs, the checks run the native programs and verify the
browser's Codespaces command handoff locally.

A separate Chromium pass covers narrow and wide layouts, light and dark themes, keyboard
controls, byte validation and restore, and the no-script request table. Browser tests exercise
both storage migration and the blocked-save case. The public version, once deployed, is checked
against the same layout, example and recovery flows.

### Evidence of learning effectiveness

No learners participated in this review. The evidence verifies that the directions, interfaces
and sample outputs work. It does not measure whether readers can explain the concepts unaided or
transfer them to their own data.
