# Independent cold-entry learner/UX review, modules 1–8

Reviewer did not author these changes. Applied the same learning-design and repository guidance as the earlier terms review. Review assumes direct arrival from contents, not completion of the previous page. Read actual canonical sources, lesson boundaries and published baseline pages; did not read author rationale/draft notes. No edits. Agent review is not novice learning validation.

## Baseline findings

C1 — High for the reported notes path; medium across sibling notes. Every notes page begins with generic “Supporting material for this module’s lessons” and no named example. why-parquet-exists-notes says “The two layouts above” although this page has no layouts; encodings-notes says “The savings in the table” with no table; compression-notes says “Their sizes are measured here” with no measurements. anatomy notes states “The fixtures have neither” without identifying which fixtures, risking extension to all book fixtures. Direction: concise module/example identity and named links to the exact evidence; rewrite limitations so their scope remains local. All eight notes pages require this treatment, not only the screenshot.

C2 — Medium, remote numbered walkthroughs treated as local. weigh-compression-costs tells readers “Set the second step’s column to 4” although no step/editor is on the page. build-encoding-readers refers to “the third step” and “the second step read by hand”; build-page-reader to “the first step’s loop” and the bit “the second step flipped”; build-decompressors to files “the second step decompressed” and “the tables above”. Direction: replace ordinals with named examples linking directly to their owning lesson/anchor. Ensure current optional code still supports the requested variation.

C3 — Medium, report-dependent core lesson has no report. handle-null-and-float-statistics opens “In the preceding report, coupon ... note ...” and later refers to “The -0 the bounds walkthrough printed”. Neither report is on this page. Direction: identify statistics.parquet and summarise the relevant null-count contrast, linking the bounds report in decide-usable-bounds. Similar cross-page “as the second step predicted” appears in decide-usable-bounds and needs the typed-comparison evidence link.

C4 — Medium, preparation is prose rather than navigation. Examples include locate-the-footer “from the previous lesson”; choose-a-tail-read “complete request chain in the previous lesson”; count-schema-levels “from the schema lesson”; stored-levels “already interpret the discounts stream”. Module breadcrumbs are not specific preparation links. Direction: link the actual mechanism/complete worked example needed by this page, without requiring the reader to identify which module item teaches it.

C5 — Low/medium, missing experiment identity on direct entry. one-list opens “The same fixture”; choose-an-encoding “The same measurement ... both files”; compare-codec-patterns “These files”; locate-the-footer “Now the other end of the file”. Several generated captions eventually name the files, so these are not missing evidence altogether, but identity arrives after the reasoning/example starts. Direction: name files and controlled comparison before use, keeping generated numerical evidence in its owner.

C6 — Medium, practice's optional follow-up has no destination. why-parquet-exists-practice asks “For each layout” and to change wanted in “the layouts step”. A cold reader has not been told which layouts or where the step lives. Direction: identify row versus column ordering and link choose-a-table-layout’s worked schematic/editor; retain the exercise as fresh application.

## Rejected baseline concerns

- follow-schema-paths “lowercase versions of the ones above” is correct: REQUIRED/OPTIONAL/REPEATED are defined earlier on that same page.
- dictionary-values “the step printed” has a local dictionary walkthrough showing the header, indices and values. It does not need an external reference merely because it uses “step”.
- stored-levels “header 03 that the walkthrough printed” refers to the local visible saved output. The separate prerequisite to interpret discounts does need a named destination, but this header reference is valid.
- follow-literals-and-copies “one more than the first step’s” compares two walkthroughs actually present on that page. “That second step, entropy coding” refers to a compression phase, not missing navigation.
- check-page-corruption’s damage walkthrough exists later on the same page. The link needed is the separate library demonstration, not the local damaged-page result.
- compare-page-versions “the two tables” refers to its own V1 and V2 tables. Only “the first step” is remote.
- The eight module indexes already identify their subject by title/question and enumerate lessons with outcomes. Their compact form is not a missing-example defect; they are navigation pages.

