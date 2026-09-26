"""ch03's problems. Edit this file; ``tests/test_the_type_system.py`` grades it."""


def leaf_paths(elements: list[tuple[str, int]]) -> list[str]:
    """Problem 3.1: rebuild the tree, and name its leaves.

    ``elements`` is a schema as the footer stores it: each element's name and number of
    children, in depth-first order, starting with the root. Return the path of every leaf, in
    order, as the names from the root's child down to the leaf joined with dots
    (``shipping.city``). The root's own name is not part of any path. A leaf is an element with
    no children.

    The test runs your function on the fixtures and on hundreds of generated schemas.
    """
    raise NotImplementedError("problem 3.1")


def max_levels(path: list[str]) -> tuple[int, int]:
    """Problem 3.2: the maximum levels of a leaf.

    ``path`` is the repetition of every field from the root's child down to the leaf, each
    ``"required"``, ``"optional"`` or ``"repeated"``. Return
    ``(max_definition_level, max_repetition_level)``.
    """
    raise NotImplementedError("problem 3.2")


def decimal_from_bytes(data: bytes, scale: int) -> str:
    """Problem 3.3: a decimal stored as bytes.

    A ``DECIMAL`` stored in a ``FIXED_LEN_BYTE_ARRAY`` is an unscaled integer in big-endian
    two's-complement form: most significant byte first, and negative when the first byte's top
    bit is set. The value is that integer divided by ten to the power ``scale``.

    Return the value as a string with exactly ``scale`` digits after the point (``"5.00"``,
    ``"-0.05"``). ``data`` is between one and sixteen bytes long; ``scale`` is at least one. Do not
    use ``int.from_bytes``: shift the bytes in yourself, so you can say where the sign comes from.
    """
    raise NotImplementedError("problem 3.3")
