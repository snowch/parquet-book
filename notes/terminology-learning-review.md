# Terminology and prerequisite review

## Brief

Review every published lesson and its optional resources, plus the cover, preface, part pages
and appendices. The learner should be able to explain the terms used by an example and use
them to reason through its fresh case without opening code or searching a later lesson.

The reported fault is present in source: the first lesson's fresh answer uses projection,
footer metadata and prefetching before their definitions. Projection is introduced in the
following lesson. The existing glossary has paragraph entries and chapter links, but no stable
entry anchors or prominent way into it from a lesson.

Prerequisites are the data-engineering audience stated in the preface and each lesson's
preparation in `tools/lessons.py`. Familiarity with SQL does not establish familiarity with
Parquet structures, binary notation or reader strategies. A definition is different from a
worked example or independent practice. Preserve the existing examples and fresh tasks;
add a small bridge where a task requires a mechanism the visible route has not demonstrated.

Inspect the actual source boundaries and built lessons. Identify terms in headings, example
output, diagrams, controls, prompts and feedback as well as explanatory prose. Introduce
essential terms locally before they carry an argument. Use ordinary language instead of
teaching a later mechanism prematurely. Keep qualifications beside the relevant claim.

## UX plan

Keep the current white paper, blue-grey rail, dark ink and blue accent. Match the book's serif
prose and sans-serif controls. Bold the defining occurrence and provide a recognisable link to
its glossary entry; explanations remain visible in the lesson. Avoid automatic highlighting of
every occurrence or definitions available only on hover.

Give the existing glossary a prominent contents entry, stable term anchors, alphabetical
navigation and search. Each definition links to the lesson that teaches it. The full glossary
and links must work without JavaScript. Search is an enhancement, with a visible label and
empty-result feedback. Review keyboard use, phone/desktop reflow and both themes.

Review the plan against the task: a dictionary lookup cannot repair a missing teaching step.
Fix first-use explanations in the lesson as well as improving reference access. The glossary
is one canonical source of definitions, not a second independently maintained data file.

## Evidence and review

Apply the Assembly Lab learning-design workflow and Frontend Design skill. Use separate
drafting and independent learner/technical review passes. Record accepted and rejected findings
and distinguish browser inspection from source inspection. Agent reviews and automated tests
are not evidence from a novice study or a complete assistive-technology audit.

## Course-wide corrections

| Module | Main first-use corrections |
| --- | --- |
| Why Parquet exists | Projection, metadata, footer, trailer, row group and column chunk before the byte-cost comparison; prefetch before feedback. |
| Anatomy | File signatures, bytes, ranges and request terminology beside the corresponding evidence. |
| Types | Physical/logical types restored to the core route; schema notation before output; decimal precision and scale. |
| Nested data | Scalar, slot and levels; concise local reminders when following nested paths. |
| Encodings | Encoding and dictionary indices, widths and miniblocks; dictionary-skipping qualification when pages can fall back. |
| Pages | Page boundaries, page body/header and CRC before the walkthroughs. |
| Compression | Codec, literal and copy before compressed-stream examples; compressed size separated from unmeasured speed. |
| Statistics | Numeric comparison, signedness and two's complement; bounds, NaN and locally scoped TYPE_ORDER rules. |
| Skipping | Predicate, pruning, Bloom bit/hash vocabulary and a reading key for the result's local bit positions. |
| Readers | Coalescing, bandwidth and concurrency beside read-strategy comparisons. |
| Writers | Selectivity and cardinality before setting-selection feedback. |
| Query engine | Scan/filter distinction, top-k and heap before they are needed. |
| Encryption | Plaintext, nonce, authentication and key roles; wrapped-key explanation moved before its output. |
| Lakehouse | Partition, manifest and table-membership terminology in the owning lessons. |
| Changing a table | Snapshot/delete model scope and dependency phases distinguished from network round trips. |
| Iceberg | Catalog, commit and partition-spec terms; the metadata schematic explicitly uses format versions one to three. |

The preface, cover, part introductions and all appendices were reviewed too. Reading prerequisites
are explicit. Essential explanation is available without reading or running code. All existing
quoted code and generated evidence is retained. Lookup output labels and the shared report field
now say `dependency_phases`; request scheduling and measured results are unchanged.

## Glossary and UX decisions

The existing glossary grew from fifty entries to 170 individually addressable definitions.
Each entry links to the teaching section, including optional sections where appropriate. Its
alphabetical navigation works without scripts; search accepts lesson spellings and aliases such
as RLE, BYTE_STREAM_SPLIT, CRC-32 and prefetching.

Bold terms that match a glossary name receive dotted links. With JavaScript these open a native
dialog containing the canonical definition. Escape and Close return focus to the term and retain
the reading position. Ordinary anchors remain the fallback without JavaScript or if the lookup
data fails to load. A glossary visit preserves the lesson bookmark. Search, page content and
dialog content derive from the same Markdown definitions.

## Independent review outcomes

Separate drafting agents covered modules one to eight, modules nine to sixteen, and front/reference
pages. Independent agents then reviewed [early lessons](terminology-reviews/learner-modules-1-8.md),
[later lessons](terminology-reviews/learner-modules-9-16.md), and
[technical accuracy and glossary UX](terminology-reviews/technical-and-ux.md). All used the
configured parent model without an override. Reviewers received the actual material before the
authors' explanations. Their reports distinguish source reading, automated visits and screenshots.

Accepted findings included generated-table labels appearing before definitions, two's complement
being taught only in optional material, missing search aliases, an unlinked earlier walkthrough,
schema-output notation, Bloom output notation, key-wrapping order, ambiguous projection wording,
phase/round-trip confusion, unqualified NaN rules, table-format equivalence and PLAIN pipeline
wording. All were corrected and independently verified. Rejected concerns and their evidence are
retained in the reports, including an apparent scroll-lock failure caused by pending smooth scroll.

Keep the short lessons, complete examples and fresh application tasks. Keep definitions local,
with glossary lookup as a reminder. The final reviews found no unresolved blocker. No novice
study or complete assistive-technology audit was performed; passing checks does not establish
learning effectiveness for the intended population.
