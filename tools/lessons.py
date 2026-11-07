"""Short reading routes cut from the canonical chapter parse, never copied prose."""

from __future__ import annotations

import copy
import html
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Lesson:
    slug: str
    title: str
    outcome: str
    preparation: str
    optional: bool = False
    kind: str = "core"
    prerequisites: tuple[tuple[str, str], ...] = ()

    @property
    def href(self) -> str:
        return f"{self.slug}.html"


MODULES = {
    "anatomy_of_a_parquet_file": (
        Lesson(
            "recognise-parquet",
            "Recognise Parquet and read its bytes",
            "Recognise the file signature and distinguish stored bytes from their display.",
            "Start here for file bytes. No hex viewer or programming is needed.",
        ),
        Lesson(
            "locate-the-footer",
            "Locate and validate the footer",
            "Decode the trailer length, locate the footer and reject an impossible span.",
            "Use byte offsets and hexadecimal notation:",
            prerequisites=(("recognise-parquet", "reading the file signature"),),
        ),
        Lesson(
            "read-the-footer-map",
            "Turn the footer into a byte map",
            "Follow row groups into column chunks and convert a chunk span into an HTTP range.",
            "Use footer boundaries and byte spans:",
            prerequisites=(("locate-the-footer", "locating the footer"),),
        ),
        Lesson(
            "trace-footer-requests",
            "Trace the dependent reads",
            "Explain which information each request supplies to the next request.",
            "Use the file’s byte map:",
            prerequisites=(("read-the-footer-map", "row groups and column chunks"),),
        ),
        Lesson(
            "choose-a-tail-read",
            "Choose a tail-read strategy",
            "Explain when a suffix read saves a request and when the footer still needs another read.",
            "Compare with the baseline request chain:",
            prerequisites=(("trace-footer-requests", "dependent footer requests"),),
        ),
        Lesson(
            "build-footer-reader",
            "Build the footer reader",
            "Connect the byte calculations and request trace to the Python and Rust implementation.",
            "Connect code to these worked examples:",
            prerequisites=(
                ("locate-the-footer", "footer calculations"),
                ("trace-footer-requests", "request trace"),
            ),
            optional=True,
        ),
    ),
    "nested_data": (
        Lesson(
            "nullable-values",
            "Distinguish a null from a value",
            "Read definition levels for one optional scalar before introducing lists.",
            "Use optional fields and maximum levels:",
            prerequisites=(("count-schema-levels", "counting schema levels"),),
        ),
        Lesson(
            "one-list",
            "Rebuild one list",
            "Distinguish a null list, an empty list and a null element, then rebuild the records.",
            "Start with missing scalar values:",
            prerequisites=(("nullable-values", "nullable values and definition levels"),),
        ),
        Lesson(
            "nested-lists",
            "Follow lists inside lists",
            "Use repetition levels to distinguish a new record, a new item and another discount.",
            "First rebuild a single list:",
            prerequisites=(("one-list", "the tags example"),),
        ),
        Lesson(
            "stored-levels",
            "Read the stored level streams",
            "Connect decoded levels to run headers, bit widths and padding in a data page.",
            "Use the decoded nested-list stream:",
            prerequisites=(("nested-lists", "the discounts example"),),
        ),
        Lesson(
            "build-nested-reader",
            "Build the nested-data reader",
            "Connect the stored levels to decoding and record reconstruction in Python and Rust.",
            "Connect code to the worked streams:",
            prerequisites=(
                ("stored-levels", "stored level runs"),
                ("nested-lists", "rebuilding discounts"),
            ),
            optional=True,
        ),
    ),
}


