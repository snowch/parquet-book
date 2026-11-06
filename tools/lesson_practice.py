"""Fresh no-code cases; numeric answers come from the reader, not hand-written outputs."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
from parquet_lab import metadata, nested, rle, schema  # noqa: E402
from parquet_lab.column import Triple  # noqa: E402
from parquet_lab.format import footer_span, parse_trailer  # noqa: E402


def exercise(question: str, answer: str, evidence: str = "") -> str:
    return (
        '<aside class="lesson-practice"><p class="eyebrow">Try a fresh case</p>'
        f"{evidence}<p>{html.escape(question)}</p>"
        "<details><summary>Check your reasoning</summary>"
        f"<p>{html.escape(answer)}</p></details></aside>"
    )


def table(headers, rows) -> str:
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join(f'<th scope="col">{html.escape(str(h))}</th>' for h in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def render_transfer(case: str) -> str:
    if case == "run-example":
        raw, width, count = bytes([4, 1]), 2, 2
        values = rle.values(rle.decode(raw, 0, width, count))
        return (
            '<div class="run-example"><p><strong>A complete RLE example.</strong> '
            f"Schematic bytes <code>{raw.hex(' ')}</code>, with a bit width of {width}. "
            f"The header {raw[0]:02x} is binary {raw[0]:b}. Its rightmost bit is zero, so this is RLE. "
            f"The remaining bits give {raw[0] >> 1} repeats; the next byte supplies the value {raw[1]}. "
            f"The reader decodes <code>{values}</code>. No packed group or padding is needed.</p></div>"
        )
    if case in ("footer", "chunk"):
        data = (ROOT / "fixtures/multiple-row-groups.parquet").read_bytes()
        trailer = parse_trailer(data[-8:], len(data))
        span = footer_span(len(data), trailer.footer_length)
        source = "<p>A different real file: <code>multiple-row-groups.parquet</code>. These inputs are decoded by the reader.</p>"
        if case == "footer":
            question = (
                f"This file has {len(data)} bytes. Its trailer is eight bytes, and the decoded footer length is {trailer.footer_length}. "
                "Where does the footer start and end? Would a length equal to the entire file size be valid? Explain both answers."
            )
            answer = (
                f"{len(data)} − 8 − {trailer.footer_length} = {span.start}. The footer occupies [{span.start}, {span.end}). "
                "A length equal to the file size would put its start before the file; reject it before requesting those bytes. "
                "A span must also leave room for the opening magic."
            )
        else:
            md = metadata.decode_file_metadata(data[span.start : span.end], span.start)
            chunk = md.row_groups[-1].columns[0]
            region = chunk.byte_range()
            question = (
                f"The last row group's {'.'.join(chunk.path)} chunk occupies [{region.start}, {region.end}). "
                "Write an inclusive HTTP byte range. Does this mean the footer contains the column's values?"
            )
            answer = (
                f"bytes={region.start}-{region.end - 1}. Fetch {region.length} bytes. "
                "The excluded end is not a byte to fetch. The footer describes the chunk; the chunk's pages store its values."
            )
        return exercise(question, answer, source)

    if case in ("scalar", "list", "nested"):
        data = (ROOT / "fixtures/nested.parquet").read_bytes()
        trailer = parse_trailer(data[-8:], len(data))
        span = footer_span(len(data), trailer.footer_length)
        md = metadata.decode_file_metadata(data[span.start : span.end], span.start)
        tree = schema.build(md.schema)
        path, inputs = {
            "scalar": (["email"], [(0, 0, None), (0, 1, b"new@example.test")]),
            "list": (
                ["tags", "list", "element"],
                [
                    (0, 1, None),
                    (0, 3, b"violet"),
                    (1, 2, None),
                    (0, 0, None),
                ],
            ),
            "nested": (
                ["items", "list", "element", "discounts", "list", "element"],
                [
                    (0, 6, 7),
                    (2, 6, 9),
                    (1, 4, None),
                ],
            ),
        }[case]
        leaf = next(leaf for leaf in schema.leaves(tree) if leaf.path == path)
        fields = nested.path_fields(tree, leaf)
        triples = [Triple(r, d, value, None, [], 0) for r, d, value in inputs]
        records = nested.assemble(fields, leaf, triples)
        evidence = "<p>Schematic input using the fixture’s schema, with fresh slots and values. The answer is reconstructed by the book’s reader, not read from another file.</p>"
        evidence += table(
            ["r", "d", "Stored value"],
            [
                (r, d, "none" if v is None else v.decode() if isinstance(v, bytes) else v)
                for r, d, v in inputs
            ],
        )
        questions = {
            "scalar": "Rebuild the email records. Does the missing value remove its record?",
            "list": "Rebuild the tags records. Explain which slot represents an empty list, which a null element and which a null list.",
            "nested": "Rebuild this column's view of items and discounts. Does r = 1 begin a new order or a new item?",
        }
        reasons = {
            "scalar": "The null still occupies a record; r = 0 starts each record.",
            "list": "d = 1 is an empty container; d = 2 is a null element in a present list; d = 0 is a null list. r = 1 continues the same record.",
            "nested": "There is one record with two items. r = 2 continues the first item's discounts; r = 1 starts the second item, whose discounts list is empty. This column cannot reconstruct sku values.",
        }
        return exercise(
            questions[case],
            json.dumps(records) + " " + reasons[case],
            evidence,
        )

    if case == "run":
        raw, width, count = bytes([6, 3]), 2, 3
        values = rle.values(rle.decode(raw, 0, width, count))
        return exercise(
            "A separate schematic level stream has bytes 06 03 (hex), a bit width of two and three slots. "
            "Is this an RLE run or a bit-packed run? Which levels does it produce?",
            f"The header 06 has low bit zero: RLE. Its remaining bits give a count of three, and the next byte is the repeated value. "
            f"The reader decodes {values}. The bit-packed example earlier used the other header kind; not every stream has padding.",
        )
    raise ValueError(f"unknown transfer case {case!r}")
