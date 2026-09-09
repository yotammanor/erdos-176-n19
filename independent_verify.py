#!/usr/bin/env python3
"""Independent standard-library verifier for a +/- avoidance witness.

This intentionally does not import ``nk2`` and enumerates progressions in a
different loop order, so it can cross-check the primary verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> tuple[int, ...]:
    text = "\n".join(
        line.partition("#")[0] for line in path.read_text(encoding="utf-8").splitlines()
    )
    symbols = [character for character in text if character in "+-"]
    unexpected = [
        character for character in text if not character.isspace() and character not in "+-"
    ]
    if unexpected:
        raise ValueError(f"unexpected symbols: {sorted(set(unexpected))}")
    return tuple(1 if character == "+" else -1 for character in symbols)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--ell", type=int, default=2)
    args = parser.parse_args()

    coloring = load(args.witness)
    n = len(coloring)
    histogram: dict[int, int] = {}
    checked = 0
    violation: dict[str, object] | None = None

    for start in range(1, n + 1):
        max_difference = (n - start) // (args.k - 1)
        for difference in range(1, max_difference + 1):
            total = 0
            positions: list[int] = []
            for offset in range(args.k):
                position = start + offset * difference
                positions.append(position)
                total += coloring[position - 1]
            checked += 1
            histogram[total] = histogram.get(total, 0) + 1
            if violation is None and abs(total) >= args.ell:
                violation = {
                    "start": start,
                    "difference": difference,
                    "sum": total,
                    "progression": positions,
                }

    result = {
        "witness_sha256": hashlib.sha256(args.witness.read_bytes()).hexdigest(),
        "n": n,
        "k": args.k,
        "ell": args.ell,
        "checked_progressions": checked,
        "sum_histogram": dict(sorted(histogram.items())),
        "avoids": violation is None,
        "first_bad": violation,
    }
    print(json.dumps(result, indent=2))
    return 0 if violation is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
