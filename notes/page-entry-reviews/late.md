# Independent learner/UX review: standalone destinations, chapters 9–16

Final disposition: no unresolved substantive cold-entry/context finding. One low-severity ambiguous column-name antecedent was reported and corrected; final rendered verification passed. This is expert learner/UX review, not novice-user validation.

## Scope and method

Read the actual eight chapter sources, lesson boundaries, preparation/link catalogs and built destination text. Applied `/workspace/assembly-lab-review/.agents/skills/learning-design/SKILL.md`, repository `CLAUDE.md` and `STYLE.md`. Assumed the stated preface prerequisites, but evaluated entry directly from contents with no preceding page visible. Did not author repository changes, read author rationale, or edit repository files.

Coverage is 53 published destinations: 8 chapter indexes, 27 core lessons, 6 optional build/library pages, 8 notes pages, 2 practice pages and 2 comparisons. Every row below had source plus rendered-text review, and automated direct browser visits at 1365×900 and 390×900 in light and dark (212 visits). No document-wide horizontal overflow was detected. All 82 unique internal main-content HTML/fragment targets were opened; none had missing fragments. This link-resolution check is distinct from the semantic preparation evidence below.

All 212 viewport screenshots were saved; manually inspected the 14 views explicitly recorded in the table. Unmarked rows were not individually visually inspected, and saved screenshots alone are not claimed as visual review. The inspection covered title/subject, goal/preparation visibility, links and opening body legibility across both widths/themes. Final two edited pages received another 8 browser visits after the final rebuild; all four configurations remained free of document overflow. The rendered footer identifies commit 60370bb; this candidate includes working-tree changes, so commit ID alone is not its complete provenance.

Artifacts: `context-late-visits.json`, `context-late-links.json`, `context-late-targets.json`, `context-late-text/`, `context-late-images/`, `context-late-final.json`, and `context-late-interactions.json` under `/workspace/scratch/`.

## Findings and final closure

**L-C1 — low, corrected:** `chapters/what_iceberg_adds.md:137`, published `keep-column-identity.html`, prose immediately after field-ID output. Candidate said: “order_number is id 1, so it reads the file’s order_id, although no file has a column of that name.” The nearest named column was `order_id`, which the fixture does contain. Correction direction: spell out requested table name. Final source and browser now say “although the file has no column named order_number.” Verified after final rebuild at both widths and both themes.

**Targeted technical-qualification closure:** `chapters/what_a_query_engine_does.md:359`, published comparison. Final rendered wording says “Opening an uncached file requires fetching and decoding that metadata before planning its data reads”; the small-file discussion acknowledges overlapping requests and table-statistics pruning. It says compaction “reduces this per-file overhead; it does not eliminate metadata or reading costs.” The cost table explicitly names the teaching engine and `writing-baseline.parquet`; its footer-first caption is consequently scoped to that experiment. Revisited all four configurations after final rebuild; closed.

Earlier potential detached references in key metadata, the encryption build, file-pruning and Iceberg feature-map pages were not retained as final findings: actual final text now names the fixtures/subject and links the owning worked example, as the rows document.

## Semantic preparation and link evidence

These checks inspected destination teaching content, not merely HTTP status:

- `decide-usable-bounds.html` defines conservative versus exact bounds and shows typed bound outputs, including missing statistics; `handle-null-and-float-statistics.html` distinguishes all-null counts from absent statistics and explains NaN/signed zero. These prepare pruning and metadata-only answers.
- `walk-page-boundaries.html` shows country chunk offsets, dictionary/data pages and header/body sizes, then derives the next header. `map-pages-to-rows.html` supplies page-to-row alignment for the planner. These are mechanisms used by module inspection/pruning, not generic topic links.
- `dictionary-values.html` defines zero-based indices and prints the dictionary, indices and reconstructed country values. This prepares why grouping cannot use indices as global identities.
- `trace-footer-requests.html` explains HEAD, GET and range requests and prints dependent size→trailer→footer reads, suffix alternatives and simulated timing. This directly prepares complete-scan dependencies.
- `read-the-footer-map.html` defines row groups/chunks/pages and displays numeric byte spans. `recognise-parquet.html` explains signatures and identifies PARE for encrypted footers. These supply actual preparation for byte framing/encryption modes.
- `follow-schema-paths.html` prints the schema and explains leaves, groups and paths. `follow-iceberg-metadata.html` explains the table metadata chain. These support field IDs without pretending that a generic module index teaches resolution.
- The pruning-notes preparation link “the sorted/shuffled comparison” lands on `compose-a-pruning-plan.html`, which names both fixtures and shows the combined condition/plan evidence. Followed by pointer on phone and focused-link Enter on desktop in both themes; named-fixture/worked-plan assertions passed.
- The Iceberg comparison’s stable-column-identity feature link lands on `keep-column-identity.html`, with actual `fixtures/changes/data/part-0.parquet`, `order_number`, `channel`, and worked ID mapping. Followed in all four configurations. Feature-map links also identify concrete snapshot, update-cost, compaction, partition and commit lessons; the map explicitly limits these to related teaching mechanisms.

## Rejected false positives

