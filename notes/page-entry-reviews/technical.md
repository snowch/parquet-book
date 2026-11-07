# Independent technical and sceptical review: standalone page context

Branch: codex/standalone-page-context. Reviewer: independent Codex agent, inherited model configuration. I did not draft or edit these changes and did not read draft reports/rationale. I used the previously read learning-design skill and authoring-review guidance, then read current AUTHORING_GUIDE.md and STYLE.md. This review is not learner validation or full accessibility certification.

## Baseline inspected

I read the actual built main content of all sixteen `*-notes.html` pages and both `*-comparison.html` pages, then the relevant chapter partitions, renderer/support-page code, and implementation/specification evidence. Extracted baseline text is saved under /workspace/scratch/context-review-pages/. The initial build identifies commit 9b82419. No draft rationale was used to interpret these pages.

Browser baseline: Chromium at http://127.0.0.1:8020, service workers blocked; why-parquet-exists-notes.html at 1440×1000 light, and what-iceberg-adds-comparison.html at 390×844 dark. I inspected actual main text and hrefs; screenshots are context-initial-why-desktop.png and context-initial-iceberg-mobile.png. The other initial pages were inspected as generated HTML/source, not falsely claimed as individual browser visits.

## Supported findings raised to the root

### 1. Medium: miniature and real-file evidence are detached in Why Parquet exists notes

Location: why-parquet-exists-notes.html, What this cannot tell you / Key takeaways; canonical chapters/why_parquet_exists.md reference partition.

The page says “The two layouts above” and “The counting files” without including either experiment or a link to its actual lesson. Its one-range-versus-one-per-row conclusion is from the small layout schematic, while the file-transfer statements come from counted library reads of real CSV/Parquet fixtures. Detached context makes the schematic sound like the physical request plan for all Parquet readers. Browser links initially went only to broad modules; no local evidence link supplied these missing subjects.

Correction direction: name the row/column layout miniature and the actual counted-file comparison separately, briefly state their setups, and link each to its owning lesson. Keep real transfer differences and simulated/ideal range counts separate.

### 2. Medium: Iceberg comparison references point to absent teaching material

Location: what-iceberg-adds-comparison.html, A map of the features and its following paragraph.

“Shown in” says “Here” for metadata trees, schema evolution and hidden partitioning, but those mechanisms are on separate core lesson pages. “Beyond this book” for commits/catalogs overlooks commit-a-table-change.html. “The rest of this section takes the rows in order” describes the old combined chapter, not this published page. Confirmed in the mobile browser table.

Correction direction: link the actual lesson for each feature. State which rows this comparison expands, and distinguish schematic specification descriptions from the book's simplified executable table.

### 3. Medium: selected writer results become universal layout rules

Location: writing-parquet-well-notes.html, Key takeaways (and any corresponding edited recommendation).

The initial page says a sorted-key lookup reads one row group, other columns nearly all, and “Small row groups ... help only a sorted column.” The fixture has unique ordered identifiers and customer values distributed throughout groups; arbitrary data can have duplicates across boundaries or narrow bounds without a globally sorted column. The checkpoint itself correctly recognises useful ranges in another column.

Correction direction: scope the measured conclusions to the named fixtures and query, and express the general mechanism in terms of bounds/range clustering rather than sortedness as a necessary condition.

### 4. Medium: dependency barriers become an object-store rule

Location: how-readers-read-notes.html, “Connections overlap requests within a phase, never across phases.”

python/parquet_lab/object_store.py TracingStore.next_phase sets a global barrier for this teaching scheduler. The source explicitly describes its phase policy; concurrency does not require every production reader to wait on unrelated requests before starting work whose dependencies have arrived.

Correction direction: say this model/reader overlaps requests within phases and waits at phase boundaries. Keep true dependency requirements distinct from the model's chosen global barriers.

### 5. Medium: encryption visibility needs its footer-mode qualification

Location: modular-encryption-notes.html, Key takeaways, “Encryption hides values, not shape. Sizes, page counts and page lengths remain visible.”

The same page says an encrypted footer hides the layout. python/parquet_lab/crypto.py encrypted_footer reads crypto metadata and the encrypted footer module; it cannot identify all columns/pages without the footer key. Plaintext-footer fixtures permit more structural inspection. A broad visibility claim stripped from its example can reverse the mode distinction.

Correction direction: identify what remains visible in each mode and link the inspection lesson. Do not treat the plaintext-footer structural view as the view of every encrypted file.

### 6. Medium: Iceberg-specific claims need the book's example scope

Location: what-iceberg-adds-notes.html Key takeaways and comparison opening.

Initial notes say every Iceberg data file is Parquet and added columns read as null from older files. Iceberg supports Avro/ORC data files as well, and a field's initial-default can govern values for older rows. Current spec explicitly permits an Avro default write format and defines initial-default semantics (saved upstream snapshot /workspace/scratch/terms-specs/iceberg.html, Default values and file_format).

