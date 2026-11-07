# Independent learner review: modules 9–16

Reviewed 2026-11-07. Reviewer did not author or edit the material and did not consult author audit notes or rationale. Used the learning-design skill in `/workspace/assembly-lab-review/.agents/skills/learning-design/SKILL.md`, its authoring rules, and parquet-book CLAUDE.md / STYLE.md. This is an agent review, not novice validation or evidence of learning. No repository files were changed.

## Scope and evidence

Read the complete canonical chapter sources `skipping_data.md`, `how_readers_read.md`, `writing_parquet_well.md`, `what_a_query_engine_does.md`, `modular_encryption.md`, `lakehouse_and_beyond.md`, `changing_a_table.md`, and `what_iceberg_adds.md`, including optional build, limits, takeaways, feedback, comparisons and problems. Read actual lesson markers and the routes/preparation in `tools/lessons.py`; read all generated worked-result output in their built pages, and selected generated tables relevant to findings. Read preface prerequisites (`index.md:92–97`): tables/rows/columns and following a small SQL query; programming and Parquet internals are not assumed. Checked earlier teaching where rejecting a potential gap.

Build log `/workspace/scratch/terms-build.log` reports a successful 116-page build. Browser inspected server `http://127.0.0.1:8020/`, whose pages displayed commit 9b82419. Source can be changing concurrently; findings below refer to the inspected wording and saved browser evidence.

All 45 scoped destinations (27 core, 18 optional) were loaded in Chromium at 1365×900/light and 390×900/dark. This is a route/render/overflow check, not 90 individually scrutinised screenshots. No document-level horizontal overflow occurred. Actual visual inspection: Bloom desktop/light and phone/dark; page overlap phone/light and phone/dark; Iceberg tree desktop/dark; glossary phone/dark; Bloom definition dialog phone/light. Saved text and screenshots are `/workspace/scratch/terms-built-*.txt` and `/workspace/scratch/terms-*.png`; checks are in `terms-late-browser.json` and scripts `terms-late-browser.mjs`, `terms-late-extra.mjs`.

## Findings

### L1 — medium: “round trip” changes meaning inside the table lookup trace

Location: `chapters/changing_a_table.md:145–148,165–169`; built `trace-a-table-lookup.html`, first worked result; walkthrough `look_up_an_order.py` output.

Evidence: introductory prose says requests are “grouped by round trip: the requests in one round trip go out together”. Printed “round trip 2” contains four delete-file requests ending at 40 ms and the trailer ending at 60 ms. Printed “round trip 5” contains requests ending at 120 and 140 ms. These are dependency phases that can occupy multiple connection rounds. Module 10 has already taught independent requests, connection limits, and the distinction between phases and parallel connections.

Learner effect (hypothesis): a reader cannot reconcile “go out together” with the displayed staggered completion times and may treat a dependency phase as one latency payment irrespective of connection capacity. That undermines the lesson's explanation of lookup cost.

Correction direction: call these groups phases, distinguish phases from rounds required when requests exceed the available connections, and align the prose and printed labels. Preserve the dependency explanation. This is a local explanation/label repair, not a request for a new activity.

### L2 — low: Bloom result needs a key for its pair notation and local bit numbering

Location: `chapters/skipping_data.md:176–188`; `test-bloom-membership.html`, first worked output.

Evidence: prose introduces “eight 32-bit words” without saying that a word here is a group of bits. Output then prints `bits [(2, True), (23, True), (24, False), … (24, True), (24, True), …]`. It does not explain that each pair gives a bit position and whether it is set, and that successive pairs refer to successive words. Thus “24” can visibly be both False and True in one block. Preface says output uses Python notation, but that is not an explanation of this representation.

Learner effect (hypothesis): a reader who understands the conceptual absence test can still fail to verify its evidence, especially when the output wraps on a phone. The conceptual fresh case is adequately prepared, so this is not a blocker to that case.

Correction direction: before the output, define word as the relevant group of 32 bits and explain pair order/local numbering plus True=set/False=clear. A short legend suffices; an extra interactive is unnecessary.

