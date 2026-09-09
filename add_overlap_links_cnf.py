#!/usr/bin/env python3
"""Append exact overlap identities to a threshold-counter DIMACS instance."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterator, Sequence

import nk2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def read_header(path: Path) -> tuple[int, int]:
    with path.open("r", encoding="ascii") as stream:
        for line in stream:
            if line.startswith("p cnf "):
                fields = line.split()
                if len(fields) != 4:
                    break
                return int(fields[2]), int(fields[3])
    raise ValueError(f"invalid or missing DIMACS header in {path}")


def states_per_progression(k: int, ell: int) -> int:
    upper_threshold = nk2.threshold(k, ell)
    return sum(min(index, upper_threshold) for index in range(1, k + 1))


def sign_variable(n: int, k: int, ell: int, progression_index: int) -> int:
    """Return the state meaning that an odd AP has the larger allowed sum."""
    if ell != 2 or k % 2 == 0:
        raise ValueError("overlap links require odd k and ell=2")
    upper_threshold = nk2.threshold(k, ell)
    sign_threshold = (k + 1) // 2
    states_before_last_row = sum(
        min(index, upper_threshold) for index in range(1, k)
    )
    offset_in_progression = states_before_last_row + sign_threshold - 1
    return (
        n
        + 1
        + progression_index * states_per_progression(k, ell)
        + offset_in_progression
    )


def relation_clauses(variables: Sequence[int]) -> Iterator[tuple[int, ...]]:
    """Encode y1 - y2 - first + last = 0 by excluding invalid rows."""
    if len(variables) != 4 or len(set(variables)) != 4:
        raise ValueError("relation requires four distinct variables")
    for bits in itertools.product((0, 1), repeat=4):
        y1, y2, first, last = bits
        if y1 - y2 - first + last == 0:
            continue
        yield tuple(
            -variable if bit else variable
            for variable, bit in zip(variables, bits)
        )


def overlap_clauses(n: int, k: int, ell: int) -> Iterator[tuple[int, ...]]:
    progressions = list(nk2.iter_aps(n, k))
    progression_index = {
        (progression[0], progression[1] - progression[0]): index
        for index, progression in enumerate(progressions)
    }
    max_difference = (n - 1) // (k - 1) if n else 0
    for difference in range(1, max_difference + 1):
        last_start = n - (k - 1) * difference
        for start in range(1, last_start - difference + 1):
            variables = (
                sign_variable(
                    n,
                    k,
                    ell,
                    progression_index[(start, difference)],
                ),
                sign_variable(
                    n,
                    k,
                    ell,
                    progression_index[(start + difference, difference)],
                ),
                start,
                start + k * difference,
            )
            yield from relation_clauses(variables)


def augment(base: Path, output: Path, n: int, k: int, ell: int) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    added = list(overlap_clauses(n, k, ell))
    declared_variables, declared_clauses = read_header(base)
    observed_clauses = 0
    found_header = False
    output.parent.mkdir(parents=True, exist_ok=True)
    with base.open("r", encoding="ascii") as source, output.open(
        "w", encoding="ascii", newline="\n"
    ) as target:
        for line in source:
            if line.startswith("p cnf "):
                if found_header:
                    raise ValueError("multiple DIMACS headers")
                target.write(
                    f"p cnf {declared_variables} {declared_clauses + len(added)}\n"
                )
                found_header = True
            else:
                target.write(line)
                stripped = line.strip()
                if stripped and not stripped.startswith("c"):
                    observed_clauses += 1
        if not found_header:
            raise ValueError("missing DIMACS header")
        if observed_clauses != declared_clauses:
            raise ValueError(
                f"header declares {declared_clauses} clauses, "
                f"observed {observed_clauses}"
            )
        for clause in added:
            target.write(" ".join(map(str, clause)) + " 0\n")

    return {
        "schema": "erdos176.overlap-linked-cnf.v1",
        "path": str(output.resolve()),
        "base": str(base.resolve()),
        "base_sha256": sha256(base),
        "sha256": sha256(output),
        "n": n,
        "k": k,
        "ell": ell,
        "variables": declared_variables,
        "base_clauses": declared_clauses,
        "overlap_clauses": len(added),
        "clauses": declared_clauses + len(added),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--ell", type=int, default=2)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = augment(args.base, args.output, args.n, args.k, args.ell)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        if args.report.exists():
            raise FileExistsError(f"refusing to overwrite {args.report}")
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
