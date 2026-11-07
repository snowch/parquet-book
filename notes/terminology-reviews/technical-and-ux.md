# Independent technical and glossary UX review

Reviewer: independent Codex agent using the inherited model configuration (no model override). I did not author the implementation or prose. I read the actual sources and built content before receiving explanations of fixes; I did not read the author's review notes. Workflow: Assembly Lab learning-design skill, docs/authoring.md technical-review guidance, Parquet CLAUDE.md and STYLE.md. This is technical/browser review, not a novice study or complete assistive-technology certification.

## Scope and evidence

I read changed claims across all sixteen chapter sources, the complete initial glossary and subsequently added definitions, glossary extraction and rendering in tools/glossary.py, tools/render.py, scripts/build-site.py, web/glossary.js and CSS. Source checks focused on projection versus SQL output, pruning versus filtering, bounds, schema/list levels, Bloom filters, encoding/compression, encryption and snapshot scope. Browser checks used the real build served at http://127.0.0.1:8020, initially 129 glossary definitions. Final-build verification is recorded below when available.

Implementation evidence read: python/parquet_lab/{schema,bloom,prune,stats,page_index,pages,crypto,engine,object_store,changes}.py, fixture generator settings, and the lookup walkthrough. Upstream source snapshots are saved in /workspace/scratch/terms-specs/: Parquet LogicalTypes.md, Encodings.md, BloomFilter.md, PageIndex.md, Encryption.md, src/main/thrift/parquet.thrift; Apache Iceberg specification; Delta PROTOCOL.md. These are current upstream texts, not a claim that every upstream feature is implemented by the teaching reader.

## Findings raised

1. **Medium, scan projection wording.** chapters/why_parquet_exists.md, “The same two columns from Parquet”: “a reader can leave the other columns unread. This includes columns used by a filter even if they are not returned.” The immediate referent makes filter-only columns appear to be skipped. The glossary and engine correctly include them in scan inputs. Explicitly make the scan's needed columns, rather than the unread columns, the subject of the last sentence. Reported to root.

2. **Medium, glossary search aliases.** web/glossary.js `apply()` searched only entry text, while tools/glossary.py ALIASES affected link targets only. Chromium reproduced `RLE` → no matches, `prefetching` → Projection only, excluding Prefetch. Both are lesson spellings. Generate alias search metadata from the existing canonical mapping and include it in filtering; normalize reasonable spelling variants. Root reports this fix implemented; verification pending final build.

3. **Medium, phase versus round-trip claims.** chapters/changing_a_table.md “Trace a complete table lookup” and walkthroughs/python/changing_a_table/look_up_an_order.py (with Rust twin) label `r.phase` groups “round trip” and say their requests “go out together.” object_store.TracingStore._record schedules on the earliest free connection. Five requests in phase 2 on four connections require two waves; `next_phase()` is a barrier. Label these groups dependency phases, explain overlapping requests up to connection capacity, and scope the barrier policy to this reader. Source recommendation sent to root after learner review raised the discrepancy. No scheduler change is needed.

4. **Medium, float-statistics scope.** chapters/metadata_and_statistics.md “Sort orders” newly says NaN “must be left out of minimum and maximum bounds,” with generic repeats in Floating point / takeaways. The reader and fixtures use TYPE_ORDER, where that account applies. Current parquet.thrift `ColumnOrder` additionally defines IEEE_754_TOTAL_ORDER (lines 1201ff) and allows NaN extrema when all non-null values are NaN. Qualify these statements locally to the ordering used here; no reader feature expansion is required. This avoids presenting the teaching reader's supported ordering as the only format rule.

5. **Medium, existing table-format overgeneralisation.** chapters/changing_a_table.md “A table and its history” defines a snapshot as data/delete file lists and says Apache Iceberg and Delta Lake “keep exactly this list.” Delta snapshots include active file actions with optional deletion-vector descriptors, along with schema/protocol/tombstones/transaction state; they do not use this exact position-delete-file/two-list JSON model. Replace the equivalence with a statement that formats track table state using different metadata and delete representations. Source: Delta PROTOCOL.md Snapshot and Add File/Remove File sections. This is pre-existing but directly relevant to the local model qualification under review.

6. **Low, encoding pipeline wording.** appendices/glossary.md PLAIN says “direct encoding ... before dictionary or delta transformations.” These are alternative value encodings, not a mandatory PLAIN→dictionary/delta pipeline. “without dictionary or delta transformations” is a minimal correction. Parquet Encodings.md and the reader's encoding dispatch support this distinction. The following sentence correctly says PLAIN need not be uncompressed.

## Browser observations

Executed /workspace/scratch/terms-tech-browser.cjs and terms-tech-browser-extra.cjs with Playwright and /usr/bin/chromium. The first automatic Playwright binary launch was unavailable; using the installed Chromium succeeded.

- Desktop 1440×1000 light and phone 390×844 dark rendered glossary and dialog without horizontal overflow. Inspected the screenshot images, not only DOM dimensions.
- Enter on a definition link opened the native modal. Initial focus was the labelled 44px close control. Escape closed it, restored the original link, retained the lesson URL and exact scroll position. Tab reached lesson link and full glossary link, then native browser focus cycle; no background book control became actionable in the modal.
- After scroll-state debounce, dialog use preserved last-read unchanged. Navigating to glossary preserved the current lesson bookmark too.
- Unmatched search gave zero displayed definitions and announced an actionable no-match status. A hash change cleared a conflicting filter and restored the target.
- A direct deep link worked. An immediate screenshot initially captured the top while smooth scrolling was in progress; repeated position measurements showed arrival at the target. This is rejected as a bug.
- A JS-disabled phone context followed the native term anchor into the glossary, displayed all definitions and kept the unusable search hidden.
- Blocking glossary.json caused navigation to the native glossary anchor, rather than losing access to the definition.
- No page JavaScript errors in the representative initial flow.