Correction direction: say this book follows Iceberg with Parquet files, and scope the null example to the demonstrated optional field without a non-null default. Naming the example is preferable to presenting these as format invariants.

### 7. Medium: a lost optimistic commit race does not necessarily discard compaction work

Location: changing-a-table-notes.html, Concurrent writers.

Initial text says a compaction losing the race “has done all its work for nothing.” Iceberg's commit conflict resolution permits retry/reuse when the rewritten files remain valid; the spec gives precisely this rewrite example. The teaching store has no concurrent writers and supplies no evidence for mandatory wasted work.

Correction direction: distinguish a failed pointer update from incompatible data changes; explain validation and retry, and say incompatible work may need recomputation.

### 8. Medium: footer accounting needs reader/cache scope

Location: metadata-and-statistics-notes.html, Key takeaways, “Every statistic is read by every query before any data.”

The book's uncached metadata reader establishes a metadata cost. It does not establish that cached metadata or table-level file pruning must reread every statistic, nor that a tail prefetch cannot bring data with its metadata. This overgeneralisation becomes particularly exposed on a standalone notes page.

Correction direction: describe this reader's uncached opening path and say footer transfer/decoding can be a cost, while linking the footer-cost example.

### 9. Medium: a simplified log fixture is described as a full Delta history

Location: what-iceberg-adds-comparison.html, Delta Lake paragraph.

The initial text says the numbered per-commit Delta transaction-log directory is “which ch14 read.” The implementation and fixture use a single simplified log, not the full checkpoint/multiple-version protocol. The original chapter's qualification is absent from the comparison.

Correction direction: name the table-format specification as the source of full-protocol claims and say the earlier lesson demonstrates selected add/remove behavior using a simplified fixture, with a direct link.

## Baseline observations across all notes

All sixteen notes initially used a generic “Supporting material for this module's lessons” prerequisite. The following detached phrases were read in generated content, not inferred by a keyword-only scan:

- Anatomy: “the footer you decoded here,” unnamed chapter fixture scope.
- Types: “This chapter computes their maximums,” “the fixture,” and an outgoing link relying on the maxima “you computed here.”
- Nested: “as pyarrow showed for one list” with the library comparison on another page.
- Encodings: “the savings in the table” with no table in notes.
- Pages: “Every page here is uncompressed” although the page itself contains no inspected pages.
- Compression: “Their sizes are measured here” and a BYTE_STREAM_SPLIT comparison lacking a named source lesson.
- Metadata: “the fixture catches every one” without naming the fixture.
- Skipping: sorting comparisons and mechanism costs need the named sorted/shuffled files and absence-test example.
- Reader strategies: model is identified, but no direct pointer to the request trace and model configuration.
- Writer settings: “as the first step printed,” with that step absent.
- Query engine: “the table,” “join table,” and “Every number here” on a notes page containing none of those comparisons.
- Encryption: module/key claims need named fixtures and inspection-only reader context.
- Lakehouse: “Nine small files ... the three ways” without naming the discovery comparison.
- Changes: “This table,” snapshots written/compacted and “the library step” need named fixture/context links.
- Iceberg: “the step resolves” and “the book's table” need the schematic versus executable-example distinction.

These observations support local context fixes, not duplicating every whole lesson or forcing a prior sequence. Final verification will assess the actual edited prose rather than treating every occurrence of “here” as a bug.

## Renderer review and rejected concerns

I reviewed tools/render.py _xref: only recognised chapter-root shorthand is replaced with target.title; explicit informative labels remain unchanged. Existing target and link-migration behavior is unchanged. tests/test_render.py passed all 9 tests. This change improves labels but cannot replace missing example context or point a broad module URL to specific evidence on its own.

Rejected: a notes page must repeat the whole lesson or add a new worked task. A short local setup, appropriately scoped conclusion and usable direct evidence link can make reference material coherent. Rejected: every forward reference or “here” is necessarily detached; it is a defect only when its subject/evidence is missing from the actual published destination. Rejected: the query-cost table has no measurement provenance; its generated condition line already names writing-baseline.parquet, rows/columns/groups, and what bytes/values count. A better introductory setup is still useful. Rejected: a change to _xref inherently breaks fragments; recognised root chapter links already had their existing destination behavior, while ordinary explicit section links follow the other path.

## Pending final patch review

Drafting is active. No merge recommendation is made from the baseline alone. Await the stable final patch/build, then reread changed claims and inspect representative built entry routes and direct links. No learner-validated claim is supported by this review.

## Final candidate verification

Reviewed the actual final source patch and served output independently of drafting notes. All nine findings above are resolved; no unresolved technical or engineering blocker remains in this review's scope.

