# Independent learner review: modules 1–8

Reviewer did not author these changes. Applied `/workspace/assembly-lab-review/.agents/skills/learning-design/SKILL.md`, its authoring/review guidance, and parquet-book CLAUDE.md, AUTHORING_GUIDE.md, STYLE.md. Read actual canonical sources and lesson markers, not author audit notes. Assumed only preface prerequisites (tables/rows/columns and a small SQL query; one programming language only for optional code). Agent review is not novice learning validation.

## Source coverage

Read index.md and every section of these canonical sources, including optional implementation, notes, problem statements and linked-library explanations: why_parquet_exists.md; anatomy_of_a_parquet_file.md; the_type_system.md; nested_data.md; encodings.md; pages.md; compression.md; metadata_and_statistics.md. Read tools/lessons.py lesson preparation/boundaries; tools/lesson_practice.py fresh cases/feedback and tools/learning.py byte/length/span/request practice. Read glossary.md and running_the_lab.md; examined generated evidence through rendered pages and selected original fragments. Did not run all coding graders or inspect every underlying reader implementation: this is a learner/terminology review, not a technical implementation audit.

All 29 core lessons covered:

- M1: read-fewer-columns; choose-a-table-layout.
- M2: recognise-parquet; locate-the-footer; read-the-footer-map; trace-footer-requests; choose-a-tail-read.
- M3: follow-schema-paths; interpret-logical-types; count-schema-levels.
- M4: nullable-values; one-list; nested-lists; stored-levels.
- M5: dictionary-values; integer-differences; string-prefixes; split-byte-positions; choose-an-encoding.
- M6: walk-page-boundaries; compare-page-versions; check-page-corruption.
- M7: follow-literals-and-copies; compare-codec-patterns; weigh-compression-costs.
- M8: compare-typed-values; decide-usable-bounds; handle-null-and-float-statistics; account-for-footer-cost.

All 16 optional destinations covered: build-footer-reader; build-schema-reader; build-nested-reader; build-encoding-readers; build-page-reader; build-decompressors; build-statistics-reader; the eight module `*-notes` pages; why-parquet-exists-practice.

## Findings

E1 — Medium, core evidence vocabulary before definition. Original `read-fewer-columns.html` generated CSV/Parquet table had headings “TRAILER AND FOOTER” and “TWO COLUMN CHUNKS”; its introduction defined only footer. Trailer and column chunk definitions first occurred in M2. Those headings divide the byte costs the lesson asks a reader to compare. Direction: explain the two regions locally before the table or use plain labels. Managing author has now added source definitions at why_parquet_exists.md around line 102 (“trailer ... small final block ...”, row group and column chunk); built verification pending final rebuild.

E2 — Medium, core route assumed an optional term. Original `compare-typed-values.html#sort-orders` table used “by value, as a big-endian two’s complement integer”. Two’s complement was defined only in optional build-schema-reader; preface grants no binary encoding prerequisite. Glossary’s original “Learn it” pointed to interpret-logical-types#stored-values-and-their-meaning, which did not teach it. Direction: local explanation sufficient to distinguish numeric and raw-byte comparison; link glossary to the actual teaching location. Author has added a source explanation before the sort table. Explain `2**n` as exponentiation in words for non-code readers (also the existing `2^31` threshold). Built verification pending.

E3 — Medium, glossary search does not recognise lesson spellings. In browser, `RLE`, `BYTE_STREAM_SPLIT`, and `CRC-32` all returned “No matching terms. Try a shorter word or clear the search.” Entries exist under Run-length encoding, Byte-stream split and CRC. A learner copying the exact unfamiliar label from a lesson is told no term exists. Direction: searchable aliases and punctuation normalisation; reuse the aliases used by term linking if possible. Initial build also lacked source additions including Two’s complement; treat that as build staleness, not a missing-source finding.

E4 — Low/medium, optional action lacks a reachable named step. `build-schema-reader.html#optional-schema-damage-investigation`: “The step writes the root’s count of children ... Change it to 0x12 ... run the step again.” That page contains no editable walkthrough for this action. The actual rebuild_the_tree.py listing belongs to count-schema-levels. Direction: name and link the earlier walkthrough and its code disclosure. The mechanism is explained and source code exists; this is discoverability across the new lesson boundary.

E5 — Low, schema notation arrives before its reading key. `follow-schema-paths` displays `REQUIRED`, `OPTIONAL`, `INTEGER(8, signed)`, `DECIMAL(9, 2)`, `TIMESTAMP(MICROS, UTC)` in the first worked result; repetition and tree reading key come later. Signedness and UTC are taught next lesson, but decimal precision/scale parameters are never explicitly decoded on the core route. Direction: tell readers what to attend to now and what type details are deferred; optionally give one short parameter key in the logical-types lesson. Do not require learning every type before following a path. This is a hypothesis about load, not observed novice confusion.

## Concerns rejected against prior teaching

