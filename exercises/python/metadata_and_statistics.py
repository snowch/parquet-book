"""ch08's problems. Edit this file; ``tests/test_metadata_and_statistics.py`` grades it."""

from enum import Enum, auto

from parquet_lab.metadata import Statistics


class Kind(Enum):
    """The kinds of column the problems use, each with its own sort order."""

    INT32 = auto()
    """``INT32``, signed. Little-endian, four bytes."""
    UINT32 = auto()
    """``INT32`` annotated as an unsigned integer. Little-endian, four bytes."""
    INT64 = auto()
    """``INT64``, signed. Little-endian, eight bytes."""
    DOUBLE = auto()
    """``DOUBLE``. Little-endian, eight bytes. NaN has no place in the order."""
    STRING = auto()
    """``BYTE_ARRAY`` holding a string: the bytes, without a length prefix."""
    DECIMAL = auto()
    """A ``DECIMAL`` in a ``FIXED_LEN_BYTE_ARRAY``: big-endian two's complement."""


def compare(kind: Kind, a: bytes, b: bytes) -> int | None:
    """Problem 8.1: compare two values in their column's sort order.

    ``a`` and ``b`` are PLAIN bytes as the footer stores them. Return ``None`` if either is NaN,
    and otherwise -1, 0 or 1 as ``a`` sorts before, with or after ``b``. Do not call
    ``parquet_lab.stats``.
    """
    raise NotImplementedError("problem 8.1")


def usable_bounds(stats: Statistics, kind: Kind, type_order: bool) -> tuple[bytes, bytes] | None:
    """Problem 8.2: the bounds a reader may use.

    Return the minimum and maximum a reader may compare values against, or ``None`` if it may
    use none. Apply the rules from the chapter:

    - ``min_value`` and ``max_value``, when both are present, and only if ``type_order`` is true
      (the footer's ``column_orders`` gives this column ``TYPE_ORDER``);
    - otherwise the deprecated ``min`` and ``max``, and only for ``INT32``, ``INT64`` and
      ``DOUBLE``;
    - never a bound that is NaN.

    You may use your ``compare`` from problem 8.1 to spot NaN.
    """
    raise NotImplementedError("problem 8.2")
