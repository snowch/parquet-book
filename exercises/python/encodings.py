"""ch05's problems. Edit this file; ``tests/test_encodings.py`` grades it."""


def decode_delta_binary_packed(data: bytes) -> list[int]:
    """Problem 5.1: DELTA_BINARY_PACKED.

    Decode every integer in ``data``. The layout, all integers ULEB128 unless noted::

        header:  block size, miniblocks per block, value count, first value (zigzag)
        block:   min delta (zigzag), one bit-width byte per miniblock, then the miniblocks

    Each miniblock holds ``block size / miniblocks per block`` deltas, each packed into its bit
    width, least significant bit first, and each to be added to the block's min delta. A value is
    the previous value plus its delta. Stop at the value count: a miniblock that is not needed has
    a width byte and no bytes of its own. The arithmetic wraps at 64 bits, as a writer's does.
    """
    raise NotImplementedError("problem 5.1")


def apply_prefixes(prefix_lengths: list[int], suffixes: list[bytes]) -> list[bytes]:
    """Problem 5.2: DELTA_BYTE_ARRAY's last step.

    Each value shares its first ``prefix_lengths[i]`` bytes with the value before it, and stores
    only the rest in ``suffixes[i]``. The first value's prefix length is zero. Rebuild the values.
    """
    raise NotImplementedError("problem 5.2")


def dictionary_values(page: bytes, count: int, dictionary: list[str]) -> list[str]:
    """Problem 5.3: dictionary indices.

    ``page`` is the values section of a dictionary-encoded data page: one byte giving the bit
    width of the indices, then ``count`` indices as an RLE / bit-packing hybrid, with no length
    prefix. Return the dictionary entry each index names.

    You wrote the hybrid decoder in problem 4.1, and you may call it:
    ``from nested_data import decode_hybrid``.
    """
    raise NotImplementedError("problem 5.3")
