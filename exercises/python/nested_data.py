"""ch04's problems. Edit this file; ``tests/test_nested_data.py`` grades it."""


def decode_hybrid(data: bytes, bit_width: int, count: int) -> list[int]:
    """Problem 4.1: the RLE / bit-packing hybrid.

    Decode ``count`` values of ``bit_width`` bits each from ``data``. The stream is a sequence of
    runs, each starting with a ULEB128 header:

    - if the header's lowest bit is 0, it is an RLE run: ``header >> 1`` copies of one value,
      which follows in ``ceil(bit_width / 8)`` bytes, little-endian;
    - if it is 1, it is a bit-packed run: ``header >> 1`` groups of eight values, each packed
      into ``bit_width`` bits, least significant bit first.

    Stop when you have ``count`` values: the last bit-packed group may be padded past it.
    """
    raise NotImplementedError("problem 4.1")


def list_from_levels(
    rep: list[int], definition: list[int], values: list[str]
) -> list[list[str | None] | None]:
    """Problem 4.2: rebuild a list column from its levels.

    The column is a standard list of optional strings::

        optional group tags (LIST) {
          repeated group list {
            optional binary element (STRING);
          }
        }

    Its maximum definition level is 3 and its maximum repetition level 1. ``rep`` and
    ``definition`` hold one level each per value slot; ``values`` holds only the values that are
    present, in order. Return one entry per record: ``None`` for a null list, ``[]`` for an empty
    one, and the list of elements otherwise, with ``None`` for a null element.
    """
    raise NotImplementedError("problem 4.2")
