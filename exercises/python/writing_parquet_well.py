"""ch11's problems. Edit this file; ``tests/test_writing_parquet_well.py`` grades it."""


def row_groups_for(bounds: list[tuple[int, int]], v: int) -> int:
    """Problem 11.1: how many row groups must a lookup read?

    ``bounds`` holds each row group's minimum and maximum of one integer column, from the footer.
    Return how many row groups a reader must read to find ``v``: those whose range includes it.
    """
    raise NotImplementedError("problem 11.1")


def mean_row_groups_per_lookup(values: list[int], row_group_size: int) -> float:
    """Problem 11.2: what does a writer's row order cost lookups?

    ``values`` is one integer column in the order the writer wrote its rows, and every row group
    but the last holds ``row_group_size`` of them. For each distinct value, count the row groups a
    lookup for it must read, using only each row group's minimum and maximum, and return the mean
    over distinct values. Sorted data gives a mean near one; shuffled data, near the number of row
    groups.
    """
    raise NotImplementedError("problem 11.2")