### L3 — low: wrapped data keys appear before their distinction from readable keys

Location: `chapters/modular_encryption.md:115–147`; `distinguish-key-names-and-keys.html`, first worked output.

Evidence: opening says “Neither file holds a key”, then the result labels long strings “wrapped data key”. The next paragraph uses “the data key was wrapped once or twice”; only after that does the envelope-encryption paragraph define data keys, wrapping, master keys and `wrappedDEK` as encrypted key material.

Learner effect (hypothesis): the first result appears to contradict the opening until the learner reaches the later explanation. This is a definition-before-example ordering lapse, not a missing explanation overall.

Correction direction: move the existing data-key/wrapping explanation before the result, or add a concise advance definition that the string is an encrypted key and does not grant access to its readable secret. Retain the toy-service limitation.

## Explicit core coverage: defined, demonstrated, practised

All listed core pages were read in source and loaded in both baseline browser configurations. “Practice” here means a fresh prompt exists and is prepared by the page; it does not mean a person demonstrated mastery.

| Module / lesson slug | Preparation, worked bridge, fresh application |
|---|---|
| 9 `rule-out-row-groups` | Predicate/pruning defined; sorted/shuffled bounds worked; inside/outside-range question. |
| 9 `map-pages-to-rows` | ColumnIndex/OffsetIndex and projection defined; real index plus complete `[2,4)` overlap miniature; fresh `[3,5)` overlap question. |
| 9 `test-bloom-membership` | Bits/hash/collision/membership defined; real filter probe and false-positive explanation; set/clear-bit application. L2. |
| 9 `compose-a-pruning-plan` | Combines the three preceding mechanisms; plan and cost tables; Bloom rejection versus retained statistics/latency application. |
| 10 `trace-a-complete-scan` | Scan/latency/connection/coalescing/concurrency defined; complete request trace and phase timeline; known/unknown offset dependency question. |
| 10 `choose-a-read-strategy` | Earlier trace supplies concrete plan; strategy/network comparisons and bandwidth definition; changed-network application. |
| 11 `compare-writer-layouts` | Point lookup/selectivity defined; controlled files, query results and byte chart; confounded comparison question. |
| 11 `choose-writer-settings` | Prior controlled comparison supplies evidence; setting consequences and cardinality defined; changed query mix question. |
| 12 `separate-scan-and-filter` | Plan/scan/filter/projection/pushdown/aggregate defined; complete stage trace and figure; candidate-group versus matching-row application. |
| 12 `answer-from-metadata` | Earlier count output demonstrates metadata answer; exact/missing/filtered limits explained; filtered count question. |
| 12 `group-dictionary-values` | Grouping defined; two locally numbered dictionary miniature; reversed fresh dictionaries. |
| 12 `limit-a-sorted-query` | Top-k defined; concrete sorted/unsorted query comparison; bounded memory versus stop-proof question. |
| 12 `use-join-derived-filters` | Join/inner/hash/build/probe/dynamic filter defined; range-based scan table; gap between actual keys question. |
| 13 `read-encryption-modes` | Plaintext/ciphertext/key/module defined; real magic and visibility tables; readable schema versus encrypted column question. |
| 13 `distinguish-key-names-and-keys` | Key metadata and envelope scheme explained; real names/wrapped material; name-versus-permission application. L3. |
| 13 `inspect-protected-modules` | Length framing/nonce/tag prepared; complete module layout and byte result; locating versus authenticating question. |
| 14 `read-partition-paths` | Partition/path contract and object key/prefix defined; directory listing plus absent column example; fresh FR/city case. |
| 14 `prune-files-before-footers` | Table format/log/actions defined; log output and complete query; surviving path but excluding bounds case. |
| 14 `resolve-table-membership` | Membership/commit defined; complete add/add/remove/add history; fresh east/west/orphan history. |
| 15 `follow-snapshots-and-deletes` | Snapshot/position delete defined; small before/after history then real delete row; earlier-snapshot question. |
| 15 `trace-a-table-lookup` | Earlier snapshot/file/page preparation; full trace and key-value comparison; one row versus many requests. L1. |
| 15 `compare-update-costs` | Copy-on-write/merge-on-read and amplification explained; rewrite/delete figure and cost tables; read-heavy workload application. |
| 15 `decide-when-to-compact` | Compaction defined previously and restated; grouping output and measured break-even table; no-future-reads and retained snapshots case. |
| 16 `follow-iceberg-metadata` | Catalog/metadata/list/manifest defined; complete shared-branch schematic; branch exclusion question. |
| 16 `keep-column-identity` | Schema evolution/stable ID defined; real rename/add/reuse worked results; dropped-name/reused-name case. |
| 16 `evolve-partition-specs` | Hidden partitioning/spec/transform defined; old-day/new-hour scenario; fresh day-to-month question. |
| 16 `commit-a-table-change` | Atomicity/optimistic concurrency defined; ordered prepare/publish/check/retry narrative; two stale-base writers case. |

