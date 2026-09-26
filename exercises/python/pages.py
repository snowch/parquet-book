"""ch06's problems. Edit this file; ``tests/test_pages.py`` grades it."""


def page_starts(chunk: bytes, base: int) -> list[int]:
    """Problem 6.1: walk a column chunk.

    ``chunk`` is a column chunk's bytes, whose first byte is at file offset ``base``. It is a run
    of pages, each a Thrift ``PageHeader`` followed by ``compressed_page_size`` bytes of body.
    Return the file offset at which every page starts.

    You may decode each header with the book's Thrift decoder::

        from parquet_lab.bytes import ByteReader
        from parquet_lab.thrift import read_struct

    ``read_struct(reader)`` reads one struct and leaves the reader after it; its ``.value`` is a
    struct whose ``.field(3).node.value`` is ``compressed_page_size``.
    """
    raise NotImplementedError("problem 6.1")


def crc_matches(body: bytes, stored: int) -> bool:
    """Problem 6.2: check a page's checksum.

    Compute the CRC-32 (the IEEE polynomial, reflected, as zlib computes it) of ``body``, and say
    whether it equals ``stored``, the signed 32-bit integer from the page header. Write the CRC
    yourself; do not call ``zlib.crc32`` or ``parquet_lab.bytes.crc32``.
    """
    raise NotImplementedError("problem 6.2")
