"""Logical types: what the bytes of a physical type mean (ch03).

Parquet stores every value as one of eight physical types, which say only how many bytes a value
takes and in what order. A logical type, recorded beside the physical type in the schema, says
how to read those bytes as something a person means: a date, a decimal, a string, an unsigned
integer.

The same four bytes can be three different values::

    e8 4f 00 00   INT32                       20456
                  INT32 + DATE                2026-01-03
                  INT32 + INTEGER(16, false)  20456

This module decodes the logical type from the footer. Applying it to a value's bytes arrives
with ch03.
"""

from __future__ import annotations

from dataclasses import dataclass

from .thrift import Node, Struct

TIME_UNITS = {1: "MILLIS", 2: "MICROS", 3: "NANOS"}

_SIMPLE = {
    1: "STRING",
    2: "MAP",
    3: "LIST",
    4: "ENUM",
    6: "DATE",
    11: "UNKNOWN",
    12: "JSON",
    13: "BSON",
    14: "UUID",
    15: "FLOAT16",
    16: "VARIANT",
    17: "GEOMETRY",
    18: "GEOGRAPHY",
}


@dataclass(frozen=True)
class LogicalType:
    """The ``LogicalType`` union from ``parquet.thrift``, with its parameters.

    ``name`` is the member's name, such as ``"DECIMAL"``. The other fields are set only for the
    members that have them. A member this reader does not know is ``"OTHER"``, with its field id.
    """

    name: str
    scale: int | None = None
    precision: int | None = None
    utc: bool | None = None
    unit: str | None = None
    bit_width: int | None = None
    signed: bool | None = None
    field_id: int | None = None

    def __str__(self) -> str:
        where = "UTC" if self.utc else "local"
        if self.name == "DECIMAL":
            return f"DECIMAL({self.precision}, {self.scale})"
        if self.name in ("TIME", "TIMESTAMP"):
            return f"{self.name}({self.unit or '?'}, {where})"
        if self.name == "INTEGER":
            return f"INTEGER({self.bit_width}, {'signed' if self.signed else 'unsigned'})"
        if self.name == "OTHER":
            return f"logical type {self.field_id}"
        return self.name


def _int(s: Struct | None, id: int) -> int | None:
    f = s.field(id) if s else None
    return f.node.value if f and type(f.node.value) is int else None


def _bool(s: Struct | None, id: int) -> bool | None:
    f = s.field(id) if s else None
    return f.node.value if f and type(f.node.value) is bool else None


def _time_unit(s: Struct | None) -> str | None:
    f = s.field(2) if s else None
    if f is None or not isinstance(f.node.value, Struct) or not f.node.value.fields:
        return None
    return TIME_UNITS.get(f.node.value.fields[0].id)


def decode(node: Node) -> LogicalType | None:
    """Decode a ``LogicalType`` union: exactly one field is set, and its id says which type it
    is."""
    if not isinstance(node.value, Struct) or not node.value.fields:
        return None
    member = node.value.fields[0]
    inner = member.node.value if isinstance(member.node.value, Struct) else None
    if member.id in _SIMPLE:
        return LogicalType(_SIMPLE[member.id])
    if member.id == 5:
        return LogicalType("DECIMAL", scale=_int(inner, 1) or 0, precision=_int(inner, 2) or 0)
    if member.id in (7, 8):
        name = "TIME" if member.id == 7 else "TIMESTAMP"
        return LogicalType(name, utc=bool(_bool(inner, 1)), unit=_time_unit(inner))
    if member.id == 10:
        signed = _bool(inner, 2)
        return LogicalType(
            "INTEGER", bit_width=_int(inner, 1) or 0, signed=True if signed is None else signed
        )
    return LogicalType("OTHER", field_id=member.id)


def date_from_days(days: int) -> str:
    """The date ``days`` after 1970-01-01, as ``YYYY-MM-DD``.

    Howard Hinnant's ``civil_from_days``: shift the epoch to 0000-03-01 so leap days fall at the
    end of a year, split into 400-year eras, and read off year, month and day.
    """
    z = days + 719_468
    era = z // 146_097
    doe = z - era * 146_097
    yoe = (doe - doe // 1460 + doe // 36_524 - doe // 146_096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y = yoe + era * 400 + (1 if m <= 2 else 0)
    return f"{y:04}-{m:02}-{d:02}"
