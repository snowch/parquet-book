"""ch13's problems. Edit this file; ``tests/test_modular_encryption.py`` grades it."""

from enum import Enum, auto


def modules(chunk: bytes) -> list[tuple[int, int]]:
    """Problem 13.1: find the modules of an encrypted column chunk.

    ``chunk`` is an encrypted column chunk's bytes. It is a run of modules, each a four-byte
    little-endian length followed by that many bytes (a 12-byte nonce, the ciphertext, a 16-byte
    tag). Return each module's ``(offset, size)`` within ``chunk``, where ``size`` counts the
    length prefix too.
    """
    raise NotImplementedError("problem 13.1")


class FooterMode(Enum):
    """How a file's footer is protected."""

    NOT_ENCRYPTED = auto()
    """No modular encryption."""
    PLAINTEXT_FOOTER = auto()
    """Encrypted columns, and a readable footer signed with the footer key."""
    ENCRYPTED_FOOTER = auto()
    """The footer itself is encrypted."""


def footer_mode(file: bytes) -> FooterMode:
    """Problem 13.2: which footer mode does a file use?

    Decide from the file's bytes. You may use the book's reader:
    ``parquet_lab.report.open_bytes(file)`` decodes a readable footer, and its
    ``encryption_algorithm`` is set when the file uses modular encryption.
    """
    raise NotImplementedError("problem 13.2")