## Page-by-page baseline coverage

Sources read: all sections and lesson boundaries in chapters/why_parquet_exists.md, anatomy_of_a_parquet_file.md, the_type_system.md, nested_data.md, encodings.md, pages.md, compression.md, metadata_and_statistics.md; tools/lessons.py segmentation/preparation; actual saved worked-result output, tables, practice and limitations as rendered. Baseline DOM text captured at 8020 for all 53 destinations below in context-baseline-*.txt. This capture is a page visit and reading record, not four-view final visual verification.

| Destination | Baseline cold-entry assessment | Final desktop light / dark | Final phone light / dark |
|---|---|---|---|
| why-parquet-exists | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| anatomy-of-a-parquet-file | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| the-type-system | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| nested-data | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| encodings | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| pages | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| compression | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| metadata-and-statistics | Subject/outcomes and destination list clear; no specific defect.  Visited / visited | Opening viewport visually read / visited |
| read-fewer-columns | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| choose-a-table-layout | The eight orders/the query unnamed before the schematic; needs named comparison and selected fields.  Visited / visited | Opening viewport visually read / visited |
| recognise-parquet | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| locate-the-footer | Now the other end of the file and same four letters inherit absent recognition example.  Visited / visited | Opening viewport visually read / visited |
| read-the-footer-map | Regions only name tiny.parquet in generated conditions; preparation half-open span has no lesson link.  Visited / visited | Opening viewport visually read / visited |
| trace-footer-requests | do what you have done and damage from footer-location lesson imply previous actions; trace should identify tiny.parquet early.  Visited / visited | Opening viewport visually read / visited |
| choose-a-tail-read | the chain/third request/both fixtures rely on previous page; named dependency trace needed.  Visited / visited | Opening viewport visually read / visited |
| follow-schema-paths | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| interpret-logical-types | Example fixture is not named until later full-table caption; prior schema should be reachable.  Visited / visited | Opening viewport visually read / visited |
| count-schema-levels | The tree/rebuild relies on schema list on another page; direct schema example link needed.  Visited / visited | Opening viewport visually read / visited |
| nullable-values | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| one-list | The same fixture opens page without naming nested.parquet.  Visited / visited | Opening viewport visually read / visited |
| nested-lists | Every item/this leaf requires earlier schema context; need identity and prep path.  Visited / visited | Opening viewport visually read / visited |
| stored-levels | discounts schema/maxima assumed; named reconstructed stream prep link needed.  Visited / visited | Opening viewport visually read / visited |
| dictionary-values | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| integer-differences | order_id miniature clear locally; ordered_at identity/meaning inherited from optional header description.  Visited / visited | Opening viewport visually read / visited |
| string-prefixes | sku/url fixture identity inherited; first steps other column and dictionary walkthrough not local.  Visited / visited | Opening viewport visually read / visited |
| split-byte-positions | floating-point weights only identified through figure/caption; fixed-width prerequisite not linked.  Visited / visited | Opening viewport visually read / visited |
| choose-an-encoding | same measurement for every column of both files; caption clarifies only after table.  Visited / visited | Opening viewport visually read / visited |
| walk-page-boundaries | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| compare-page-versions | the first step is on another page; explicit V1/V2 fixture comparison needed.  Visited / visited | Opening viewport visually read / visited |
| check-page-corruption | library step at end of Building it not a link; damage walkthrough itself appears locally below, so that reference alone is not dangling.  Visited / visited | Opening viewport visually read / visited |
| follow-literals-and-copies | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| compare-codec-patterns | These files unnamed until table conditions; prior fixture/encoding setup needs explicit identity.  Visited / visited | Opening viewport visually read / visited |
| weigh-compression-costs | Set second steps column asks for absent editor; link real decompressor walkthrough.  Visited / visited | Opening viewport visually read / visited |
| compare-typed-values | Subject and example established locally; named prep navigation still checked under C4.  Visited / visited | Opening viewport visually read / visited |
| decide-usable-bounds | as second step predicted points to typed-comparison page; fixture otherwise identifiable from table conditions.  Visited / visited | Opening viewport visually read / visited |
| handle-null-and-float-statistics | preceding report and bounds walkthrough absent; link report and identify statistics.parquet.  Visited / visited | Opening viewport visually read / visited |
| account-for-footer-cost | Footer-cost examples first named inside table; relevant file identity/prep should be discoverable.  Visited / visited | Opening viewport visually read / visited |
| build-footer-reader | C2/C4: implementation assumes remote examples; name/link evidence and coding preparation.  Visited / visited | Opening viewport visually read / visited |
| build-schema-reader | C2/C4: implementation assumes remote examples; name/link evidence and coding preparation.  Visited / visited | Opening viewport visually read / visited |
| build-nested-reader | C2/C4: implementation assumes remote examples; name/link evidence and coding preparation.  Visited / visited | Opening viewport visually read / visited |
| build-encoding-readers | C2/C4: implementation assumes remote examples; name/link evidence and coding preparation.  Visited / visited | Opening viewport visually read / visited |
| build-page-reader | C2/C4: implementation assumes remote examples; name/link evidence and coding preparation.  Visited / visited | Opening viewport visually read / visited |
| build-decompressors | C2/C4: implementation assumes remote examples; name/link evidence and coding preparation.  Visited / visited | Opening viewport visually read / visited |
| build-statistics-reader | C2/C4: implementation assumes remote examples; name/link evidence and coding preparation.  Visited / visited | Opening viewport visually read / visited |
| why-parquet-exists-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| anatomy-of-a-parquet-file-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| the-type-system-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| nested-data-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| encodings-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| pages-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| compression-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| metadata-and-statistics-notes | C1: generic support introduction; identify module experiment and link evidence for limits.  Visited / visited | Opening viewport visually read / visited |
| why-parquet-exists-practice | for each layout/the layouts step assumes unstated pair and unreachable optional editor.  Visited / visited | Opening viewport visually read / visited |


