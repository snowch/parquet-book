"""Statistics: what the footer says about a column chunk's values, and when a reader may believe
it (ch08).

A column chunk's ``Statistics`` hold a minimum and a maximum as bytes. They mean something only
with an order, and the right order depends on the column's type, not on its bytes:

=============================================================  ===========================
Column                                                         Order
=============================================================  ===========================
``INT32``, ``INT64``, and the dates, times and timestamps       signed
``INT32``, ``INT64`` marked as unsigned integers                unsigned
``FLOAT``, ``DOUBLE``, ``FLOAT16``                              signed, by value, no NaN
``DECIMAL`` on bytes                                            signed, big-endian
any other byte array: strings, UUIDs, binary                    unsigned, byte by byte
``INT96``, ``INTERVAL``                                         undefined
=============================================================  ===========================

:class:`Comparator` is that table as code. :func:`bounds` applies the rules for which fields a
reader may use: the newer ``min_value`` and ``max_value`` when the footer says their order, and
the deprecated ``min`` and ``max`` only where signed comparison was the right order anyway.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import Enum, auto

from .logical import be_twos_complement, f16_to_float
from .metadata import Statistics
from .schema import Leaf

SIGNED, UNSIGNED, UNDEFINED = "signed", "unsigned", "undefined"
"""The three sort orders the format distinguishes."""


def _cmp(a, b) -> int:
    return (a > b) - (a < b)


class Comparator(Enum):
    """How to compare two PLAIN-encoded values of one column (without a length prefix)."""

    BOOL = auto()
    I32 = auto()
    U32 = auto()
    I64 = auto()
    U64 = auto()
    F32 = auto()
    F64 = auto()
    F16 = auto()
    BIG_ENDIAN_SIGNED = auto()
    """A decimal stored in bytes: big-endian two's complement."""
    BYTES = auto()
    """Strings and other byte arrays: byte by byte, each byte unsigned, shorter first on a tie."""
    SIGNED_BYTES = auto()
    """Byte by byte with each byte signed, as Java's ``byte`` compares. Never right; it is how
    early writers computed the deprecated ``min`` and ``max`` of strings."""
    FLOAT_BITS = auto()
    """A float's bits compared as a signed integer. Never right either."""
    NONE = auto()

    @property
    def description(self) -> str:
        """What this comparator compares, in words."""
        return _DESCRIPTIONS[self]

    @staticmethod
    def for_leaf(leaf: Leaf, converted: str | None) -> Comparator:
        """The comparator for a leaf column, from its physical type and its annotation."""
        lt = leaf.logical_type
        unsigned = (lt is not None and lt.name == "INTEGER" and lt.signed is False) or converted in (
            "UINT_8",
            "UINT_16",
            "UINT_32",
            "UINT_64",
        )
        decimal = (lt is not None and lt.name == "DECIMAL") or converted == "DECIMAL"
        t = leaf.physical_type
        if t == 0:
            return Comparator.BOOL
        if t == 1:
            return Comparator.U32 if unsigned else Comparator.I32
        if t == 2:
            return Comparator.U64 if unsigned else Comparator.I64
        if t == 4:
            return Comparator.F32
        if t == 5:
            return Comparator.F64
        if t == 7 and lt is not None and lt.name == "FLOAT16":
            return Comparator.F16
        if t == 7 and converted == "INTERVAL":
            return Comparator.NONE
        if t in (6, 7):
            return Comparator.BIG_ENDIAN_SIGNED if decimal else Comparator.BYTES
        return Comparator.NONE  # INT96

    def order(self) -> str:
        if self in (Comparator.U32, Comparator.U64, Comparator.BYTES):
            return UNSIGNED
        return UNDEFINED if self is Comparator.NONE else SIGNED

    def mistake(self) -> tuple[Comparator, str] | None:
        """The mistake a reader is most likely to make with this column, and what it does
        wrong."""
        return _MISTAKES.get(self)

    def compare(self, a: bytes, b: bytes) -> int | None:
        """Compare two values: -1, 0 or 1. ``None`` when either is not a valid value of the type,
        or either is NaN, which has no place in the order."""
        c = Comparator
        if self is c.BOOL:
            return _cmp(a[0], b[0]) if a and b else None
        formats = {c.I32: ("<i", 4), c.U32: ("<I", 4), c.I64: ("<q", 8), c.U64: ("<Q", 8)}
        if self in formats:
            f, n = formats[self]
            return _cmp(struct.unpack(f, a)[0], struct.unpack(f, b)[0]) if len(a) == len(b) == n else None
        if self in (c.F32, c.F64, c.F16):
            x, y = _float(self, a), _float(self, b)
            if x is None or y is None or math.isnan(x) or math.isnan(y):
                return None
            return _cmp(x, y)
        if self is c.BIG_ENDIAN_SIGNED:
            x, y = be_twos_complement(a), be_twos_complement(b)
            return None if x is None or y is None else _cmp(x, y)
        if self is c.BYTES:
            return _cmp(bytes(a), bytes(b))
        if self is c.SIGNED_BYTES:
            return _cmp([x - 256 if x > 127 else x for x in a], [x - 256 if x > 127 else x for x in b])
        if self is c.FLOAT_BITS:
            f = {4: "<i", 8: "<q"}.get(len(a))
            return _cmp(struct.unpack(f, a)[0], struct.unpack(f, b)[0]) if f and len(b) == len(a) else None
        return None

    def min_max(self, values: list[bytes]) -> tuple[bytes, bytes] | None:
        """The smallest and largest of ``values`` in this order, skipping values it cannot place
        (NaN). This is how a writer computes the statistics, so a reader can check them."""
        out = None
        for v in values:
            if self.compare(v, v) is None:
                continue
            if out is None:
                out = (v, v)
            else:
                lo, hi = out
                out = (v if self.compare(v, lo) == -1 else lo, v if self.compare(v, hi) == 1 else hi)
        return out