- Null/list distinctions are prepared: follow-schema-paths defines optional as “zero or one ... null, meaning that no value is present”; nullable-values defines scalar/slot/d/r and demonstrates the complete scalar case before fresh practice; one-list then explicitly maps d=0..3 and r. No missing definition finding for these.
- Maximum levels are not silently treated as per-record levels: count-schema-levels says “These are limits set by the schema” and includes one complete shipping.city path. Its fresh required-parent/optional-leaf case applies that counting rule; subsequent actual streams are taught separately.
- RLE versus bit packing is defined before its fresh header exercise: stored-levels explains widths, both run kinds and removing the low bit, then provides a complete RLE miniature and connects it to the fixture’s packed header. No requirement to fully teach multibyte ULEB128 to answer the one-byte core exercise; multibyte parsing belongs to optional implementation.
- Dictionary indices are defined as zero-based before output, and a displayed dictionary/indices/values sequence demonstrates reconstruction before a fresh dictionary. No missing dictionary bridge.
- Delta computation is defined, then demonstrated with a complete first-value/differences sequence before miniblock composition. Negative-delta practice follows the explicit “non-negative excess over minimum” explanation.
- Overlapping copies are defined and demonstrated by a complete XY miniature before real codec tags and the fresh AB case. No need for a second prerequisite activity.
- Conservative bounds are locally defined using ant/antelope/bat before the exactness flags and practice. NaN and signed zeros have local explanations before their relevant final question.
- Checksums are defined before the first page walkthrough and again with the CRC algorithm name; the damage example then demonstrates mismatch. A matching checksum’s limitation is stated before practice. No missing checksum mechanism.
- Binary/hexadecimal numeric reading is explained before the interactive byte question: tools/learning.py adds “Each position is worth sixteen times the position to its right.” Thus merely noting that prose defines the alphabet but not conversion would be a false positive.

## Browser evidence and limits

Used Chromium through installed Playwright at http://127.0.0.1:8020/. Initial build banner: commit 9b82419 (working-tree modifications are not identified by that banner). Canonical sources continued changing during review. Detailed browser log and screenshots are `/workspace/scratch/early-browser-log.json` and `/workspace/scratch/early-*.png`; rendered main text saved as `early-text-*.txt`.

The four-view sweep visits all 29 core, all 16 optional and glossary at 1366×850 and 390×850, in explicit light and dark themes. It measures page horizontal overflow and actual theme/background, and exercises a bold dotted definition-level link with keyboard Enter, Escape and focus restoration in each view. Selected screenshots are visually inspected; visiting every page is not a claim to have visually inspected every screenful, interaction or code output. Full assistive-technology/screen-reader and all code execution checks are outside this review.

Final completion and correction verification will be appended after the sweep/final build.

Completed initial browser sweep: 184 visits (46 destinations × four views). All four requested themes were actually applied; no document-level horizontal overflow. Definition-level lookup opens by Enter, focuses Close, closes by Escape, and restores the initiating link in all four views. Visually inspected all four dialog states plus phone schema/column-layout/glossary screens: legible text, visible focus and contained modal on phone. Initial search failures above reproduced. These checks precede final correction rebuild and do not close E1–E4 yet.

## Final candidate correction verification

Rechecked the rebuilt candidate after the managing author’s final-build signal, using actual rendered main text and interactions. Focused pages: read-fewer-columns, compare-typed-values, follow-schema-paths, interpret-logical-types, build-schema-reader, count-schema-levels (linked target), glossary. Each was visited at desktop 1366×850 and phone 390×850 in light/dark. Evidence: `/workspace/scratch/early-final-log.json`, `early-final-*.txt`, and four `early-final-dialog-*.png` screenshots, all four inspected visually.

- **E1 closed.** The trailer, row group and column chunk definitions now precede the byte-comparison table, explaining its labels before they carry the argument.
- **E2 closed.** The core Sort orders section defines two’s complement before the table and explains exponentiation in words before `2**n`; the earlier `2^31` threshold also has its power gloss. The glossary dialog’s Learn it link now targets `compare-typed-values.html#sort-orders`, the actual core explanation. The explanation teaches how to interpret the term; it does not claim standalone practice of full signed decoding.
- **E3 closed.** All four views show 170 glossary entries. Searching `RLE` finds Run-length encoding; `BYTE_STREAM_SPLIT` finds Byte-stream split (plus one relevant descriptive match); `CRC-32` finds CRC; `prefetching` finds Prefetch (plus two descriptive matches); straight-apostrophe `two's complement` finds Two’s complement and Sign extension. Extra descriptive matches are consistent with the stated search scope and are not failures.
- **E4 closed.** “Open the code for the tree-rebuilding walkthrough” now links to `count-schema-levels.html#schema-level-walkthrough`. Followed the link in every viewport/theme; its real target is the section containing that walkthrough and its code disclosure.
- **E5 closed.** REQUIRED/OPTIONAL/REPEATED definitions and a focus/defer statement precede the first schema output. Precision and scale are explained before DECIMAL parameters appear. Braces, root name and field structure are explained before the textual tree, with a complete optional-binary-country example. Type interpretation remains explicitly assigned to the next lesson, appropriate to this lesson’s path-following outcome.

The final two’s-complement modal is legible and contained in all four states. Enter opens it, Close receives focus, Tab reaches Learn it, Escape closes it and restores the trigger in each state. Body overflow becomes hidden and restores to visible. No document horizontal overflow in the checked final lesson pages.

**Rejected new concern:** an initial immediate scroll measurement appeared to show backdrop wheel scrolling. That measurement included the pending smooth focus-scroll animation. With the trigger scrolled into view and settled first, open/backdrop wheel/close preserve scrollY: phone 2903 throughout, desktop 1995 throughout in the diagnostic run. A follow-up using the normal stylesheet and a settled trigger also confirms no backdrop scroll. This is not an open UI defect.

Decision: retain the definitions, worked examples, fresh cases and glossary lookup; all five findings in this review are corrected and independently checked in the final built candidate. No residual finding from this focused verification. The original limits still apply: this is agent review/browser verification, not observation of novice learning or a complete screen-reader audit.