Artifacts: terms-tech-dialog-mobile-dark.png, terms-tech-glossary-mobile-dark.png, terms-tech-direct-link.png, terms-tech-glossary-desktop-light.png in /workspace/scratch/. The first glossary mobile screenshot is intentionally not evidence of completed deep-link arrival; terms-tech-direct-link.png is the settled follow-up.

## Challenged and rejected concerns

- **Projection definition itself conflates SQL output:** rejected. Glossary explicitly scopes the scan and says condition-only columns can be required; query-engine prose separates scan/filter. Finding 1 is a local antecedent problem.
- **Bloom positive implies membership, or hash collisions are the only false-positive cause:** rejected. The new prose explicitly describes overlapping bits from multiple values and candidate status, and qualifies the no-false-negative guarantee by correct writing/reading. Bloom implementation/spec agree on split blocks and xxHash64.
- **Dictionary absence always permits chunk skipping:** rejected after reading the actual changed text: it now requires every data page to use that dictionary and separately checks fallback encodings.
- **AES-GCM layout asserted for every encryption algorithm:** rejected. The module-layout introduction now scopes to the inspected AES-GCM files, and the same lesson distinguishes AES_GCM_CTR_V1 unauthenticated page bodies. Footer signature versus file magic and insecure toy key wrapping are explicitly separated.
- **List levels erase null/empty distinction:** rejected. Schema-derived maxima and actual levels distinguish absent list, empty repeated group, null element and present value; legacy layouts are acknowledged. The general repeated-field shorthand is backed by the field repetition model and expanded in the nested lesson.
- **Iceberg must cover version 4 tree structure:** rejected as a requirement. The schematic explicitly targets format versions one through three. Current spec says version 4 is under active development and not formally adopted. A stable-version scope is appropriate.
- **Full glossary automatically destroys the lesson bookmark:** rejected by code and browser evidence. `remember()` excludes glossary.html; its link remains a normal page navigation.
- **Need a manual focus trap or text-only JS fallback:** rejected. Native modal dialog and native anchors provide the observed keyboard/fallback behavior. Complete screen-reader testing remains unperformed.

## Decision

Keep the single canonical glossary, native anchor fallback and optional native dialog. Correct the precise issues above and verify the final generated build. No critical security or runtime blocker was found. Passing these checks supports accuracy and representative operation, not learning effectiveness or full accessibility certification.

## Final verification, 7 November 2026

All six findings are resolved in source and generated content. The final glossary contains 170 entries, including Dependency phase. I reran focused browser checks on the rebuilt localhost site with service workers blocked, and independently checked the changed report and walkthrough outputs.

- Projection now says needed columns include filter-only columns before explaining which other columns may remain unread. Verified rendered Read fewer columns lesson.
- Generated `data-aliases` comes from the canonical term/alias mapping; filtering normalises hyphens, underscores and apostrophes. Browser assertions passed for RLE, prefetching, CRC-32, BYTE_STREAM_SPLIT, straight-apostrophe two's complement and dependency phases, each finding its intended definition.
- Python and Rust report JSON for order 300 in after-a-day matched exactly: 16 requests, 5 dependency phases, 24,093 bytes, 140,198 simulated microseconds. The reported phase count equals the distinct request phases; phase 2 has two distinct request start times, supporting the corrected distinction. Both walkthroughs print the same phase/request trace. Their complete text differs only in existing Rust quotes around string output values, which is not a grouping discrepancy. Generated changes-lookup.md labels “Dependency phases (requests)”. The browser WASM panel displayed “5 dependency phases, 16 requests, 24,093 bytes” and dataset dependencyPhases=5. Prose locally explains the connection limit and phase barrier.
- NaN rules and practice feedback name TYPE_ORDER. Final verification initially caught one remaining unqualified standalone takeaway; root corrected it. Confirmed regenerated metadata-and-statistics-notes.html now says “Under TYPE_ORDER” and states other declared orders require their own rules.
- Snapshot prose now explicitly says table formats use different metadata and delete representations, with this JSON state identified as the teaching fixture.
- PLAIN now says “without dictionary or delta transformations,” verified in rendered glossary.

Final browser regression assertions also passed: no-match search and clearing on deep link, canonical PLAIN anchor, Enter/Escape modal flow and focus restoration, exact lesson-scroll and bookmark preservation, 390px dark-mode reflow, network-failure native fallback, and JS-disabled native fallback with all 170 definitions. No page JavaScript errors were observed. I inspected the final phone screenshot (terms-tech-final-mobile-dark.png) showing the Dependency phase entry beneath the fixed header. Script: /workspace/scratch/terms-tech-final.cjs.

An initial final-run wait for the lookup laboratory timed out while the build/check work was active. A focused diagnosis then loaded the same laboratory successfully, and the complete final test rerun passed, including the WASM dependency-phase display. No reproducible application defect remained.

**Final decision:** no unresolved blocker from this technical/glossary review. Keep the changes. The review still does not establish novice learning effectiveness or complete assistive-technology coverage.
