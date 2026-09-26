"""ch12's problems. Edit this file; ``tests/test_a_tiny_query_engine.py`` grades it."""


def sum_by_key(keys: list[str], values: list[int]) -> list[tuple[str, int]]:
    """Problem 12.1: a hash aggregate.

    ``keys[i]`` is row ``i``'s group and ``values[i]`` its value. Return each group with the sum
    of its values, sorted by group, comparing groups as UTF-8 bytes. This is ``SELECT key,
    sum(value) ... GROUP BY key ORDER BY key``.
    """
    raise NotImplementedError("problem 12.1")


def top_n(rows: list[tuple[int, int]], n: int) -> list[tuple[int, int]]:
    """Problem 12.2: the top ``n``.

    ``rows`` are ``(order_id, amount)`` pairs. Return the ``n`` with the largest amounts, largest
    first, breaking ties by the smaller ``order_id`` first. This is ``ORDER BY amount DESC,
    order_id LIMIT n``. Sorting everything works; keeping only the best ``n`` as you go uses less
    memory.
    """
    raise NotImplementedError("problem 12.2")
