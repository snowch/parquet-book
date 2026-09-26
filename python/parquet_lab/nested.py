"""Nested data: repetition and definition levels, and records rebuilt from them (ch04).

A column stores a flat sequence of values, but a record can hold nulls, lists, and lists of
structs holding lists. Parquet keeps the shape by storing two small integers beside every value
slot, as the Dremel paper describes:

- the **definition level** ``d`` counts how many of the optional and repeated fields on the path
  are present. At the maximum, the value is there. Below it, the field at depth ``d + 1`` is the
  first one missing, which says whether the value is null, or its list empty, or its parent
  absent.
- the **repetition level** ``r`` says where a new element starts. Zero starts a new record. A
  higher level continues the record and starts a new element in the list whose repeated field
  has that repetition level.

This module names each field on a leaf's path with the levels at which it appears, explains any
triple in those terms, and reassembles records from a column's triples.
"""

from __future__ import annotations

from dataclasses import dataclass

from .column import Triple
from .logical import value_json
from .schema import OPTIONAL, REPEATED, Leaf, SchemaNode


@dataclass
class PathField:
    """One field on the path from the root to a leaf."""

    name: str
    repetition: str
    definition: int
    """The definition level a value has when this field is present."""
    rep: int
    """The repetition level that starts a new element of this field, if it is repeated; for
    other fields, the repetition level of the nearest repeated field above it."""
    is_list: bool
    """Annotated ``LIST``: a group whose repeated child is the list itself."""
    label: str
    """How the book names this field: ``items[].sku`` rather than ``items.list.element.sku``."""


def path_fields(root: SchemaNode, leaf: Leaf) -> list[PathField]:
    """The fields on a leaf's path, with their levels."""
    out: list[PathField] = []
    node = root
    definition = rep = 0
    label = ""
    parent_is_list = in_list_element = False
    for name in leaf.path:
        child = next((c for c in node.children if c.name == name), None)
        if child is None:
            break
        if child.repetition == OPTIONAL:
            definition += 1
        elif child.repetition == REPEATED:
            definition += 1
            rep += 1
        # Name the field the way a reader of the data would: a LIST's repeated group and its
        # element vanish into `[]`.
        if parent_is_list and child.repetition == REPEATED:
            label += "[]"
            in_list_element = True
        elif in_list_element:
            in_list_element = False
        else:
            label += ("." if label else "") + child.name
        is_list = child.logical_type is not None and child.logical_type.name == "LIST"
        out.append(PathField(child.name, child.repetition, definition, rep, is_list, label))
        parent_is_list = is_list
        node = child
    return out


def explain(fields: list[PathField], t: Triple) -> str:
    """What a triple says, in words."""
    max_def = fields[-1].definition if fields else 0
    if t.rep == 0:
        starts = "starts a new record"
    else:
        f = next((f for f in fields if f.repetition == REPEATED and f.rep == t.rep), None)
        starts = (
            f"adds an element to `{_list_name(fields, f)}`"
            if f
            else f"repetition level {t.rep} matches no repeated field"
        )
    if t.definition >= max_def:
        defined = "the value is present"
    else:
        # The first field whose presence would have raised the level past `d`.
        i = next((i for i, f in enumerate(fields) if f.definition > t.definition), None)
        if i is None:
            defined = f"definition level {t.definition} is above the maximum"
        elif fields[i].repetition == REPEATED:
            defined = f"`{_list_name(fields, fields[i])}` is an empty list"
        elif i > 0 and fields[i - 1].repetition == REPEATED:
            defined = f"an element of `{_list_name(fields, fields[i - 1])}` is null"
        else:
            defined = f"`{fields[i].label}` is null"
    return f"{starts}; {defined}"


def _list_name(fields: list[PathField], repeated: PathField) -> str:
    """The name of the list a repeated field makes: the ``LIST`` group above it when there is
    one."""
    i = next(i for i, f in enumerate(fields) if f is repeated)
    return fields[i - 1].label if i > 0 and fields[i - 1].is_list else repeated.label


def assemble(fields: list[PathField], leaf: Leaf, triples: list[Triple]) -> list[dict]:
    """Rebuild each record's value for this one column: the record with only this leaf's path in
    it.

    Records are split where ``r == 0``. Within a record, each field's value is built from the
    triples that belong to one instance of it:

    - a repeated field's triples split into elements wherever ``r`` is at most its repetition
      level; if the first triple's ``d`` says the field is absent, the list is empty;
    - an optional field whose first triple's ``d`` says it is absent is null;
    - a leaf's value is the one triple's value.

    A ``LIST``-annotated group becomes an array of its elements, as readers present it, and each
    value is read through the leaf's logical type.
    """

    def field_value(i: int, ts: list[Triple]) -> object:
        """The value of ``fields[i]``, given the triples of one instance of its parent."""
        f = fields[i]
        if f.repetition == REPEATED:
            if ts[0].definition < f.definition:
                return []
            elements, start = [], 0
            for j in range(1, len(ts) + 1):
                if j == len(ts) or ts[j].rep <= f.rep:
                    elements.append(element_value(i, ts[start:j]))
                    start = j
            return elements
        if ts[0].definition < f.definition:
            return None
        if f.is_list and i + 1 < len(fields):
            # A LIST group is its list: present it as the array, not as a struct holding one.
            return field_value(i + 1, ts)
        return element_value(i, ts)

    def element_value(i: int, ts: list[Triple]) -> object:
        """One present instance of ``fields[i]``: the value, or a struct of the next field."""
        if i + 1 == len(fields):
            v = ts[0].value
            return None if v is None else value_json(leaf.physical_type, leaf.logical_type, v)
        if i > 0 and fields[i - 1].is_list and fields[i].repetition == REPEATED:
            # The repeated group of a LIST: its one child is the element, shown directly.
            return field_value(i + 1, ts)
        return {fields[i + 1].name: field_value(i + 1, ts)}

    records, start = [], 0
    for i in range(1, len(triples) + 1):
        if i == len(triples) or triples[i].rep == 0:
            if i > start:
                records.append({fields[0].name: field_value(0, triples[start:i])})
            start = i
    return records
