"""ch10's problems. Edit this file; ``tests/test_how_readers_read.py`` grades it."""


def coalesce(ranges: list[tuple[int, int]], gap: int | None) -> list[tuple[int, int]]:
    """Problem 10.1: merge byte ranges into requests.

    ``ranges`` are half-open ``(start, end)`` byte ranges, in any order, possibly overlapping.
    Return the requests a reader should make, sorted: overlapping ranges always merge, and with a
    ``gap``, ranges separated by ``gap`` bytes or fewer merge too, so a gap of zero merges ranges
    that touch. ``None`` merges only what overlaps.
    """
    raise NotImplementedError("problem 10.1")


def finish_time(phases: list[list[int]], connections: int) -> int:
    """Problem 10.2: how long do requests take on several connections?

    ``phases`` lists, phase by phase, how long each request takes, in the order the reader issues
    them. Every request in a phase may start once the whole previous phase has finished. Each goes
    on the connection that is free soonest (the lowest-numbered, on a tie), and starts when that
    connection is free. Return when the last request finishes, with time starting at zero.
    """
    raise NotImplementedError("problem 10.2")
