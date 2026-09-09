#!/usr/bin/env python3
"""Independently audit the deterministic threshold-counter DIMACS encoding."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterator, Sequence, TextIO


Clause = tuple[int, ...]


def clause_satisfied(clause: Sequence[int], values: dict[int, bool]) -> bool:
    return any(values[abs(literal)] == (literal > 0) for literal in clause)


def audit_local_gadgets() -> None:
    """Exhaustively establish the Boolean meaning of every counter gadget."""
    gadgets = (
        ((-4, 3), (4, -3)),
        ((-1, 4), (-3, 4), (-4, 1, 3)),
        ((-4, 2), (-4, 3), (4, -2, -3)),
        (
            (-1, 4),
            (-2, -3, 4),
            (-4, 1, 2),
            (-4, 1, 3),
        ),
    )
    meanings = (
        lambda a, b, x: x,
        lambda a, b, x: a or x,
        lambda a, b, x: b and x,
        lambda a, b, x: a or (b and x),
    )
    for clauses, meaning in zip(gadgets, meanings):
        for a, b, x, current in itertools.product((False, True), repeat=4):
            values = {1: a, 2: b, 3: x, 4: current}
            observed = all(clause_satisfied(clause, values) for clause in clauses)
            expected = current == meaning(a, b, x)
            if observed != expected:
                raise AssertionError(
                    f"counter gadget truth-table failure: {clauses}, {values}"
                )


def overlap_relation_clauses(variables: Sequence[int]) -> Iterator[Clause]:
    """Independently encode y1 - y2 - first + last = 0."""
    for bits in itertools.product((False, True), repeat=4):
        y1, y2, first, last = bits
        if int(y1) - int(y2) - int(first) + int(last) == 0:
            continue
        yield tuple(
            -variable if bit else variable
            for variable, bit in zip(variables, bits)
        )


def audit_overlap_relation() -> None:
    variables = (1, 2, 3, 4)
    clauses = tuple(overlap_relation_clauses(variables))
    if len(clauses) != 10:
        raise AssertionError("overlap relation should exclude ten truth-table rows")
    for bits in itertools.product((False, True), repeat=4):
        values = dict(zip(variables, bits))
        observed = all(clause_satisfied(clause, values) for clause in clauses)
        y1, y2, first, last = bits
        expected = int(y1) - int(y2) - int(first) + int(last) == 0
        if observed != expected:
            raise AssertionError(
                f"overlap truth-table failure: {bits}, observed={observed}"
            )


def arithmetic_progressions(n: int, k: int) -> Iterator[tuple[int, ...]]:
    difference = 1
    while 1 + (k - 1) * difference <= n:
        last_start = n - (k - 1) * difference
        start = 1
        while start <= last_start:
            yield tuple(start + offset * difference for offset in range(k))
            start += 1
        difference += 1


def expected_clauses(
    n: int,
    k: int,
    ell: int,
    fix_first: bool,
    overlap_links: bool = False,
) -> Iterator[Clause]:
    upper_forbidden = (k + ell + 1) // 2
    lower_required = k - upper_forbidden + 1
    next_variable = n
    state_variables: dict[tuple[int, int], int] = {}
    for progression in arithmetic_progressions(n, k):
        states: dict[tuple[int, int], int] = {}
        for prefix_length, literal in enumerate(progression, start=1):
            maximum_threshold = min(prefix_length, upper_forbidden)
            for count in range(1, maximum_threshold + 1):
                next_variable += 1
                current = next_variable
                states[prefix_length, count] = current
                previous_same = states.get((prefix_length - 1, count))
                if count == 1:
                    if previous_same is None:
                        yield (-current, literal)
                        yield (current, -literal)
                    else:
                        yield (-previous_same, current)
                        yield (-literal, current)
                        yield (-current, previous_same, literal)
                    continue
                previous_lower = states[prefix_length - 1, count - 1]
                if previous_same is None:
                    yield (-current, previous_lower)
                    yield (-current, literal)
                    yield (current, -previous_lower, -literal)
                else:
                    yield (-previous_same, current)
                    yield (-previous_lower, -literal, current)
                    yield (-current, previous_same, previous_lower)
                    yield (-current, previous_same, literal)
        yield (states[k, lower_required],)
        yield (-states[k, upper_forbidden],)
        if overlap_links:
            if ell != 2 or k % 2 == 0:
                raise ValueError("overlap links require odd k and ell=2")
            difference = progression[1] - progression[0]
            state_variables[(progression[0], difference)] = states[
                k, (k + 1) // 2
            ]
    if fix_first and n:
        yield (1,)
    if overlap_links:
        maximum_difference = (n - 1) // (k - 1) if n else 0
        for difference in range(1, maximum_difference + 1):
            last_start = n - (k - 1) * difference
            for start in range(1, last_start - difference + 1):
                variables = (
                    state_variables[(start, difference)],
                    state_variables[(start + difference, difference)],
                    start,
                    start + k * difference,
                )
                yield from overlap_relation_clauses(variables)


def data_lines(stream: TextIO) -> Iterator[str]:
    for raw_line in stream:
        line = raw_line.strip()
        if line and not line.startswith("c"):
            yield line


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def audit(
    path: Path,
    *,
    n: int,
    k: int,
    ell: int,
    fix_first: bool,
    overlap_links: bool = False,
) -> dict[str, object]:
    audit_local_gadgets()
    if overlap_links:
        audit_overlap_relation()
    with path.open("r", encoding="ascii") as stream:
        lines = data_lines(stream)
        try:
            header = next(lines)
        except StopIteration as error:
            raise ValueError("empty DIMACS file") from error
        fields = header.split()
        if len(fields) != 4 or fields[:2] != ["p", "cnf"]:
            raise ValueError(f"invalid DIMACS header: {header!r}")
        declared_variables = int(fields[2])
        declared_clauses = int(fields[3])

        count = 0
        maximum_variable = 0
        for count, expected in enumerate(
            expected_clauses(n, k, ell, fix_first, overlap_links),
            start=1,
        ):
            try:
                line = next(lines)
            except StopIteration as error:
                raise ValueError(
                    f"DIMACS ended before expected clause {count}"
                ) from error
            tokens = [int(token) for token in line.split()]
            if not tokens or tokens[-1] != 0 or 0 in tokens[:-1]:
                raise ValueError(f"invalid clause terminator at clause {count}")
            actual = tuple(tokens[:-1])
            if actual != expected:
                raise ValueError(
                    f"clause {count} differs: expected {expected}, got {actual}"
                )
            maximum_variable = max(
                maximum_variable,
                *(abs(literal) for literal in expected),
            )
        try:
            extra = next(lines)
        except StopIteration:
            extra = None
        if extra is not None:
            raise ValueError(f"unexpected clause after clause {count}: {extra!r}")

    if declared_clauses != count:
        raise ValueError(
            f"header declares {declared_clauses} clauses, audited {count}"
        )
    if declared_variables != maximum_variable:
        raise ValueError(
            f"header declares {declared_variables} variables, "
            f"audited {maximum_variable}"
        )
    report: dict[str, object] = {
        "schema": "erdos176.independent-cnf-audit.v1",
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "n": n,
        "k": k,
        "ell": ell,
        "fix_first": fix_first,
        "variables": declared_variables,
        "clauses": declared_clauses,
        "local_gadget_truth_tables": "PASS",
        "exact_clause_stream": "PASS",
    }
    if overlap_links:
        report["overlap_links"] = "PASS"
        report["overlap_relation_truth_table"] = "PASS"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cnf", type=Path)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--ell", type=int, default=2)
    parser.add_argument("--fix-first", action="store_true")
    parser.add_argument("--overlap-links", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = audit(
        args.cnf,
        n=args.n,
        k=args.k,
        ell=args.ell,
        fix_first=args.fix_first,
        overlap_links=args.overlap_links,
    )
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