MODULES.update(
    {
        "why_parquet_exists": (
            Lesson(
                "read-fewer-columns",
                "Read fewer columns",
                "Explain why selecting columns can reduce file bytes read.",
                "Start here. You need only the idea of rows and columns.",
            ),
            Lesson(
                "choose-a-table-layout",
                "Choose a layout for a workload",
                "Choose between column scans and complete-record lookups.",
                "Build on the measured comparison:",
                prerequisites=(("read-fewer-columns", "CSV and Parquet bytes read"),),
            ),
        ),
        "the_type_system": (
            Lesson(
                "follow-schema-paths",
                "Follow the schema tree",
                "Identify leaves, groups and the path that names a stored column.",
                "Find the schema in the footer:",
                prerequisites=(("read-the-footer-map", "the footer byte map"),),
            ),
            Lesson(
                "interpret-logical-types",
                "Interpret the same stored bytes",
                "Use the physical type and logical annotation to interpret a value.",
                "Find a leaf and its annotation:",
                prerequisites=(("follow-schema-paths", "the schema tree"),),
            ),
            Lesson(
                "count-schema-levels",
                "Count optional and repeated ancestors",
                "Derive maximum definition and repetition levels from a leaf path.",
                "Use required, optional and repeated fields:",
                prerequisites=(("follow-schema-paths", "the schema tree"),),
            ),
            Lesson(
                "build-schema-reader",
                "Build the schema and type reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the worked schema:",
                prerequisites=(
                    ("follow-schema-paths", "schema paths"),
                    ("count-schema-levels", "maximum levels"),
                ),
                optional=True,
            ),
        ),
        "encodings": (
            Lesson(
                "dictionary-values",
                "Replace repeated values with indices",
                "Reconstruct values from a dictionary and its indices.",
                "Use the integer-run format for indices:",
                prerequisites=(("stored-levels", "run headers and bit packing"),),
            ),
            Lesson(
                "integer-differences",
                "Reconstruct integer differences",
                "Recover values from a first value and successive deltas.",
                "Read a sequence of integers. Physical header details are optional.",
            ),
            Lesson(
                "string-prefixes",
                "Rebuild strings from lengths and prefixes",
                "Recover strings from stored lengths, shared prefixes and suffixes.",
                "Use differences and byte-array lengths:",
                prerequisites=(
                    ("integer-differences", "integer deltas"),
                    ("interpret-logical-types", "byte-array lengths and values"),
                ),
            ),
            Lesson(
                "split-byte-positions",
                "Separate byte positions before compression",
                "Explain why byte-stream split can change compressibility without changing encoded length.",
                "Use fixed-width stored values:",
                prerequisites=(("interpret-logical-types", "physical and logical types"),),
            ),
            Lesson(
                "choose-an-encoding",
                "Choose an encoding for a pattern",
                "Use value patterns and measured sizes to justify an encoding choice.",
                "Compare the patterns in the worked examples:",
                prerequisites=(
                    ("dictionary-values", "repeated values"),
                    ("integer-differences", "integer deltas"),
                    ("string-prefixes", "shared string prefixes"),
                    ("split-byte-positions", "byte-stream split"),
                ),
            ),
            Lesson(
                "build-encoding-readers",
                "Build the encoding readers",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to these decoding examples:",
                prerequisites=(
                    ("dictionary-values", "dictionary indices"),
                    ("integer-differences", "integer deltas"),
                    ("string-prefixes", "string deltas"),
                ),
                optional=True,
            ),
        ),
        "pages": (
            Lesson(
                "walk-page-boundaries",
                "Walk page boundaries",
                "Locate the next page from its header and compressed body size.",
                "Use column-chunk byte ranges:",
                prerequisites=(("read-the-footer-map", "the footer byte map"),),
            ),
            Lesson(
                "compare-page-versions",
                "Compare data page versions",
                "Explain how V1 and V2 separate levels, values and compression.",
                "Use page headers and nested-value streams:",
                prerequisites=(
                    ("walk-page-boundaries", "page boundaries"),
                    ("stored-levels", "stored levels"),
                ),
            ),
            Lesson(
                "check-page-corruption",
                "Distinguish corruption from decoding errors",
                "Explain what checking a page CRC establishes and what it cannot establish.",
                "Distinguish a page header from its body:",
                prerequisites=(("walk-page-boundaries", "page boundaries"),),
            ),
            Lesson(
                "build-page-reader",
                "Build the page reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the page examples:",
                prerequisites=(
                    ("walk-page-boundaries", "header and body lengths"),
                    ("compare-page-versions", "V1 and V2 bodies"),
                    ("check-page-corruption", "checksum checks"),
                ),
                optional=True,
            ),
        ),
        "compression": (
            Lesson(
                "follow-literals-and-copies",
                "Follow literals and overlapping copies",
                "Trace how a compressed copy can reuse bytes it has just produced.",
                "Place compression within a page:",
                prerequisites=(("compare-page-versions", "page compression boundaries"),),
            ),
            Lesson(
                "compare-codec-patterns",
                "Compare codecs on different patterns",
                "Distinguish a value-pattern effect from a codec-size comparison.",
                "Use the compressed-token walkthrough:",
                prerequisites=(("follow-literals-and-copies", "literals and copies"),),
            ),
            Lesson(
                "weigh-compression-costs",
                "Weigh encoding and decompression costs",
                "Explain the tradeoff between bytes saved and page work required.",
                "Connect encoding to page compression:",
                prerequisites=(
                    ("split-byte-positions", "byte-stream split"),
                    ("compare-page-versions", "V1 and V2 boundaries"),
                ),
            ),
            Lesson(
                "build-decompressors",
                "Build the decompressors",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the compressed-token examples:",
                prerequisites=(("follow-literals-and-copies", "literals and overlapping copies"),),
                optional=True,
            ),
        ),
        "metadata_and_statistics": (
            Lesson(
                "compare-typed-values",
                "Compare values in their declared order",
                "Use physical/logical types to choose the correct comparison order.",
                "Use physical types and logical annotations:",
                prerequisites=(("interpret-logical-types", "stored values and their meaning"),),
            ),
            Lesson(
                "decide-usable-bounds",
                "Decide whether bounds are usable",
                "Distinguish known typed bounds from missing or unsafe statistics.",
                "Choose the column’s comparison order:",
                prerequisites=(("compare-typed-values", "typed value comparisons"),),
            ),
            Lesson(
                "handle-null-and-float-statistics",
                "Handle nulls and exceptional floats",
                "Explain how nulls, absent statistics, NaN and signed zero affect a decision.",
                "Distinguish missing from trustworthy bounds:",
                prerequisites=(("decide-usable-bounds", "usable statistics"),),
            ),
            Lesson(
                "account-for-footer-cost",
                "Account for metadata overhead",
                "Explain why more statistics can increase the cost paid by every query.",
                "Use the footer’s row-group and column map:",
                prerequisites=(("read-the-footer-map", "footer metadata"),),
            ),
            Lesson(
                "build-statistics-reader",
                "Build the statistics reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the statistics decisions:",
                prerequisites=(
                    ("compare-typed-values", "typed comparisons"),
                    ("decide-usable-bounds", "usable bounds"),
                    ("handle-null-and-float-statistics", "nulls and floats"),
                ),
                optional=True,
            ),
        ),
        "skipping_data": (
            Lesson(
                "rule-out-row-groups",
                "Rule out row groups safely",
                "Use bounds and null counts to prove a row group cannot match.",
                "Use trustworthy bounds and null counts:",
                prerequisites=(
                    ("decide-usable-bounds", "usable bounds"),
                    ("handle-null-and-float-statistics", "missing values and exceptional floats"),
                ),
            ),
            Lesson(
                "map-pages-to-rows",
                "Map kept pages across columns",
                "Use row ranges to select pages when columns have different page boundaries.",
                "Start with whole-group pruning and page boundaries:",
                prerequisites=(
                    ("rule-out-row-groups", "ruling out row groups"),
                    ("walk-page-boundaries", "page headers"),
                ),
            ),
            Lesson(
                "test-bloom-membership",
                "Interpret Bloom-filter membership",
                "Distinguish definite absence from possible presence.",
                "Start with candidate groups and a query condition:",
                prerequisites=(("rule-out-row-groups", "row-group pruning"),),
            ),
            Lesson(
                "compose-a-pruning-plan",
                "Compose a safe skipping plan",
                "Explain the distinct contributions of ranges, page indexes and Bloom filters.",
                "Compare the three mechanisms:",
                prerequisites=(
                    ("rule-out-row-groups", "row-group bounds"),
                    ("map-pages-to-rows", "page indexes"),
                    ("test-bloom-membership", "Bloom filters"),
                ),
            ),
            Lesson(
                "build-pruning-planner",
                "Build the pruning planner",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the combined result:",
                prerequisites=(("compose-a-pruning-plan", "the sorted and shuffled orders comparison"),),
                optional=True,
            ),
        ),
        "how_readers_read": (
            Lesson(
                "trace-a-complete-scan",
                "Trace a complete scan",
                "Follow request dependencies from metadata to selected data pages.",
                "Connect metadata discovery to pruning:",
                prerequisites=(
                    ("trace-footer-requests", "footer requests"),
                    ("compose-a-pruning-plan", "the combined pruning plan"),
                ),
            ),
            Lesson(
                "choose-a-read-strategy",
                "Choose a read strategy",
                "Trade request latency against extra bytes, concurrency and merging.",
                "Keep the baseline requests in view:",
                prerequisites=(("trace-a-complete-scan", "the complete scan trace"),),
            ),
            Lesson(
                "build-scan-planner",
                "Build the scan planner",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the request model:",
                prerequisites=(
                    ("trace-a-complete-scan", "the complete scan"),
                    ("choose-a-read-strategy", "strategy costs"),
                ),
                optional=True,
            ),
        ),
        "writing_parquet_well": (
            Lesson(
                "compare-writer-layouts",
                "Compare controlled writer layouts",
                "Separate the effect of a changed layout from a changed table or query.",
                "Use the scan’s request and byte costs:",
                prerequisites=(("choose-a-read-strategy", "read-strategy trade-offs"),),
            ),
            Lesson(
                "choose-writer-settings",
                "Choose settings for a workload",
                "Justify a layout choice and its tradeoff for a new query mix.",
                "Use the controlled evidence:",
                prerequisites=(("compare-writer-layouts", "seven writer layouts"),),
            ),
            Lesson(
                "inspect-writer-settings",
                "Inspect writer settings and reader costs",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the controlled files:",
                prerequisites=(
                    ("compare-writer-layouts", "the writer-layout comparison"),
                    ("choose-writer-settings", "settings trade-offs"),
                ),
                optional=True,
            ),
        ),
        "what_a_query_engine_does": (
            Lesson(
                "separate-scan-and-filter",
                "Separate scanning from filtering",
                "Explain which work belongs to the file scan and which to later query stages.",
                "Use the path from metadata to selected pages:",
                prerequisites=(("trace-a-complete-scan", "the complete scan trace"),),
            ),
            Lesson(
                "answer-from-metadata",
                "Answer a query from metadata",
                "State when row counts or bounds suffice without reading column data.",
                "Distinguish candidate groups from matching rows:",
                prerequisites=(("separate-scan-and-filter", "scanning and filtering"),),
            ),
            Lesson(
                "group-dictionary-values",
                "Group values across local dictionaries",
                "Explain why dictionary indices cannot be treated as global identities.",
                "Use local dictionaries and query stages:",
                prerequisites=(
                    ("dictionary-values", "dictionary indices"),
                    ("separate-scan-and-filter", "scanning and filtering"),
                ),
            ),
            Lesson(
                "limit-a-sorted-query",
                "Decide when a sorted limit can stop",
                "Distinguish bounded sort memory from evidence that scanning may stop.",
                "Use trustworthy ranges to rule out groups:",
                prerequisites=(("rule-out-row-groups", "row-group pruning"),),
            ),
            Lesson(
                "use-join-derived-filters",
                "Use filters learned from a join input",
                "Explain how known build-side keys can prune the probe-side scan.",
                "Distinguish pruning from checking returned rows:",
                prerequisites=(("separate-scan-and-filter", "scanning and filtering"),),
            ),
        ),
        "modular_encryption": (
            Lesson(
                "read-encryption-modes",
                "Recognise encryption modes",
                "Predict which metadata remains visible in the two footer modes.",
                "Use file signatures and the footer map:",
                prerequisites=(
                    ("recognise-parquet", "file signatures"),
                    ("read-the-footer-map", "the footer byte map"),
                ),
            ),
            Lesson(
                "distinguish-key-names-and-keys",
                "Distinguish key metadata from keys",
                "Explain why a key reference is not possession of decryption material.",
                "Use the two visibility cases:",
                prerequisites=(("read-encryption-modes", "plaintext and encrypted footers"),),
            ),
            Lesson(
                "inspect-protected-modules",
                "Inspect module boundaries and leakage",
                "Separate visible sizes and framing from protected values and verified authenticity.",
                "Distinguish visible metadata from key material:",
                prerequisites=(("distinguish-key-names-and-keys", "key names and keys"),),
            ),
            Lesson(
                "build-encryption-inspector",
                "Build the encryption inspector",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the visible file framing:",
                prerequisites=(
                    ("read-encryption-modes", "footer modes"),
                    ("inspect-protected-modules", "protected module boundaries"),
                ),
                optional=True,
            ),
        ),
        "lakehouse_and_beyond": (
            Lesson(
                "read-partition-paths",
                "Read partition values from paths",
                "Explain how a dataset can supply a partition column absent from individual files.",
                "Identify the columns and conditions a query needs:",
                prerequisites=(("separate-scan-and-filter", "scanning and filtering"),),
            ),
            Lesson(
                "prune-files-before-footers",
                "Prune files before reading their footers",
                "Use table-level statistics to avoid opening ruled-out files.",
                "Use path values and statistics:",
                prerequisites=(
                    ("read-partition-paths", "partition paths"),
                    ("rule-out-row-groups", "range-based pruning"),
                ),
            ),
            Lesson(
                "resolve-table-membership",
                "Resolve table membership from a log",
                "Distinguish files present in storage from files active in a table version.",
                "Use the table log’s file list:",
                prerequisites=(("prune-files-before-footers", "file selection from a log"),),
            ),
            Lesson(
                "build-table-reader",
                "Build the table reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to the table example:",
                prerequisites=(
                    ("read-partition-paths", "path-derived values"),
                    ("prune-files-before-footers", "file pruning"),
                    ("resolve-table-membership", "active files"),
                ),
                optional=True,
            ),
        ),
        "changing_a_table": (
            Lesson(
                "follow-snapshots-and-deletes",
                "Follow a snapshot and its deletes",
                "Explain how a snapshot changes visible rows while older data can remain stored.",
                "Distinguish stored files from active table files:",
                prerequisites=(("resolve-table-membership", "table membership"),),
            ),
            Lesson(
                "trace-a-table-lookup",
                "Trace a complete table lookup",
                "Follow the full metadata-to-row lookup chain and explain its cost.",
                "Use the snapshot’s data files and deletes:",
                prerequisites=(("follow-snapshots-and-deletes", "snapshots and position deletes"),),
            ),
            Lesson(
                "compare-update-costs",
                "Compare copy-on-write and merge-on-read",
                "Explain where update work is paid and how it changes later scans.",
                "Use the snapshot and its complete read path:",
                prerequisites=(
                    ("follow-snapshots-and-deletes", "the deleted-order example"),
                    ("trace-a-table-lookup", "finding one order"),
                ),
            ),
            Lesson(
                "decide-when-to-compact",
                "Decide when compaction repays its cost",
                "Compare immediate rewriting with expected future scan savings.",
                "Use the measured read and write trade-off:",
                prerequisites=(("compare-update-costs", "copy-on-write and merge-on-read"),),
            ),
            Lesson(
                "build-snapshot-reader",
                "Build the snapshot reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Connect code to visible rows and lookup costs:",
                prerequisites=(
                    ("follow-snapshots-and-deletes", "the snapshot and deletes"),
                    ("trace-a-table-lookup", "the complete lookup"),
                ),
                optional=True,
            ),
        ),
        "what_iceberg_adds": (
            Lesson(
                "follow-iceberg-metadata",
                "Follow Iceberg metadata to data files",
                "Explain how snapshot, manifest-list and manifest layers locate candidate files.",
                "Use snapshots and file-level pruning:",
                prerequisites=(
                    ("follow-snapshots-and-deletes", "snapshot membership"),
                    ("prune-files-before-footers", "file pruning"),
                ),
            ),
            Lesson(
                "keep-column-identity",
                "Keep column identity across schema changes",
                "Use field IDs to distinguish a rename from a different field reusing a name.",
                "Use stored column paths and table metadata:",
                prerequisites=(
                    ("follow-schema-paths", "schema paths"),
                    ("follow-iceberg-metadata", "Iceberg metadata"),
                ),
            ),
            Lesson(
                "evolve-partition-specs",
                "Evolve partitioning without renaming fields",
                "Explain why files written under different partition specs can coexist.",
                "Use stable field identities and path partitions:",
                prerequisites=(
                    ("keep-column-identity", "field IDs"),
                    ("read-partition-paths", "partition values"),
                ),
            ),
            Lesson(
                "commit-a-table-change",
                "Commit a table change safely",
                "Explain how an atomic metadata commit detects concurrent changes.",
                "Follow the metadata pointer to a snapshot:",
                prerequisites=(("follow-iceberg-metadata", "Iceberg’s metadata tree"),),
            ),
        ),
    }
)