## Final review and acceptance

Accepted the final rendered candidate after the managing author's final build signal (`context-verified-build.log`; subsequent full-check rebuild uses the same source). No residual finding from this review's cold-entry context and navigation scope. This is independent agent review, not validation with novice learners.

C1–C6 are closed. All eight notes now have subject-specific titles, a stated purpose and named example links. Their limitations identify their fixtures and comparison. Why Parquet exists notes explicitly distinguishes measured CSV/Parquet reads from the row/column schematic; no absent “two layouts above” remains. Core lessons name the file or controlled comparison before relying on it. Preparation links identify the needed mechanism. The null/float lesson identifies statistics.parquet and links the bounds report; builds name their remote evidence rather than relying on absent ordinal steps. Practice identifies the schematic and its real-file comparison while keeping new workloads as application questions. Local references rejected above still have their local antecedents.

The first candidate exposed these additional issues; all were reported before final repair and are now closed:

| ID / severity | Exact first-candidate evidence and location | Final rendered verification |
|---|---|---|
| C7 / medium | weigh-compression-costs “multi-codec walkthrough” went to compression.html#multi-codec-walkthrough; the ID did not exist. Source chapters/compression.md:102 label preceded a bold paragraph. | Actual H2 “Decode the same page with different codecs” now owns follow-literals-and-copies.html#multi-codec-walkthrough. Keyboard activation reaches that section in all four views. Its output compares SNAPPY/LZ4_RAW/GZIP and its revealed code contains the editable column variable, decompress call and out.data needed by the proposed variation. |
| C8 / medium | nested-data-notes “library comparison”; check-page-corruption “library comparison”; weigh-compression-costs “library comparison” all resolved to build-footer-reader.html#ask-a-library. The anchor existed but taught footer metadata, not their claims. Sources chapters/nested_data.md:524, pages.md:180, compression.md:270. | Links now reach build-nested-reader, build-page-reader and build-decompressors respectively, each at #ask-a-library. Read the actual target evidence: offsets [0,2,2,2,4], null-list bitmap and reconstructed tags; unchecked row 58 changes PL→SE while checksum checking refuses the file; pyarrow prints LZ4 while file/crate identify LZ4_RAW. This closes relevance, not only URL existence. |
| C9 / medium | string-prefixes preparation promised “PLAIN byte arrays” at dictionary-values, which explains PLAIN generally but not the required length representation. tools/lessons.py:188–191. | “byte-array lengths and values” now opens interpret-logical-types. Its physical-types table explicitly says BYTE_ARRAY is “a length, then that many bytes”, the mechanism needed by the string-length comparison. |
| C10 / low | anatomy notes “footer you decoded here”; type-system notes “maximums you computed here” falsely attributed remote work to the notes page. Sources chapters/anatomy_of_a_parquet_file.md:836 and the_type_system.md:655. | Anatomy now says “footer located in the tiny-file example” linking locate-the-footer#locate-the-footer. Types says levels “introduced by the schema-level walkthrough” linking count-schema-levels#schema-level-walkthrough. Those targets teach footer location and schema maximum-level counting respectively. |

