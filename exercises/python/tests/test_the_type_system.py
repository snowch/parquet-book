"""Grades ch03's problems. Run with::

python3 -m pytest exercises/python/tests/test_the_type_system.py --problems
"""

import pytest
from parquet_lab import logical, schema
from parquet_lab.bytes import Span
from parquet_lab.metadata import PhysicalType, SchemaElement
from parquet_lab.report import open_bytes
from the_type_system import decimal_from_bytes, leaf_paths, max_levels

from fixtures import Rng, fixtures

REPETITIONS = [schema.REQUIRED, schema.OPTIONAL, schema.REPEATED]


def element(name, children=None, rep=None, physical=None) -> SchemaElement:
    return SchemaElement(
        name=name,
        physical_type=PhysicalType(physical) if physical is not None else None,
        type_length=None,
        repetition=rep,
        num_children=children,
        converted_type=None,
        logical_type=None,
        scale=None,
        precision=None,
        field_id=None,
        span=Span(0, 0),
    )


def random_schema(rng: Rng) -> list[SchemaElement]:
    """A random schema, flattened depth-first, as the footer would store it."""
    out: list[SchemaElement] = []
    count = [0]

    def node(depth: int) -> None:
        is_group = depth < 4 and rng.next(3) == 0
        rep = ["REQUIRED", "OPTIONAL", "REPEATED"][rng.next(3)]
        count[0] += 1
        e = element(f"f{count[0]}", None, rep, None if is_group else 1)
        out.append(e)
        if is_group:
            e.num_children = 1 + rng.next(3)
            for _ in range(e.num_children):
                node(depth + 1)

    n = 1 + rng.next(4)
    out.append(element("schema", n))
    for _ in range(n):
        node(1)
    return out


def flat(elements: list[SchemaElement]) -> list[tuple[str, int]]:
    return [(e.name, e.num_children or 0) for e in elements]


@pytest.mark.problem("3.1")
def test_problem_3_1_leaf_paths_match_pyarrow():
    for name, data, manifest in fixtures():
        expected = [leaf["path"] for leaf in manifest["leaves"]]
        assert leaf_paths(flat(open_bytes(data).schema)) == expected, name


@pytest.mark.problem("3.1")
def test_problem_3_1_leaf_paths_match_the_reader_on_generated_schemas():
    rng = Rng(0x2545_F491_4F6C_DD1D)
    for _ in range(500):
        elements = random_schema(rng)
        expected = [leaf.dotted_path() for leaf in schema.leaves(schema.build(elements))]
        assert leaf_paths(flat(elements)) == expected, (
            f"schema {flat(elements)}: a group's children are the next num_children subtrees, not "
            "the next num_children elements"
        )


@pytest.mark.problem("3.2")
def test_problem_3_2_max_levels_for_every_path_up_to_five_deep():
    for length in range(6):
        for code in range(3**length):
            path = [REPETITIONS[(code // 3**i) % 3] for i in range(length)]
            assert tuple(max_levels(path)) == schema.max_levels(path), path


@pytest.mark.problem("3.2")
def test_problem_3_2_max_levels_match_pyarrow():
    for name, data, manifest in fixtures():
        leaves = schema.leaves(schema.build(open_bytes(data).schema))
        for leaf, e in zip(leaves, manifest["leaves"], strict=True):
            want = (e["max_definition_level"], e["max_repetition_level"])
            assert tuple(max_levels(leaf.repetitions)) == want, f"{name} {leaf.dotted_path()}"


@pytest.mark.problem("3.3")
def test_problem_3_3_the_fixture_decimals_match_pyarrow():
    _, data, manifest = next(f for f in fixtures() if f[0] == "types.parquet")
    chunk = next(c for c in open_bytes(data).row_groups[0].columns if c.dotted_path() == "amount")
    expected = next(c for c in manifest["row_groups"][0]["columns"] if c["path"] == "amount")["statistics"]
    assert decimal_from_bytes(chunk.statistics.min_value, 2) == expected["min"]
    assert decimal_from_bytes(chunk.statistics.max_value, 2) == expected["max"]


@pytest.mark.problem("3.3")
def test_problem_3_3_generated_decimals():
    rng = Rng(0x9E37_79B9_7F4A_7C15)
    for _ in range(2000):
        data = bytes(rng.next(256) for _ in range(1 + rng.next(16)))
        scale = 1 + rng.next(6)
        want = logical.decimal(logical.be_twos_complement(data), scale)
        assert decimal_from_bytes(data, scale) == want, (
            f"bytes {data.hex(' ')}, scale {scale}: if the sign is wrong, check the top bit of the "
            "first byte; if the digits are, check you read most significant first"
        )


def test_generated_schemas_are_varied():
    """Scaffolding, not a problem: the generated schemas include groups, nesting and every
    repetition, so problem 3.1 cannot pass by treating the list as flat."""
    rng = Rng(0x2545_F491_4F6C_DD1D)
    nested = repeated = False
    for _ in range(500):
        for leaf in schema.leaves(schema.build(random_schema(rng))):
            nested |= len(leaf.path) > 2
            repeated |= leaf.max_repetition_level > 1
    assert nested and repeated