def module_href(chapter) -> str:
    """Existing chapter URLs now name the module, never a combined reading page."""
    return f"{chapter.anchor}.html"


# Supporting destinations name their subject and the evidence they qualify.
# Keep these distinct from prerequisites: a reader may open a limitation before an example.
NOTES = {
    "why_parquet_exists": (
        "Limits of CSV and Parquet comparisons",
        "Separate measured file reads from schematic layouts, then check what each example establishes.",
        (
            ("read-fewer-columns", "CSV/Parquet byte counts"),
            ("choose-a-table-layout", "row and column layouts"),
        ),
    ),
    "anatomy_of_a_parquet_file": (
        "Footer reading: limits and sources",
        "Check the scope of the footer fixtures and simulated storage requests.",
        (("read-the-footer-map", "the tiny file’s byte map"), ("choose-a-tail-read", "tail-read strategies")),
    ),
    "the_type_system": (
        "Parquet types: coverage and older annotations",
        "Check which type interpretations the examples support and where legacy conventions need care.",
        (
            ("interpret-logical-types", "stored values and their meanings"),
            ("count-schema-levels", "maximum schema levels"),
        ),
    ),
    "nested_data": (
        "Nested data: limits and other representations",
        "Check the scope of the nested-data reader and compare levels with other representations.",
        (("nested-lists", "the nested discounts example"), ("stored-levels", "its stored level streams")),
    ),
    "encodings": (
        "Encoding results: limits and sources",
        "Distinguish measured size savings on chosen patterns from decoding speed or a general encoding rule.",
        (
            ("choose-an-encoding", "the encoding-size comparison"),
            ("dictionary-values", "dictionary decoding"),
        ),
    ),
    "pages": (
        "Page sizes, coverage and limitations",
        "Check what the small uncompressed page examples establish about page structure and sizing.",
        (
            ("walk-page-boundaries", "page headers and boundaries"),
            ("compare-page-versions", "V1 and V2 bodies"),
        ),
    ),
    "compression": (
        "Compression measurements: limits and sources",
        "Separate measured compressed sizes from codec speed, tuning and production page behaviour.",
        (
            ("compare-codec-patterns", "codec sizes by pattern"),
            ("weigh-compression-costs", "encoding and page work"),
        ),
    ),
    "metadata_and_statistics": (
        "Statistics: coverage and unsafe assumptions",
        "Check where the statistics examples stop: query decisions, shortened bounds and writer-specific errors.",
        (
            ("decide-usable-bounds", "usable typed bounds"),
            ("handle-null-and-float-statistics", "nulls and exceptional floats"),
        ),
    ),
    "skipping_data": (
        "Pruning results: limits and sources",
        "Check the planner’s scope before treating saved bytes as a prediction of query speed.",
        (
            ("compose-a-pruning-plan", "the sorted/shuffled comparison"),
            ("map-pages-to-rows", "pages and row ranges"),
        ),
    ),
    "how_readers_read": (
        "Scan costs: model limits and sources",
        "Distinguish the simulated request costs from live storage, caching and decoding time.",
        (
            ("trace-a-complete-scan", "the complete request trace"),
            ("choose-a-read-strategy", "the strategy comparison"),
        ),
    ),
    "writing_parquet_well": (
        "Writer settings: measurement limits and sources",
        "Check which reader costs the controlled writer-layout experiment measures and which costs it leaves out.",
        (
            ("compare-writer-layouts", "the seven writer layouts"),
            ("choose-writer-settings", "settings trade-offs"),
        ),
    ),
    "what_a_query_engine_does": (
        "Query costs: teaching-engine limits",
        "Check what the teaching engine’s byte counts and probe-side join experiment actually measure.",
        (
            ("separate-scan-and-filter", "the scan/filter walkthrough"),
            ("use-join-derived-filters", "the join-filter comparison"),
        ),
    ),
    "modular_encryption": (
        "Encryption inspection: limits and sources",
        "Distinguish inspecting visible framing from decrypting data or verifying authenticity.",
        (
            ("read-encryption-modes", "the two footer modes"),
            ("inspect-protected-modules", "visible module boundaries"),
        ),
    ),
    "lakehouse_and_beyond": (
        "Table logs: example limits and sources",
        "Check what the nine-file table and its small log leave out about production tables.",
        (
            ("prune-files-before-footers", "the three file-selection strategies"),
            ("resolve-table-membership", "the active-file history"),
        ),
    ),
    "changing_a_table": (
        "Snapshots and updates: model limits",
        "Check the snapshot model’s assumptions about deletes, concurrent writers, retained history and rewrite costs.",
        (
            ("follow-snapshots-and-deletes", "the snapshot and delete example"),
            ("compare-update-costs", "the update-cost comparison"),
        ),
    ),
    "what_iceberg_adds": (
        "Iceberg examples: coverage and limitations",
        "Distinguish the teaching table from real Iceberg metadata, commits and engine support.",
        (("follow-iceberg-metadata", "the metadata tree"), ("keep-column-identity", "the field-ID example")),
    ),
}

