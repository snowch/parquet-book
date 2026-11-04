"""Static figures must preserve the reader's answers and remain usable without JavaScript."""

from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.render import render

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "chapters" / "_generated"
SVG = "{http://www.w3.org/2000/svg}"
sys.path.insert(0, str(ROOT / "python"))

from parquet_lab import report  # noqa: E402


def labels(name):
    return [n.text or "" for n in ET.parse(GENERATED / f"visual-{name}.svg").iter(f"{SVG}text")]


@pytest.mark.parametrize("path", sorted(GENERATED.glob("visual-*.svg")), ids=lambda p: p.stem)
def test_figures_have_alternatives_and_are_published_under_the_base_path(path):
    svg = ET.parse(path).getroot()
    assert svg.find(f"{SVG}title").text
    assert len(svg.find(f"{SVG}desc").text) > 80
    assert svg.get("aria-labelledby") == "title description"
    assert not list(svg.iter(f"{SVG}script"))
    md = path.with_suffix(".md").read_text()
    assert ":alt: " in md and md.rstrip().endswith("*")
    html = render(
        {
            "type": "image",
            "url": f"/{path.stem}-myst-hash.svg",
            "urlSource": f"_generated/{path.name}",
            "alt": svg.find(f"{SVG}desc").text,
        }
    )
    assert f'src="{path.name}"' in html
    assert f'href="{path.name}"' in html
    assert 'tabindex="0"' in html and 'role="region"' in html
    assert 'width="680"' in html and 'height="' in html


def test_footer_diagram_locates_the_footer_from_the_fixture_bytes():
    data = (ROOT / "fixtures/tiny.parquet").read_bytes()
    length = int.from_bytes(data[-8:-4], "little")
    assert f"Footer starts at {len(data)} − 8 − {length} = {len(data) - 8 - length}" in labels("footer")


def test_layout_marks_the_selected_columns_in_both_storage_orders():
    with (ROOT / "fixtures/formats/eight-orders.csv").open() as file:
        rows = list(csv.reader(file))
    wanted = [name in {"country", "amount_cents"} for name in rows[0]]
    count = len(rows) - 1
    expected = wanted * count + [selected for selected in wanted for _ in range(count)]
    svg = ET.parse(GENERATED / "visual-layouts.svg")
    cells = [n for n in svg.iter(f"{SVG}rect") if n.get("height") == "32"]
    assert len(cells) == len(expected)
    assert [n.get("fill") == "#dceaf5" for n in cells] == expected
    assert labels("layouts").count("•") == sum(expected)


def test_nested_records_and_slots_match_the_independent_python_reader():
    data = (ROOT / "fixtures/nested.parquet").read_bytes()
    tags = report.levels(data, 2)
    shown = labels("nested-tags")
    for record in tags["records"]:
        assert json.dumps(record["tags"], separators=(",", ":")) in shown
    # The columns have fixed x positions, so each repetition/definition/value remains aligned.
    texts = list(ET.parse(GENERATED / "visual-nested-tags.svg").iter(f"{SVG}text"))
    slots = {}
    for node in texts:
        if node.get("x") in {"310", "370", "430"} and int(node.get("y")) > 75:
            slots.setdefault(node.get("y"), []).append(node.text)
    expected = [
        [str(t["rep"]), str(t["def"]), str(t["value"]) if t["value"] is not None else "∅ (no value)"]
        for t in tags["triples"]
    ]
    assert list(slots.values()) == expected
    shown = labels("nested-discounts")
    for t in report.levels(data, 4)["triples"]:
        value = str(t["value"]) if t["value"] is not None else "∅"
        assert f"({t['rep']}, {t['def']}, {value})" in shown


def test_query_counts_are_the_engine_results_not_an_illustrated_guess():
    sql = "SELECT country, count(*) FROM orders WHERE order_id < 300 GROUP BY country ORDER BY country"
    result = report.query((ROOT / "fixtures/writing-baseline.parquet").read_bytes(), sql)
    shown = labels("query-stages")
    for stage in result["stages"]:
        assert stage["name"] in shown
        assert f"{stage['rows_in']} rows → {stage['rows_out']} rows" in shown


def test_pruning_labels_agree_with_the_reader_for_both_layouts():
    expected = []
    for file in ("pruning-sorted.parquet", "pruning-shuffled.parquet"):
        result = report.skipping((ROOT / "fixtures" / file).read_bytes(), 0, "=", "431", 1)
        expected += ["SKIP" if g["skipped"] else "KEEP" for g in result["row_groups"]]
    assert [s for s in labels("pruning") if s in {"KEEP", "SKIP"}] == expected
