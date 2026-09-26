"""What the graders share: the fixtures, and a small deterministic generator."""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def fixtures():
    """The fixtures, each with what pyarrow said about it when it wrote it. ch13's encrypted
    fixtures need keys for most of what the problems read, so they are left out."""
    out = []
    for path in sorted(FIXTURES.glob("*.parquet")):
        manifest = json.loads(path.with_suffix(".json").read_text())
        if "encryption" not in manifest["generator"]:
            out.append((path.name, path.read_bytes(), manifest))
    assert out
    return out


class Rng:
    """xorshift: the tests need no dependencies, and every run is the same."""

    def __init__(self, seed: int) -> None:
        self.state = seed

    def next(self, n: int) -> int:
        x = self.state
        x ^= (x << 13) & 0xFFFF_FFFF_FFFF_FFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFF_FFFF_FFFF_FFFF
        self.state = x
        return x % n