PRACTICE = {
    "why_parquet_exists": (
        "Practise choosing row and column layouts",
        "Apply column selection and record lookup trade-offs to new workloads, without running code.",
        (("read-fewer-columns", "measured column reads"), ("choose-a-table-layout", "layout choices")),
    ),
    "what_a_query_engine_does": (
        "Practise reasoning about Parquet queries",
        "Explain which query stages can save reads and which must inspect values.",
        (
            ("separate-scan-and-filter", "scan and filter stages"),
            ("answer-from-metadata", "metadata-only answers"),
        ),
    ),
    "what_iceberg_adds": (
        "Practise reasoning about Iceberg table changes",
        "Apply file membership, stable field identity and partition evolution to new table changes.",
        (("keep-column-identity", "field identity"), ("evolve-partition-specs", "partition evolution")),
    ),
}

COMPARISONS = {
    "what_a_query_engine_does": (
        "Compare Parquet query costs",
        "Compare bytes and decoded values across query shapes; these counts do not measure execution time.",
        (
            ("separate-scan-and-filter", "scan and filter stages"),
            ("answer-from-metadata", "metadata-only answers"),
        ),
    ),
    "what_iceberg_adds": (
        "Compare table-format responsibilities",
        "Locate Iceberg’s responsibilities above Parquet, then compare its approach with Delta Lake and Hudi.",
        (("follow-iceberg-metadata", "Iceberg metadata"), ("commit-a-table-change", "table commits")),
    ),
}