Small-example check: the real filters and table traces are larger than minimal toy inputs, but they are preceded by mechanism definitions or earlier full traces. The explicit page-overlap, local-dictionary, membership-history and snapshot miniatures are useful bridges and should stay. No need to add a separate activity for each term. Commit and partition-evolution lessons demonstrate via short complete prose scenarios; they do not run a catalog or a real Iceberg tree, and say so. The proposed Bloom fix improves notation without shrinking the real implementation silently.

## Optional coverage

All 18 optional pages were included in source review and browser route checks, rather than excluded as non-core:

- Module 9: `build-pruning-planner`, `skipping-data-notes` — bounds/filter/page implementations, coding problems, repeated-column and combined-condition limits.
- Module 10: `build-scan-planner`, `how-readers-read-notes` — merge/fetch/connection clock code, problems, caching/network/decode limits.
- Module 11: `inspect-writer-settings`, `writing-parquet-well-notes` — settings/index/dictionary code, layout problems, fixture-scale and writer-cost limits.
- Module 12: `what-a-query-engine-does-notes`, `what-a-query-engine-does-practice`, `what-a-query-engine-does-comparison` — engine limits, all four reasoning problems, wide/small-file and query-cost comparison.
- Module 13: `build-encryption-inspector`, `modular-encryption-notes` — module parsing/refusal, footer-mode problems, decryption and access-control scope.
- Module 14: `build-table-reader`, `lakehouse-and-beyond-notes` — percent-encoding defined before path parser, action replay and type checks, path/log problems, real-log and concurrency limits.
- Module 15: `build-snapshot-reader`, `changing-a-table-notes` — delete/lookup implementation and compaction stubs, alternative deletes, concurrency, expiry/time travel and write costs.
- Module 16: `what-iceberg-adds-notes`, `what-iceberg-adds-practice`, `what-iceberg-adds-comparison` — limits, all four reasoning problems, Delta/Hudi feature comparison and explained timeline/file-group vocabulary.

Coding excerpts and graders were inspected as teaching destinations and prerequisites, not executed or independently proven correct. Optional Python/Rust knowledge is reasonable on the chosen build route; it is not smuggled into the essential route as a requirement to run code.

## Challenged/rejected candidate findings

- “Hash appears unexplained in hash joins”: rejected. `skipping_data.md:169–174` defines hash and collision on the earlier core route; `what_a_query_engine_does.md:295–299` defines hash table/build/probe locally. The dynamic-filter task needs conservative range reasoning, not implementation of a hash join.
- “Half-open overlap notation is unprepared”: rejected. Module 2 teaches half-open byte spans and the page-index lesson explicitly works which two rows `[2,4)` includes before its fresh case. No requirement to repeat the entire notation course.
- “Repeated data is silently treated as row counts”: rejected for the inspected core route. Page lesson explicitly limits this planner to non-repeated columns before the miniature and task.
- “Bloom collision/false-positive result is a definition without a mechanism”: rejected. Bits/hash and combined overlapping bit selections are explained before the probe, and the nonmember false positive is described afterwards; L2 is about decoding the displayed notation, not missing Bloom semantics.
- “Compaction problem requires snapshot retention only hidden in optional notes”: rejected. Core `resolve-table-membership` explains keeping replaced files readable and the before/after snapshot lesson demonstrates that old readers still see the old row. Optional notes add the term time travel and expiry mechanics.
- “Schema evolution assumes IDs before defining them”: rejected. The tree lesson locally calls field ID a stable number, and the identity lesson defines never changing/reusing IDs before its result. Added nullable-field default limitation is explicit on the core page.
- “Full AES or Avro implementation must precede encryption/tree tasks”: rejected. AES-GCM is explained at the needed encryption/authentication level; the tree lesson describes Avro as a row format. Tasks require visible structure and pointers, not implementing those formats.

