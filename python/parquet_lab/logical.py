"""Logical types: what the bytes of a physical type mean (ch03).

Parquet stores every value as one of eight physical types, which say only how many bytes a value
takes and in what order. A logical type, recorded beside the physical type in the schema, says
how to read those bytes as something a person means: a date, a decimal, a string, an unsigned
integer.

The same four bytes can be three different values::

    e8 4f 00 00   INT32                       20456
                  INT32 + DATE                2026-01-03
                  INT32 + INTEGER(16, false)  20456

This module decodes the logical type from the footer, and applies it to a value's bytes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .encoding import quote, show_float
from .thrift import Node, Struct

TIME_UNITS = {1: "MILLIS", 2: "MICROS", 3: "NANOS"}
PER_SECOND = {"MILLIS": 1_000, "MICROS": 1_000_000, "NANOS": 1_000_000_000}
"""How many of each unit make one second."""

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


def time_of_day(ticks: int, unit: str) -> str:
    """A count of ``unit`` since midnight, as ``HH:MM:SS`` with a fraction when there is one."""
    per = PER_SECOND[unit]
    secs, frac = divmod(ticks, per)
    h, m, sec = secs // 3600, (secs // 60) % 60, secs % 60
    digits = len(str(per)) - 1
    if frac == 0:
        return f"{h:02}:{m:02}:{sec:02}"
    return f"{h:02}:{m:02}:{sec:02}.{frac:0{digits}}"


def timestamp(ticks: int, unit: str, utc: bool) -> str:
    """A timestamp: ``ticks`` of ``unit`` since 1970-01-01T00:00:00.

    ``utc`` is ``isAdjustedToUTC``. True means an instant, shown with a ``Z``. False means a
    wall-clock reading with no zone: the same digits, but no claim about which instant they name.
    """
    days, rest = divmod(ticks, PER_SECOND[unit] * 86_400)
    return f"{date_from_days(days)}T{time_of_day(rest, unit)}{'Z' if utc else ''}"


def decimal(unscaled: int, scale: int) -> str:
    """An unscaled integer and a scale, as a decimal string: ``(12345, 2)`` is ``123.45``."""
    if scale <= 0:
        return str(unscaled * 10**-scale)
    digits = str(abs(unscaled)).rjust(scale + 1, "0")
    return f"{'-' if unscaled < 0 else ''}{digits[:-scale]}.{digits[-scale:]}"


def be_twos_complement(data: bytes) -> int | None:
    """A big-endian two's-complement integer, of any length up to 16 bytes.

    Decimals stored as ``FIXED_LEN_BYTE_ARRAY`` or ``BYTE_ARRAY`` use this, and they are the one
    place Parquet puts the most significant byte first. Everything else is little-endian.
    """
    if not 1 <= len(data) <= 16:
        return None
    # Start from all ones when the top bit says negative, then shift each byte in.
    value = -1 if data[0] & 0x80 else 0
    for b in data:
        value = (value << 8) | b
    return value


def f16_to_float(bits: int) -> float:
    """A half-precision float's bits as a float."""
    sign = -1.0 if bits & 0x8000 else 1.0
    exp, frac = (bits >> 10) & 0x1F, bits & 0x3FF
    if exp == 0:
        return sign * frac * 2.0**-24
    if exp == 31:
        return sign * float("inf") if frac == 0 else float("nan")
    return sign * (1 + frac / 1024) * 2.0 ** (exp - 15)


def interpret(physical: int, logical: LogicalType, data: bytes) -> str | None:
    """One PLAIN-encoded value, read through its logical type. ``None`` when the bytes do not
    fit, or when the logical type adds nothing to the physical reading.

    A PLAIN statistics value has no length prefix, so a ``BYTE_ARRAY`` value here is the bare
    bytes.
    """
    i32 = struct.unpack("<i", data)[0] if len(data) == 4 else None
    i64 = struct.unpack("<q", data)[0] if len(data) == 8 else None
    name = logical.name
    if physical == 1 and name == "DATE":
        return date_from_days(i32) if i32 is not None else None
    if physical in (1, 2) and name == "INTEGER":
        v = i32 if physical == 1 else i64
        if v is None:
            return None
        return str(v if logical.signed else v % (2**32 if physical == 1 else 2**64))
    if physical == 2 and name == "TIMESTAMP" and logical.unit:
        return timestamp(i64, logical.unit, bool(logical.utc)) if i64 is not None else None
    if physical in (1, 2) and name == "TIME" and logical.unit:
        t = i32 if physical == 1 else i64
        return time_of_day(t, logical.unit) if t is not None else None
    if physical in (1, 2) and name == "DECIMAL":
        v = i32 if physical == 1 else i64
        return decimal(v, logical.scale) if v is not None else None
    if physical in (6, 7) and name == "DECIMAL":
        v = be_twos_complement(data)
        return decimal(v, logical.scale) if v is not None else None
    if physical in (6, 7) and name in ("STRING", "ENUM", "JSON"):
        try:
            return quote(data.decode("utf-8"))
        except UnicodeDecodeError:
            return None
    if physical == 7 and name == "FLOAT16" and len(data) == 2:
        return show_float(f16_to_float(int.from_bytes(data, "little")), single=True)
    if physical == 7 and name == "UUID" and len(data) == 16:
        h = data.hex()
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    return None


def int96_timestamp(data: bytes) -> str | None:
    """An ``INT96`` value: eight bytes of nanoseconds within the day, then a four-byte Julian day.

    Deprecated, and still written by some engines. It has no logical type: the convention lives
    outside the specification, which is why it caused so many time-zone bugs.
    """
    if len(data) != 12:
        return None
    nanos, julian = struct.unpack("<qi", data)
    # Julian day 2440588 is 1970-01-01.
    days = julian - 2_440_588
    return timestamp(days * 86_400 * 1_000_000_000 + nanos, "NANOS", False)