def resources(chapter) -> tuple[Lesson, ...]:
    items = []
    for kind, catalogue in (("notes", NOTES), ("practice", PRACTICE), ("comparison", COMPARISONS)):
        if chapter.slug not in catalogue:
            continue
        title, outcome, prerequisites = catalogue[chapter.slug]
        items.append(
            Lesson(
                f"{chapter.anchor}-{kind}",
                title,
                outcome,
                "Examples discussed:" if kind == "notes" else "Start with:",
                optional=True,
                kind=kind,
                prerequisites=prerequisites,
            )
        )
    return tuple(items)


def reading_pages(canonical: list[dict]) -> list[dict]:
    """The core route visits every module and lesson, skipping optional labs/resources."""
    pages = []
    for page in canonical:
        if page["source"].startswith("appendices/"):
            continue
        chapter = page.get("chapter")
        if not chapter:
            pages.append(page)
            continue
        pages.append({**page, "module": True})
        pages.extend(lesson_page(page, lesson) for lesson in MODULES[chapter.slug] if not lesson.optional)
    return pages


def lesson_page(page: dict, lesson: Lesson) -> dict:
    return {**page, "href": lesson.href, "title": lesson.title, "lesson": lesson}


def lesson_nodes(mdast: dict, chapter_slug: str) -> dict[str, dict]:
    """Partition canonical block wrappers; keep examples, tables and code pairs whole."""

    def blocks(node):
        for child in node.get("children", []):
            if child["type"] == "block":
                yield from blocks(child)
            else:
                yield copy.deepcopy(child)

    expected = [lesson.slug for lesson in MODULES[chapter_slug]] + ["reference"]
    found = []
    groups = {"overview": {"type": "root", "children": []}}
    current = "overview"
    for node in blocks(mdast):
        if node["type"] == "code" and node.get("lang") == "lesson":
            current = node["value"].strip()
            found.append(current)
            groups[current] = {"type": "root", "children": []}
        else:
            groups[current]["children"].append(node)
    if found != expected:
        raise ValueError(f"{chapter_slug}: lesson markers {found!r}, expected {expected!r}")
    if any(not group["children"] for name, group in groups.items() if name != "overview"):
        raise ValueError(f"{chapter_slug}: empty lesson")
    return groups


