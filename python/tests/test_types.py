"""ch03: the schema tree and logical types. The Rust modules of the same names carry the same
tests."""

from __future__ import annotations

import struct

import pytest
from parquet_lab import report
from parquet_lab.logical import (
    LogicalType,
    be_twos_complement,
    date_from_days,
    decimal,
    f16_to_float,
    int96_timestamp,
    interpret,
    timestamp,
)
from parquet_lab.schema import OPTIONAL, REPEATED, REQUIRED, build, leaves, max_levels
from test_fixtures import FIXTURES, IDS


def test_day_numbers_are_dates():
    assert date_from_days(0) == "1970-01-01"
    assert date_from_days(20456) == "2026-01-03"
    assert date_from_days(-1) == "1969-12-31"
    assert date_from_days(11016) == "2000-02-29"


def test_timestamps_keep_their_unit_and_their_zone():
    assert timestamp(0, "MICROS", True) == "1970-01-01T00:00:00Z"
    assert timestamp(1_767_432_600_000_000, "MICROS", True) == "2026-01-03T09:30:00Z"
    assert timestamp(1_500, "MILLIS", False) == "1970-01-01T00:00:01.500"
    assert timestamp(-1, "NANOS", True) == "1969-12-31T23:59:59.999999999Z"


def test_decimals_put_the_point_where_the_scale_says():
    assert decimal(12345, 2) == "123.45"
    assert decimal(-5, 2) == "-0.05"
    assert decimal(500, 2) == "5.00"
    assert decimal(7, 0) == "7"
    assert decimal(7, -2) == "700"


def test_decimal_bytes_are_big_endian_twos_complement():
    assert be_twos_complement(bytes([0x00, 0x00, 0x07, 0xCF])) == 1999
    assert be_twos_complement(bytes([0xFF, 0xFF])) == -1
    assert be_twos_complement(bytes([0x80])) == -128
    assert be_twos_complement(b"") is None


def test_the_same_bytes_mean_what_the_logical_type_says():
    assert interpret(1, LogicalType("DATE"), struct.pack("<i", 20456)) == "2026-01-03"
    unsigned = LogicalType("INTEGER", bit_width=32, signed=False)
    assert interpret(1, unsigned, struct.pack("<i", -1)) == "4294967295"
    dec = LogicalType("DECIMAL", scale=2, precision=9)
    assert interpret(7, dec, bytes([0, 0, 0x01, 0xF4])) == "5.00"


def test_half_floats_decode():
    assert f16_to_float(0x3C00) == 1.0
    assert f16_to_float(0xC000) == -2.0
    assert f16_to_float(0x3555) == 0.333251953125


def test_int96_is_nanoseconds_and_a_julian_day():
    data = struct.pack("<qi", 3_600_000_000_000, 2_440_589)
    assert int96_timestamp(data) == "1970-01-02T01:00:00"


def test_levels_count_the_fields_that_may_be_absent_and_that_repeat():
    assert max_levels([]) == (0, 0)
    assert max_levels([REQUIRED, OPTIONAL]) == (1, 0)
    assert max_levels([OPTIONAL, REPEATED, OPTIONAL]) == (3, 1)


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_the_rebuilt_tree_has_pyarrows_leaves(name, data, manifest):
    found = leaves(build(report.open_bytes(data).schema))
    assert [leaf.dotted_path() for leaf in found] == [e["path"] for e in manifest["leaves"]]
    for leaf, e in zip(found, manifest["leaves"], strict=True):
        assert leaf.max_definition_level == e["max_definition_level"]
        assert leaf.max_repetition_level == e["max_repetition_level"]
        assert leaf.physical_type.name == e["physical_type"]


def test_logical_types_read_statistics_the_way_pyarrow_does():
    # pyarrow reports statistics already converted through the logical type. The reader applies
    # the logical type itself, to the raw bytes, and must arrive at the same values. Only the
    # spelling differs: pyarrow prints a UTC timestamp with a space and "+00:00", and strings
    # without quotes.
    def normalise(s: str) -> str:
        return s.strip('"').replace(" ", "T", 1).replace("+00:00", "Z")

    compared = 0
    for name, data, manifest in FIXTURES:
        md = report.open_bytes(data)
        found = leaves(build(md.schema))
        for rg, expected in zip(md.row_groups, manifest["row_groups"], strict=True):
            for c, e, leaf in zip(rg.columns, expected["columns"], found, strict=True):
                if leaf.logical_type is None or c.statistics is None:
                    continue
                for raw, key in ((c.statistics.min_value, "min"), (c.statistics.max_value, "max")):
                    want = (e.get("statistics") or {}).get(key)
                    if raw is None or not isinstance(want, str):
                        continue
                    got = interpret(c.physical_type, leaf.logical_type, raw)
                    assert got is not None, f"{name} {c.dotted_path()}: no reading of {raw!r}"
                    assert normalise(got) == normalise(want), f"{name} {c.dotted_path()} {key}"
                    compared += 1
    assert compared >= 10