def _float(c: Comparator, v: bytes) -> float | None:
    if c is Comparator.F32 and len(v) == 4:
        return struct.unpack("<f", v)[0]
    if c is Comparator.F64 and len(v) == 8:
        return struct.unpack("<d", v)[0]
    if c is Comparator.F16 and len(v) == 2:
        return f16_to_float(int.from_bytes(v, "little"))
    return None


_DESCRIPTIONS = {
    Comparator.BOOL: "booleans, false first",
    Comparator.I32: "signed integers",
    Comparator.I64: "signed integers",
    Comparator.U32: "unsigned integers",
    Comparator.U64: "unsigned integers",
    Comparator.F32: "floating-point values, leaving out NaN",
    Comparator.F64: "floating-point values, leaving out NaN",
    Comparator.F16: "floating-point values, leaving out NaN",
    Comparator.BIG_ENDIAN_SIGNED: "signed big-endian integers",
    Comparator.BYTES: "unsigned bytes",
    Comparator.SIGNED_BYTES: "signed bytes",
    Comparator.FLOAT_BITS: "the bits as signed integers",
    Comparator.NONE: "nothing, because the order is undefined",
}

_MISTAKES = {
    Comparator.U32: (Comparator.I32, "reads values of 2^31 and above as negative"),
    Comparator.U64: (Comparator.I64, "reads values of 2^63 and above as negative"),
    Comparator.I32: (Comparator.U32, "reads negative values as large positive ones"),
    Comparator.I64: (Comparator.U64, "reads negative values as large positive ones"),
    Comparator.BYTES: (
        Comparator.SIGNED_BYTES,
        "puts bytes 0x80 and above, every non-ASCII character, before the letter A",
    ),
    Comparator.BIG_ENDIAN_SIGNED: (Comparator.BYTES, "ignores the sign, so negative amounts sort last"),
    Comparator.F32: (Comparator.FLOAT_BITS, "reverses negative numbers and sorts NaN above everything"),
    Comparator.F64: (Comparator.FLOAT_BITS, "reverses negative numbers and sorts NaN above everything"),
}

MIN_MAX_VALUE, DEPRECATED = "min_value and max_value", "min and max (deprecated)"
"""Which pair of fields the bounds came from."""


@dataclass
class Bounds:
    """A minimum and a maximum a reader may compare values against."""

    min: bytes
    max: bytes
    source: str
    min_exact: bool
    """False when the writer shortened the value: the bound holds, but no row has it."""
    max_exact: bool


class Unusable(ValueError):
    """Why a reader may not use a column chunk's statistics."""


def bounds(stats: Statistics, comparator: Comparator, type_order: bool) -> Bounds:
    """The bounds a reader may use, or why it may not use any.

    ``type_order`` is whether the footer's ``column_orders`` gives this column ``TYPE_ORDER``.
    """

    def is_nan(v: bytes) -> bool:
        return comparator.compare(v, v) is None

    if comparator.order() == UNDEFINED:
        raise Unusable("this type has no defined sort order, so its minimum and maximum mean nothing")
    if stats.min_value is not None and stats.max_value is not None:
        if not type_order:
            raise Unusable(
                "the footer has no column_orders, so the order of min_value and max_value is undefined"
            )
        if is_nan(stats.min_value) or is_nan(stats.max_value):
            raise Unusable("a bound is NaN, which writers were never meant to store; ignore both")
        return Bounds(
            stats.min_value,
            stats.max_value,
            MIN_MAX_VALUE,
            stats.is_min_value_exact is not False,
            stats.is_max_value_exact is not False,
        )
    if stats.min is not None and stats.max is not None:
        # The deprecated fields were computed with signed comparison. That is right only for
        # types whose order is signed and that are not compared as bytes.
        byte_array = comparator in (Comparator.BYTES, Comparator.BIG_ENDIAN_SIGNED)
        if comparator.order() != SIGNED or byte_array:
            raise Unusable(
                "only the deprecated min and max are present, and they were computed with signed "
                f"comparison; this column's order is {comparator.description}"
            )
        if is_nan(stats.min) or is_nan(stats.max):
            raise Unusable("a bound is NaN, which writers were never meant to store; ignore both")
        return Bounds(stats.min, stats.max, DEPRECATED, True, True)
    raise Unusable("the footer records no minimum and maximum for this column chunk")