def supporting_nodes(groups: dict, chapter) -> dict[str, dict]:
    """Give problems, comparisons and limitations actual destinations, without a full page."""
    notes, problems, comparison = [], [], []
    destination = notes
    extra = chapter.slug in ("what_a_query_engine_does", "what_iceberg_adds")
    if extra:
        destination = comparison
    for node in groups["reference"]["children"]:
        if node.get("type") == "heading" and node.get("depth") == 2:
            title = node_text(node)
            destination = problems if title == "Problems" else notes
        destination.append(node)
    result = {
        "notes": {"type": "root", "children": notes},
        "practice": {"type": "root", "children": problems},
        "comparison": {"type": "root", "children": comparison},
    }
    build = next((lesson for lesson in MODULES[chapter.slug] if lesson.optional), None)
    if build:
        groups[build.slug]["children"].extend(problems)
    return result


def node_text(node) -> str:
    if "value" in node:
        return str(node["value"])
    return "".join(node_text(child) for child in node.get("children", []))


def module_card(chapter) -> str:
    lessons = MODULES[chapter.slug]
    core = [lesson for lesson in lessons if not lesson.optional]
    items = "".join(
        f'<li data-lesson="{lesson.slug}"><a href="{lesson.href}">{html.escape(lesson.title)}</a>'
        f"<p>{html.escape(lesson.outcome)}</p></li>"
        for lesson in core
    )
    optional = tuple(lesson for lesson in lessons if lesson.optional) + resources(chapter)
    links = "".join(
        f'<li data-lesson="{lesson.slug}"><a href="{lesson.href}">{html.escape(lesson.title)}</a></li>'
        for lesson in optional
    )
    return (
        '<section class="module-card" aria-label="Lessons in this module">'
        '<p class="eyebrow">Choose a lesson</p>'
        "<p>Follow these lessons in order. Each ends with a fresh case you can reason through without running code.</p>"
        f'<ol class="lesson-list">{items}</ol><div class="module-resources">'
        f"<p>Optional labs and supporting material</p><ul>{links}</ul></div></section>"
    )


