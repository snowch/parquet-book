"""Teaching evidence must agree with the fixture and actual reader traces."""

import json
from pathlib import Path

import pytest

from tools.learning import evidence, render_learning

ROOT = Path(__file__).resolve().parent.parent


def test_practice_answers_match_writer_manifest_and_bytes():
    manifest = json.loads((ROOT / "fixtures/tiny.json").read_text())
    data = (ROOT / "fixtures/tiny.parquet").read_bytes()
    report = evidence()
    assert report["byte"] == data[0]
    assert report["size"] == manifest["file_size"]
    assert report["length"] == manifest["footer_length"]
    assert report["start"] == len(data) - 8 - manifest["footer_length"]
    assert sum(value * weight for value, weight in report["terms"]) == manifest["footer_length"]
    chunk = report["chunk"]
    assert chunk["end"] - chunk["start"] > 0
    assert chunk["end"] <= report["start"]


def test_request_choices_cover_footer_without_duplicate_file_bytes():
    d = evidence()
    assert len(d["cases"]) == len(d["sizes"]) * 3
    for case in d["cases"]:
        requests = case["requests"]
        assert sum(r["method"] == "HEAD" for r in requests) == (case["mode"] == "head")
        gets = [r for r in requests if r["method"] == "GET"]
        assert len(gets) == 1 + (case["prefetch"] < d["length"] + 8)
        fetched = set()
        for request in gets:
            raw = request["range"].removeprefix("bytes=")
            if raw.startswith("-"):
                start, end = d["size"] - int(raw[1:]), d["size"] - 1
            else:
                start, end = map(int, raw.split("-"))
            offsets = set(range(start, end + 1))
            assert not fetched & offsets
            assert len(offsets) == request["bytes"]
            fetched |= offsets
        assert set(range(d["start"], d["size"])) <= fetched
        assert len(fetched) == case["bytes"]


@pytest.mark.parametrize("name", ["byte", "length", "start", "chunk", "requests"])
def test_no_javascript_view_keeps_evidence_and_explanations(name):
    rendered = render_learning(name)
    assert 'class="learning-controls" hidden' in rendered
    assert "<details>" in rendered
    assert "<table>" in rendered or "Reveal the explanation" in rendered


def test_unknown_check_fails_instead_of_silently_losing_content():
    with pytest.raises(ValueError):
        render_learning("missing")
