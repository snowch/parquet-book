"""The fixed parts of a Parquet file: the magic bytes at each end, and the trailer.

::

    offset 0                                                         file_size
    │                                                                        │
    ▼                                                                        ▼
    ┌──────┬─────────────────────────┬──────────────────┬────────────┬──────┐
    │ PAR1 │ row groups (the data)   │ footer           │ footer len │ PAR1 │
    │  4   │ …                       │ FileMetaData     │ u32 LE, 4  │  4   │
    └──────┴─────────────────────────┴──────────────────┴────────────┴──────┘
                                                        └──── trailer: 8 ────┘

A reader starts at the *end*. Nothing at the front of the file says where anything is: the
writer did not know the offsets of its row groups until it had written them, so it wrote the map
last. The last eight bytes are the only part of the file whose position is known before reading
anything, and they say how to find the map.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import Span, le_terms, read_le_u32

MAGIC = b"PAR1"
"""The four ASCII bytes that open and close every unencrypted Parquet file."""

MAGIC_ENCRYPTED_FOOTER = b"PARE"
"""The closing magic of a file whose footer is encrypted (ch13)."""

TRAILER_LEN = 8
"""The trailer: a four-byte footer length followed by the four-byte magic."""

MIN_FILE_LEN = len(MAGIC) + TRAILER_LEN
"""The smallest file that can be valid: opening magic plus trailer, with an empty footer."""


class FormatError(ValueError):
    """Why a file could not be located, before any metadata was parsed."""


class TooShort(FormatError):
    def __init__(self, file_size: int) -> None:
        super().__init__(
            f"a {file_size}-byte file cannot be Parquet: the magic and trailer alone take {MIN_FILE_LEN}"
        )


class BadMagic(FormatError):
    def __init__(self, found: bytes, span: Span) -> None:
        super().__init__(f"expected PAR1 at {span}, found {' '.join(f'{b:02x}' for b in found)}")


class EncryptedFooter(FormatError):
    def __init__(self) -> None:
        super().__init__(
            "this file ends in PARE: its footer is encrypted, and without the footer key a "
            "reader can see only its crypto metadata (ch13)"
        )


class FooterLengthTooLarge(FormatError):
    def __init__(self, footer_length: int, available: int) -> None:
        super().__init__(
            f"the trailer claims a {footer_length}-byte footer, but only {available} bytes lie "
            "between the opening magic and the trailer"
        )


@dataclass(frozen=True)
class Trailer:
    """The last eight bytes of a file, decoded."""

    data: bytes
    """The eight raw bytes, as read."""
    span: Span
    """Where they sit in the file: always the last eight bytes."""
    footer_length: int
    """The first four bytes, read as a little-endian ``u32``."""
    magic: bytes
    """The last four bytes."""

    def length_span(self) -> Span:
        """The span of the footer-length field alone."""
        return Span(self.span.start, self.span.start + 4)

    def magic_span(self) -> Span:
        """The span of the closing magic alone."""
        return Span(self.span.start + 4, self.span.end)

    def length_terms(self) -> list[tuple[int, int]]:
        """The footer-length bytes with the weight of each, for showing the arithmetic."""
        return le_terms(self.data[:4])


def parse_trailer(last8: bytes, file_size: int) -> Trailer:
    """Decode the trailer of a file of ``file_size`` bytes from its last eight bytes."""
    if file_size < MIN_FILE_LEN:
        raise TooShort(file_size)
    span = Span(file_size - TRAILER_LEN, file_size)
    magic = last8[4:8]
    if magic == MAGIC_ENCRYPTED_FOOTER:
        raise EncryptedFooter()
    if magic != MAGIC:
        raise BadMagic(magic, Span(span.start + 4, span.end))
    footer_length = read_le_u32(last8[0:4])
    return Trailer(last8, span, footer_length, magic)


def footer_span(file_size: int, footer_length: int) -> Span:
    """Where the footer is: the ``footer_length`` bytes that end where the trailer begins.

    ::

        footer_start = file_size - 8 - footer_length
        footer_end   = file_size - 8

    The footer cannot overlap the opening magic, so a length that would put its start before
    byte 4 means the trailer is lying, and the reader stops rather than trusting it.
    """
    if file_size < MIN_FILE_LEN:
        raise TooShort(file_size)
    footer_end = file_size - TRAILER_LEN
    available = footer_end - len(MAGIC)
    if footer_length > available:
        raise FooterLengthTooLarge(footer_length, available)
    return Span(footer_end - footer_length, footer_end)


def check_header(first4: bytes) -> Span:
    """Check the opening magic: the first four bytes of the file."""
    span = Span(0, len(MAGIC))
    if first4 != MAGIC:
        raise BadMagic(first4, span)
    return span