def lesson_intro(chapter, lesson: Lesson) -> str:
    core = [item for item in MODULES[chapter.slug] if not item.optional]
    position = (
        {"notes": "Module notes", "practice": "Further practice", "comparison": "Optional comparison"}.get(
            lesson.kind, "Optional build lab"
        )
        if lesson.optional
        else f"Lesson {core.index(lesson) + 1} of {len(core)}"
    )
    links = "; ".join(
        f'<a href="{html.escape(slug, quote=True)}.html">{html.escape(label)}</a>'
        for slug, label in lesson.prerequisites
    )
    preparation = html.escape(lesson.preparation)
    if links:
        preparation += f" {links}."
    purpose = "On this page" if lesson.kind in ("notes", "comparison") else "Your goal"
    return (
        '<div class="lesson-intro reading-guide">'
        f'<p class="eyebrow">{position} · <a href="{module_href(chapter)}">{html.escape(chapter.title)}</a></p>'
        f"<p><strong>{purpose}:</strong> {html.escape(lesson.outcome)}</p>"
        f'<p class="lesson-preparation">{preparation}</p></div>'
    )


def reference_links(body: str, canonical_href: str) -> str:
    """Resolve local fragment links against the canonical source for the ownership pass."""
    ids = set(re.findall(r'\bid="([^"]+)"', body))
    return re.sub(
        r'href="#([^"]+)"',
        lambda match: match[0] if match[1] in ids else f'href="{canonical_href}#{match[1]}"',
        body,
    )