### Browser and semantic coverage

All 53 destinations in the table above were visited and captured at 1366×850 and 390×850 in explicit light and dark themes: 212 page visits, correct actual theme/background in each, and zero document-width overflow. Read rendered main text and preparation/evidence references for all 29 core lessons, all 16 optional pages and eight module indexes. Inspected the opening viewport visually for every destination in phone/light contact sheets; separately inspected all eight notes in phone/dark, Why Parquet exists notes in all four views, build-schema-reader phone/light, null/float desktop/dark and practice phone/dark. This is not a claim to have visually read every screenful or every code tab in all four views. Opening layout, text wrapping and visible example links were readable in inspected images; wide data tables remain scrollable inside their own containers.

After the final repairs, revisited all six affected source destinations in all four views (24 visits), read the seven repaired source references and their actual target evidence, and inspected relevant final images. Previous broad-sweep screenshots are unchanged except for these focused repairs; phone/light contact sheets use the repaired versions where applicable.

The internal link inventory contains 109 distinct destination URLs from main-page links (including some navigation). Checked status and target anchor presence, then compared new preparation/evidence labels and surrounding claims with the target teaching content. This semantic pass is what caught C8 and C9 despite valid HTTP responses. External specification/repository citations were not exhaustively audited; this review makes no claim to do so.

Actual keyboard contents route: open the contents drawer by keyboard on phone, focus its lesson search, type “Why Parquet exists”, Tab seven times to the notes destination, Enter. In all four views this lands on “Limits of CSV and Parquet comparisons”, with the stated purpose and both example links visible. No mouse click was used for that navigation.

Glossary sample in the final build: focus the bold dotted checksum link, Enter opens the definition, Escape closes and restores focus in all four views. Its Learn it link is check-page-corruption.html#checksums, the actual explanation; the full-reference link is glossary.html#term-checksum. Inspected the phone dialogs in both themes: contained panel, readable text and visible close-button focus.

Legacy samples also resolve to meaningful owners: compression.html#multi-codec-walkthrough → follow-literals-and-copies with its new heading; anatomy-of-a-parquet-file.html#locate-the-footer → locate-the-footer; nested-data.html#ask-a-library → build-nested-reader; the-type-system.html#schema-level-walkthrough → count-schema-levels. Checked final URLs and heading text, not only response codes.

Evidence files: context-final-browser.json (212 visits + four contents routes); context-final-links.json and context-final-targets.json (first-candidate link/semantic evidence); context-repaired-browser.json (24 final focused visits and target text); context-navigation.json (final glossary, keyboard evidence link and legacy routes); context-final-*.txt/png, context-repaired-*.png, context-sheet-0.png through context-sheet-8.png, context-glossary-*.png. All are under /workspace/scratch. No repository files were edited by this reviewer.
