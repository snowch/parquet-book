"""The reader's problems in Python. Each test marked ``problem`` fails until you solve it, so a
plain ``pytest`` skips them, as ``cargo test`` skips the Rust ones; run them with ``--problems``::

    python3 -m pytest exercises/python --problems

Like the Rust tests, none stores an answer. Each computes what it expects at test time, from the
book's reader or from what pyarrow wrote about a fixture.
"""

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
# The book's Python reader, which the tests compare your answers with. The graders load each stub
# by its file (tests/fixtures.py), because a chapter's name can be a standard module's too
# (`encodings`); this directory goes last on the path, so one stub can still import another.
sys.path.insert(0, str(HERE.parent.parent / "python"))
sys.path.append(str(HERE))


def pytest_addoption(parser):
    parser.addoption("--problems", action="store_true", help="run the problems, which fail until solved")


def pytest_configure(config):
    config.addinivalue_line("markers", "problem(number): a problem's test, run with --problems")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--problems"):
        return
    skip = pytest.mark.skip(reason="a problem: fails until you solve it; run with --problems")
    for item in items:
        if item.get_closest_marker("problem"):
            item.add_marker(skip)