def migrate_links(body: str, anchors: dict[str, str]) -> str:
    return re.sub(r'href="([^"]+)"', lambda match: f'href="{anchors.get(match[1], match[1])}"', body)


def legacy_navigation(body: str, chapter, anchors: dict[str, str]) -> str:
    """Old deep links open the owning lesson; without JS they land on its module entry."""
    prefix = module_href(chapter) + "#"
    mapping = {key[len(prefix) :]: value for key, value in anchors.items() if key.startswith(prefix)}
    present = set(re.findall(r'\bid="([^"]+)"', body))
    for lesson in (*MODULES[chapter.slug], *resources(chapter)):
        old_ids = [
            key
            for key, value in mapping.items()
            if (value.startswith(lesson.href + "#") or value == lesson.href) and key not in present
        ]
        targets = "".join(
            f'<span id="{html.escape(key, quote=True)}" class="legacy-anchor"></span>' for key in old_ids
        )
        body = body.replace(f'<li data-lesson="{lesson.slug}">', f'<li data-lesson="{lesson.slug}">{targets}')
    encoded = json.dumps(mapping).replace("</", "<\\/")
    return (
        body
        + f"""<script>(() => {{
const targets = {encoded};
let fragment = location.hash.slice(1);
try {{ fragment = decodeURIComponent(fragment); }} catch (e) {{}}
const target = targets[fragment];
if (target && target.split("#")[0] !== location.pathname.split("/").pop()) location.replace(target);
}})();</script>"""
    )
