"""The schema: a tree, stored as a flat list (ch03).

The footer's ``schema`` field is a list of ``SchemaElement``\\ s in depth-first order. The first
is the root, which names the whole record. A group element says how many children it has, and
they follow it immediately, each with its own subtree. A leaf has no children and a physical
type, and holds data: every leaf is one column, and every column chunk in the file belongs to
exactly one leaf. ::

    flat:   schema(3)  order_id  shipping(2)  city  postcode

    tree:   schema
            ├── order_id
            └── shipping
                ├── city
                └── postcode

Rebuilding the tree needs nothing but ``num_children``. So does computing, for each leaf, the
largest definition and repetition levels its values can carry, which ch04 uses to decode them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bytes import Span
from .encoding import quote
from .logical import LogicalType
from .metadata import PhysicalType, SchemaElement

REQUIRED, OPTIONAL, REPEATED = "required", "optional", "repeated"
"""How many values a field has in each record: exactly one, zero or one, or zero or more."""


def repetition_of(name: str | None) -> str:
    return {"OPTIONAL": OPTIONAL, "REPEATED": REPEATED}.get(name or "", REQUIRED)


@dataclass
class SchemaNode:
    """A node of the rebuilt tree."""

    element: int
    """Position in the footer's flat list."""
    name: str
    repetition: str
    physical_type: PhysicalType | None
    type_length: int | None
    logical_type: LogicalType | None
    converted_type: str | None
    field_id: int | None
    span: Span
    children: list[SchemaNode] = field(default_factory=list)

    def is_leaf(self) -> bool:
        return not self.children and self.physical_type is not None


@dataclass
class Leaf:
    """A leaf column, with everything a reader needs to decode its values."""

    column: int
    """Which column this is: its position among the leaves, and so among each row group's
    column chunks."""
    path: list[str]
    """The names from the root's child down to the leaf."""
    repetitions: list[str]
    """The repetition of every field on the path, root excluded."""
    max_definition_level: int
    max_repetition_level: int
    element: int
    physical_type: PhysicalType
    type_length: int | None
    logical_type: LogicalType | None

    def dotted_path(self) -> str:
        return ".".join(self.path)


class SchemaError(ValueError):
    pass


def build(elements: list[SchemaElement]) -> SchemaNode:
    """Rebuild the tree from the footer's flat, depth-first list.

    Read an element; if it says it has ``n`` children, the next ``n`` subtrees are its children,
    each read the same way. The recursion consumes the list from the front, and the whole list
    must be consumed by the root's subtree.
    """
    if not elements:
        raise SchemaError("the schema has no elements, not even a root")
    position = [0]
    root = _subtree(elements, position)
    if position[0] != len(elements):
        raise SchemaError(
            f"the root's subtree ends before the list does; elements from {position[0]} belong to no one"
        )
    return root


def _subtree(elements: list[SchemaElement], position: list[int]) -> SchemaNode:
    index = position[0]
    e = elements[index]
    position[0] += 1
    children = []
    for _ in range(max(e.num_children or 0, 0)):
        if position[0] >= len(elements):
            raise SchemaError(
                f"group {quote(e.name)} (element {index}) claims more children than the schema has elements"
            )
        children.append(_subtree(elements, position))
    if index > 0 and not children and e.physical_type is None:
        raise SchemaError(f"element {index} ({quote(e.name)}) has no children and no physical type")
    return SchemaNode(
        element=index,
        name=e.name,
        repetition=repetition_of(e.repetition),
        physical_type=e.physical_type,
        type_length=e.type_length,
        logical_type=e.logical_type,
        converted_type=e.converted_type,
        field_id=e.field_id,
        span=e.span,
        children=children,
    )


def max_levels(path: list[str]) -> tuple[int, int]:
    """The largest definition and repetition levels a leaf's values can carry.

    Walk the path from the root's child to the leaf. Every field that may be absent (optional or
    repeated) adds one to the maximum definition level: a value is "defined to level d" when the
    first d such fields are present. Every repeated field adds one to the maximum repetition
    level. Required fields add nothing, because they are always there.
    """
    definition = sum(1 for r in path if r != REQUIRED)
    repetition = sum(1 for r in path if r == REPEATED)
    return definition, repetition


def leaves(root: SchemaNode) -> list[Leaf]:
    """Every leaf of the tree, in column order."""
    out: list[Leaf] = []

    def walk(node: SchemaNode, path: list[SchemaNode]) -> None:
        for child in node.children:
            here = [*path, child]
            if child.children:
                walk(child, here)
                continue
            repetitions = [n.repetition for n in here]
            definition, repetition = max_levels(repetitions)
            out.append(
                Leaf(
                    column=len(out),
                    path=[n.name for n in here],
                    repetitions=repetitions,
                    max_definition_level=definition,
                    max_repetition_level=repetition,
                    element=child.element,
                    physical_type=child.physical_type
                    if child.physical_type is not None
                    else PhysicalType(-1),
                    type_length=child.type_length,
                    logical_type=child.logical_type,
                )
            )

    walk(root, [])
    return out


def physical_word(t: int, type_length: int | None) -> str:
    """The physical type as the schema notation writes it: ``int64``, ``binary``,
    ``fixed_len_byte_array(4)``."""
    words = ["boolean", "int32", "int64", "int96", "float", "double", "binary"]
    if 0 <= t < len(words):
        return words[t]
    if t == 7:
        return f"fixed_len_byte_array({type_length or 0})"
    return f"type{t}"


def to_text(root: SchemaNode) -> str:
    """The tree in the textual notation Parquet tools print, which comes from the Dremel paper::

    message schema {
      required int64 order_id;
      optional group shipping {
        optional binary city (STRING);
      }
    }
    """
    out = [f"message {root.name} {{\n"]

    def line(node: SchemaNode, depth: int) -> None:
        indent = "  " * depth
        annotation = f" ({node.logical_type})" if node.logical_type else ""
        if not node.children:
            t = (
                physical_word(node.physical_type, node.type_length)
                if node.physical_type is not None
                else "group"
            )
            out.append(f"{indent}{node.repetition} {t} {node.name}{annotation};\n")
            return
        out.append(f"{indent}{node.repetition} group {node.name}{annotation} {{\n")
        for c in node.children:
            line(c, depth + 1)
        out.append(f"{indent}}}\n")

    for c in root.children:
        line(c, 1)
    out.append("}\n")
    return "".join(out)
