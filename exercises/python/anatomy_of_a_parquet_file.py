"""ch02's problems. Edit this file; ``tests/test_anatomy_of_a_parquet_file.py`` grades it."""


def footer_length(trailer: bytes) -> int:
    """Problem 2.1: the footer length.

    ``trailer`` is the last eight bytes of a Parquet file. Return the footer length they encode.

    The first four bytes are an unsigned 32-bit integer, least significant byte first. Do not use
    ``int.from_bytes`` or ``struct``: write the arithmetic, one byte and one power of 256 at a
    time, so that you can say what each byte contributes.
    """
    raise NotImplementedError("problem 2.1")


def footer_range(file_size: int, footer_length: int) -> tuple[int, int] | None:
    """Problem 2.2: where the footer is.

    Given the file size and the footer length from its trailer, return the footer's byte range
    as ``(start, end)``, with ``end`` excluded. Return ``None`` when no valid file could have this
    size and footer length: when the footer would overlap the four-byte opening magic, or when the
    file is too small to hold the magic and the trailer at all.
    """
    raise NotImplementedError("problem 2.2")


def gets_to_open(footer_length: int, prefetch: int) -> int:
    """Problem 2.3: how many ``GET`` requests it takes to open a file.

    A reader already knows the file size (from a directory listing). It reads the last
    ``prefetch`` bytes of the file in one ``GET``, never fewer than the eight-byte trailer, and
    fetches whatever part of the footer that did not cover in a second ``GET``.

    Return how many ``GET`` requests it makes to have the whole footer. The test runs the book's
    reader against a traced object store for many values of ``prefetch`` and counts.
    """
    raise NotImplementedError("problem 2.3")
