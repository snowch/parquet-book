"""ch09's problems. Edit this file; ``tests/test_skipping_data.py`` grades it."""

from enum import Enum, auto


class Cmp(Enum):
    """The comparisons problem 9.1 handles."""

    EQ = auto()
    LT = auto()
    GT = auto()
    IS_NULL = auto()


def can_skip(cmp: Cmp, value: int, bounds: tuple[int, int] | None, null_count: int, num_values: int) -> bool:
    """Problem 9.1: may a reader skip a page or a column chunk?

    The condition is ``column cmp value`` on an ``INT64`` column. From metadata, the reader knows
    the smallest and largest non-null values (``bounds``, ``None`` when every value is null or
    none are recorded), how many values are null (``null_count``), and how many values there are
    in all (``num_values``). Return ``True`` only if no row can satisfy the condition. Null
    satisfies no comparison except ``IS_NULL``.
    """
    raise NotImplementedError("problem 9.1")


SALT = [0x47B6137B, 0x44974D91, 0x8824AD5B, 0xA2B7289D, 0x705495C7, 0x2DF1424B, 0x9EFC4947, 0x5C6BFB31]


def may_contain(bitset: bytes, hash: int) -> bool:
    """Problem 9.2: probe a split block Bloom filter.

    ``bitset`` is the filter's bitset: blocks of 32 bytes, each eight little-endian 32-bit words.
    ``hash`` is the xxHash64 of the value, an unsigned 64-bit integer. The block is
    ``((hash >> 32) * number_of_blocks) >> 32``. For each word ``i``, the bit to test is the top
    five bits of ``(hash & 0xFFFFFFFF) * SALT[i]``, kept to 32 bits (``& 0xFFFFFFFF``). Return
    ``False`` if any tested bit is clear.
    """
    raise NotImplementedError("problem 9.2")
