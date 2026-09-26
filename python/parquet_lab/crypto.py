"""Modular encryption: what a reader without keys can still see (ch13).

Parquet encrypts a file in **modules**: the footer, and for each encrypted column every page
header and every page, separately. Each module is written the same way::

    [length: u32, little-endian]   the bytes that follow
    [nonce: 12 bytes]              never reused under one key
    [ciphertext]                   the module, encrypted with AES
    [tag: 16 bytes]                AES-GCM's check that nothing was changed

This module reads everything that is not encrypted, and describes the modules that are. It does
not decrypt: that needs AES and the keys, and ch13 is about what remains without them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span
from .format import footer_span
from .metadata import as_struct, union_member
from .thrift import Node, read_struct

MAGIC_ENCRYPTED = b"PARE"
"""The magic an encrypted-footer file starts and ends with."""
NONCE_LEN = 12
TAG_LEN = 16


class CryptoError(ValueError):
    pass


@dataclass(frozen=True)
class Module:
    """One encrypted module, split into its parts."""

    span: Span
    length: Span
    nonce: Span
    ciphertext: Span
    tag: Span


def read_module(r: ByteReader) -> Module:
    """Read the module that starts at ``r``, from its length prefix alone."""
    start = r.offset()
    n = r.read_le_u32()
    if n < NONCE_LEN + TAG_LEN:
        raise CryptoError(f"a module at offset {start} claims {n} bytes, fewer than a nonce and a tag")
    _, body = r.read_bytes(n)
    return Module(
        span=Span(start, body.end),
        length=Span(start, start + 4),
        nonce=Span(body.start, body.start + NONCE_LEN),
        ciphertext=Span(body.start + NONCE_LEN, body.end - TAG_LEN),
        tag=Span(body.end - TAG_LEN, body.end),
    )


def chunk_modules(file: bytes, chunk: Span) -> list[Module]:
    """The modules of an encrypted column chunk: page headers and pages, alternating."""
    if chunk.end > len(file):
        raise CryptoError(f"column chunk {chunk} is past the end of the file")
    r = ByteReader(file[chunk.start : chunk.end], chunk.start)
    out = []
    while not r.is_at_end():
        out.append(read_module(r))
    return out


@dataclass
class EncryptedFooter:
    """What an encrypted-footer file shows: its crypto metadata, and one module where the
    ``FileMetaData`` should be."""

    footer: Span
    crypto_metadata: Node
    algorithm: str
    key_metadata: bytes | None
    module: Module


def encrypted_footer(file: bytes) -> EncryptedFooter:
    """Read an encrypted-footer file's footer, as far as anyone without the footer key can."""
    size = len(file)
    if size < 12 or file[:4] != MAGIC_ENCRYPTED or file[-4:] != MAGIC_ENCRYPTED:
        raise CryptoError("not an encrypted-footer file: it does not start and end with PARE")
    length = int.from_bytes(file[-8:-4], "little")
    footer = footer_span(size, length)
    r = ByteReader(file[footer.start : footer.end], footer.start)
    try:
        crypto_metadata = read_struct(r)
    except ValueError as e:
        raise CryptoError(f"FileCryptoMetaData: {e}") from e
    s = as_struct(crypto_metadata)
    algorithm = union_member(s.field(1).node) if s.field(1) else "UNKNOWN"
    key = s.field(2)
    key_metadata = key.node.value if key and isinstance(key.node.value, bytes) else None
    module = read_module(r)
    if not r.is_at_end():
        raise CryptoError(
            f"{footer.end - r.offset()} bytes follow the encrypted FileMetaData inside the footer"
        )
    return EncryptedFooter(footer, crypto_metadata, algorithm, key_metadata, module)