- `compare-writer-layouts`: “as the first step predicted” refers to the structural/layout step on this same published page, before the read-cost result. Both demonstrations remain local.
- `separate-scan-and-filter`: “same query” in the library comparison has the query walkthrough and stage explanation on this page.
- `inspect-protected-modules`: “the two modules the step read” refers to the page's own header/page walkthrough; “per-column page counts above” refers to its own plaintext-footer inspector output.
- `prune-files-before-footers`: “the step’s query” immediately specifies `country = 'UK' AND order_id < 200`; its log/query output is local.
- `keep-column-identity`: “as the step before did” in the library section refers to the local executable field-ID walkthrough, not a preceding destination.
- “Above the files”/“above data files” in Iceberg material denotes the table metadata layer, not an absent earlier example.

## Page-by-page coverage

`S+B4` means actual source and built-text review plus automated visits in all four width/theme combinations. The final column separately states which viewport screenshot I manually inspected. Every row's subject/context evidence was read; no claim that every screenshot or every possible interaction was manually inspected.

| Destination | Kind | Coverage | Local subject / preparation / scope evidence | Screenshot inspected |
|---|---|---|---|---|
| `skipping-data.html` | module | S+B4 | Overview identifies metadata pruning; lesson list links bounds, page maps, Bloom filters and combination. | — |
| `rule-out-row-groups.html` | core | S+B4 | Defines predicate/pruning, names sorted and shuffled fixtures before outputs; usable-bound/null preparation is substantive. | — |
| `map-pages-to-rows.html` | core | S+B4 | Names pruning-sorted.parquet and order_id=431 before page-index evidence; row-group preparation leads to named comparison. | — |
| `test-bloom-membership.html` | core | S+B4 | Names both fixtures; membership mechanism and local (row-group, column) pair legend precede results. | — |
| `compose-a-pruning-plan.html` | core | S+B4 | Names sorted/shuffled query; links separate statistics, page-index and Bloom mechanisms before composition. | — |
| `build-pruning-planner.html` | optional build/library | S+B4 | Opens with named combined pruning example and both fixtures; implementation sections have local code antecedents. | — |
| `skipping-data-notes.html` | notes | S+B4 | Names sorted/shuffled orders comparison, links it and page-row mapping; limits describe this teaching planner. | phone light |
| `how-readers-read.html` | module | S+B4 | Overview describes requests, byte costs and dependencies; links trace and strategy comparison. | — |
| `trace-a-complete-scan.html` | core | S+B4 | Defines scan, names pruning-sorted query and store model; footer request and combined-pruning targets prepare dependencies. | — |
| `choose-a-read-strategy.html` | core | S+B4 | Names file/query and links complete trace before strategy comparisons; deterministic-model scope explicit. | — |
| `build-scan-planner.html` | optional build/library | S+B4 | Named scan/strategy preparation; local code implements range merging and scheduling; library-version limits stated. | — |
| `how-readers-read-notes.html` | notes | S+B4 | Names request-strategy comparison on pruning-sorted.parquet and complete trace; simulated costs distinguished from live network. | desktop dark |
| `writing-parquet-well.html` | module | S+B4 | Overview names writer decisions and controlled layouts; lesson list supplies paths into experiment. | — |
| `compare-writer-layouts.html` | core | S+B4 | Defines seven writing-* fixtures as same orders with controlled settings; both structural and read-cost outputs on this page. | — |
| `choose-writer-settings.html` | core | S+B4 | Names controlled writer-layout experiment and links it before recommendations; recommendations depend on workload. | — |
| `inspect-writer-settings.html` | optional build/library | S+B4 | Names writing-baseline.parquet and controlled comparison; version difference and local library-code roles explicit. | — |
| `writing-parquet-well-notes.html` | notes | S+B4 | Names writing-* fixtures and controlled comparison; scale/writer-cost limitations tied to measured settings. | desktop light |
| `what-a-query-engine-does.html` | module | S+B4 | Overview distinguishes file from engine; lessons identify scan/filter, metadata answers, grouping, limits and joins. | — |
| `separate-scan-and-filter.html` | core | S+B4 | Introduces scan/filter roles and named writing-baseline fixture before query evidence; walkthrough and library example same-page. | — |
| `answer-from-metadata.html` | core | S+B4 | Links named query-cost comparison and fixture before discussing count/min/max; exact/usable bounds preparation teaches needed distinction. | — |
| `group-dictionary-values.html` | core | S+B4 | Defines grouping and local indices; names GROUP BY country and writing-baseline; dictionary preparation includes actual decoded indices. | — |
| `limit-a-sorted-query.html` | core | S+B4 | Names query-cost comparison, fixture and ORDER BY order_id LIMIT 5; local sorting requirements explain why engine still reads all. | — |
| `use-join-derived-filters.html` | core | S+B4 | Explains two-table join scenario and derives filter locally; preparation links scan/filter mechanism. | — |
| `what-a-query-engine-does-notes.html` | notes | S+B4 | Names query-cost comparison and teaching-engine measurements; bytes/values scope separated from production execution. | — |
| `what-a-query-engine-does-practice.html` | practice | S+B4 | Establishes writing-baseline default and sorted/dictionary properties before questions; preparation targets demonstrate mechanisms. | phone dark |
| `what-a-query-engine-does-comparison.html` | comparison | S+B4 | Names teaching engine and writing-baseline before table; final uncached-file and compaction qualifications verified. | phone light, final |
| `modular-encryption.html` | module | S+B4 | Overview defines topic and separates modes, key metadata and protected framing. | — |
| `read-encryption-modes.html` | core | S+B4 | Names plaintext-footer and encrypted-footer fixtures and encrypted columns before comparison; signatures preparation teaches PAR1/PARE. | — |
| `distinguish-key-names-and-keys.html` | core | S+B4 | Names both fixtures/columns; defines envelope encryption, wrapped keys and lack of plaintext keys before output. | desktop dark |
| `inspect-protected-modules.html` | core | S+B4 | Names plaintext-footer fixture and protected columns; module framing walkthrough and subsequent visual map both local. | — |
| `build-encryption-inspector.html` | optional build/library | S+B4 | Names keyless inspector, both fixtures and owning module-boundary lesson; links footer-mode comparison for visibility contrast. | phone light |
| `modular-encryption-notes.html` | notes | S+B4 | Names both fixtures and two experiments; explicitly says no decryption or authentication verification. | — |
| `lakehouse-and-beyond.html` | module | S+B4 | Overview introduces table beyond one file and links paths, file pruning and membership. | — |
| `read-partition-paths.html` | core | S+B4 | Names fixtures/table and country directories; path-derived value mechanism demonstrated before check. | — |
| `prune-files-before-footers.html` | core | S+B4 | Defines table format/log, names fixtures/table, links path lesson; log and explicit UK/order_id query local. | phone dark |
| `resolve-table-membership.html` | core | S+B4 | Introduces membership scenario and log actions; preparation points to actual log-based file example. | — |
| `build-table-reader.html` | optional build/library | S+B4 | Names fixtures/table, country partitions and single Delta-shaped log; links actual path/pruning/membership lessons. | desktop light |
| `lakehouse-and-beyond-notes.html` | notes | S+B4 | Names fixtures/table experiment and single log; scopes omissions of Delta protocol/history/checkpoints. | — |
| `changing-a-table.html` | module | S+B4 | Overview frames snapshots/deletes/update costs; links four core lessons and optional reader. | — |
| `follow-snapshots-and-deletes.html` | core | S+B4 | Names fixtures/changes and _snapshots.json; locally demonstrates snapshot contents and delete applicability. | — |
| `trace-a-table-lookup.html` | core | S+B4 | Names fixtures/changes, after-a-day and order300; defines phases before output and links snapshot/deletes evidence. | desktop dark |
| `compare-update-costs.html` | core | S+B4 | Names fixtures/changes and compared snapshots; links snapshot history before costs and distinguishes modeled workloads. | — |
| `decide-when-to-compact.html` | core | S+B4 | Names snapshot/update experiment; local cost trade-off and retained history limits grounded in example. | — |
| `build-snapshot-reader.html` | optional build/library | S+B4 | Identifies teaching snapshot table and implemented steps; links ownership lessons before code and exercises. | — |
| `changing-a-table-notes.html` | notes | S+B4 | Names fixtures/changes, snapshot membership, lookup, update costs and compaction with links; JSON/model limitations explicit. | phone light |
| `what-iceberg-adds.html` | module | S+B4 | Overview states schematic metadata treatment plus executable field-ID evidence; lesson list separates responsibilities. | — |
| `follow-iceberg-metadata.html` | core | S+B4 | Defines metadata chain, manifest list and manifests locally; names schematic example rather than claiming fixture reads. | — |
| `keep-column-identity.html` | core | S+B4 | Names fixtures/changes/data/part-0.parquet; stable-ID mechanism local; final order_number antecedent explicit. | desktop dark, final |
| `evolve-partition-specs.html` | core | S+B4 | Defines partition transform/spec and change scenario locally; preparation supplies path and metadata context. | — |
| `commit-a-table-change.html` | core | S+B4 | Defines catalog/atomic commit and concurrent-writer scenario locally; preparation links metadata chain. | — |
| `what-iceberg-adds-notes.html` | notes | S+B4 | Separates schematic metadata tree/commit from executable field-ID walkthrough; says teaching table is not Iceberg. | phone dark |
| `what-iceberg-adds-practice.html` | practice | S+B4 | Introduces schema/snapshot/partition scenarios; preparation targets supply ID and partition-spec mechanisms. | — |
| `what-iceberg-adds-comparison.html` | comparison | S+B4 | Feature map has concrete owning-lesson links; states examples demonstrate related mechanisms, not complete Iceberg reader. | desktop light |

## Review limits

Browser visits used Chromium in the supplied environment, with emulated viewport/color scheme. Phone interaction was pointer activation at phone width, not a physical touch device. Keyboard checks focused the intended preparation link then pressed Enter; they do not certify complete keyboard navigation or accessibility. This task did not rerun exercises, validate live engines/networks, or infer learner mastery from successful page rendering.