1. **Closed — real versus schematic evidence.** `chapters/why_parquet_exists.md:218` now distinguishes the real CSV/Parquet byte-read comparison from the layout schematic, names their evidence limits, and links the actual examples. The standalone notes render with an example-specific title and two preparation links. The column-layout conclusion is about contiguous selected values, not a universal storage-request count.
2. **Closed — Iceberg feature map and preparation.** The comparison now links each actual lesson, includes commits among covered responsibilities, and distinguishes the schematic Iceberg tree from executable file/reader examples. No claim that all prior material reads rows in order remains.
3. **Closed — writer-layout conclusions.** Notes now tie outcomes to the named sorted/shuffled fixtures and tested ranges. Sorting is not presented as the only way small groups can help, and a sorted lookup is not promised to touch one group for every predicate.
4. **Closed — scheduler scope.** The reader notes identify the teaching reader/model policy behind dependency barriers; they do not impose the demonstration's scheduling choices on all readers.
5. **Closed — encryption leakage scope.** `chapters/modular_encryption.md:466` and its takeaway at line 495 distinguish readable structural information in plaintext-footer mode from the more limited visible framing in encrypted-footer mode, with named inspection fixtures and links.
6. **Closed — Iceberg format/default scope.** `chapters/what_iceberg_adds.md:277` and the notes acknowledge Avro/ORC as well as Parquet. The old-row null example is qualified by the field/default setup; it is not the general outcome of every added column.
7. **Closed — commit retries.** `chapters/changing_a_table.md:320` and line 549 describe validation, possible retry/reuse or recomputation, and identify the absent concurrency simulation. They no longer promise all work is wasted after any lost pointer race.
8. **Closed — metadata costs.** The metadata notes scope the opening path and cache implications. A repeated broad formulation found during final review in `chapters/what_a_query_engine_does.md:359` was also corrected: the served comparison now says opening an uncached file requires metadata and compaction reduces per-file overhead rather than eliminating all costs.
9. **Closed — Delta example scope.** `chapters/what_iceberg_adds.md:331` names the earlier single simplified log example and separates it from the full multi-version protocol.

The source pass covered all sixteen chapter patches, both optional comparisons, the changed preface/part/appendix material, and metadata/renderer/test/doc changes. Named fixtures and direct evidence links now replace the baseline detached setup references. Source/model/spec checks supporting the corrections are described above; this is not an independent implementation of every external table format.

### Engineering checks

- `tools/lessons.py`: resource-specific titles, goals and prerequisite links use the existing route catalogue. Prerequisites are escaped when emitted. The new defaults preserve callers without prerequisite metadata. Reference resources describe their actual purpose instead of pretending to be another worked lesson.
- `tools/render.py`: shorthand replacement uses destination titles and keeps custom descriptive labels and existing href handling. It does not change the fragment routing mechanism.
- `tests/test_render.py` and `tests/test_lessons.py`: **39 passed** on the final candidate. The only warning is an installed anyio/pytest API deprecation, unrelated to these changes.
- Reviewed browser smoke additions for all optional-resource routes, responsive widths, metadata headings and keyboard entry navigation. The documentation additions require examining published URLs and model scope rather than treating source-file proximity as context.

### Actual browser evidence

Independent Playwright script `/workspace/scratch/context-review-final.cjs` passed against `http://127.0.0.1:8020`:

- All **18 notes/comparison pages** loaded at 1440px/light; their visible heading matched their course metadata, preparation links existed, and every local main-content href returned 200 with any requested fragment present.
- All 18 pages also passed the document-width/reflow check at **390px/dark**. No page JavaScript errors were observed. I visually inspected the phone notes and Iceberg-comparison screenshots; the new local setup, useful labels and preparation links are visible and readable.
- Keyboard activation of the first chapter notes' evidence link opened `read-fewer-columns.html`, where the worked example is actually present.
- Representative pre-existing canonical chapter/heading URLs redirected to the intended split lesson and preserved the original anchor: `why-parquet-exists.html#one-table-two-layouts`, `anatomy-of-a-parquet-file.html#locate-the-footer`, `nested-data.html#two-lists-deep`, and `encodings.html#byte-stream-split`.

A separate final browser check `/workspace/scratch/context-review-front.cjs` inspected the changed preface, four part openers and both appendices at 390px/dark. All **94 local main-content links** resolved with fragments present, no bare `chNN` link labels remained in those pages, and no horizontal document overflow or page JavaScript error was observed. It also confirmed the final uncached-opening caveat is present in the served query comparison.

Artifacts: `/workspace/scratch/context-review-pages/final-*.txt`, `/workspace/scratch/context-final-why-desktop-light.png`, `/workspace/scratch/context-final-why-mobile-dark.png`, `/workspace/scratch/context-final-iceberg-mobile-dark.png`.

### Limits and disposition

Accept the corrections and engineering changes for the stated standalone-entry task. Reject a remaining-blocker claim based solely on a repeated term, a cross-reference, or a schematic: the final pages name the relevant example and its limitations and give usable evidence routes. Rejected the suggestion that all chapter content must be duplicated on every optional page; the concrete local setup and links solve the identified detached context without that duplication.

This is a technical/source/browser review. It does not establish novice learning outcomes, complete assistive-technology certification, or correctness of external format implementations beyond the checked claims.