## Access and decision

Keyboard Enter opens the inline Bloom glossary definition; Escape closes it and restores focus to the originating term. A phone click opens a 350 px-wide dialog within a 390 px viewport; the labelled close button works. Glossary search for Bloom reports six matches, a nonsense query announces no matches, and clearing restores 129 terms. The answer disclosure opens with keyboard Enter. Visible text, focus outline and underlined links were legible in inspected light/dark screenshots. No screen-reader, touch-device, zoom, full keyboard traversal, or exhaustive contrast audit was performed; no claim of complete accessibility follows from these checks.

Keep the current short lesson route and explicit miniature bridges. Correct L1's phase/round-trip vocabulary and the two local representation/ordering issues. No high-severity missing-prerequisite blocker was found across this scope. Whether target learners can independently apply the mechanisms remains untested with people.

## Focused final verification — 2026-11-07

Re-read the corrected sources and current built pages after the final candidate build. L1, L2 and L3 are resolved for this learner review.

- **L1 resolved.** `changing_a_table.md:148–152` defines a dependency phase before the trace, states the connection limit, and says that a phase can contain more than one network round trip. The explanation after the trace explicitly says requests in a phase need not start together. Both `look_up_an_order` walkthrough sources now print `phase`, and the rebuilt result shows phases 1–5 while retaining the previously inspected 40/60 and 120/140 ms staggered timings. The generated comparison header is “Dependency phases (requests)”. Source inspection confirms both native/Python report fields are `dependency_phases`. I also waited for the browser's live changes panel to reach `data-state=ok`: it rendered “5 dependency phases, 16 requests, 24,093 bytes”, with `data-dependency-phases=5`. This resolves the contradictory vocabulary without claiming that connections remove dependencies.
- **L2 resolved.** The Bloom result now has a preceding legend defining each `(position, True/False)` pair, distinguishing positions local to different words, stating zero-based positions, and explaining True=set/False=clear. It explicitly says equal positions in different pairs are different bits. That supplies the missing interpretive bridge for the duplicated 24 values. The legend and result remain readable at phone width.
- **L3 resolved.** The key lesson now begins “Neither file holds a plaintext encryption key”, allows protected key material in key metadata, and defines envelope encryption, data key, key-encryption/master key and wrapping before the first output. The wrapped value is explicitly distinguished from its readable secret before it appears. The apparent contradiction is removed.
- Also inspected the snapshot wording in `follow-snapshots-and-deletes`: it now says table formats track table state but metadata/delete representations differ, and identifies the one-JSON-file representation as this teaching fixture. The earlier exact-equivalence language is gone.

Verification browser scope: the three affected lessons loaded at 1365×900/light and 390×900/dark without document overflow. Read current DOM text and result ordering in all six loads; visually inspected the final phone/dark Bloom result and desktop/light key lesson screenshots. Inspected the live dependency-phase label as described above. Artifacts: `/workspace/scratch/terms-late-verify.json`, `/workspace/scratch/terms-final-*.png`, and `/workspace/scratch/terms-final-phase-panel.png`. No code execution/parity suite was rerun by this reviewer; the checks here establish the displayed teaching sequence and labels, not independent technical validation of unchanged scheduling semantics.

Final learner-review decision: no outstanding L1–L3 findings, and no new prerequisite blocker found in this focused check. Original coverage limitations and absence of human novice evidence still apply.
