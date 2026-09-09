#!/usr/bin/env python3
"""Independently audit the compact overlap-chain DIMACS encoding."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterator, Sequence, TextIO, Union


Clause = tuple[int, ...]


def clause_satisfied(clause: Sequence[int], values: dict[int, bool]) -> bool:
    return any(values[abs(literal)] == (literal > 0) for literal in clause)


def audit_local_counter_gadgets() -> None:
    """Check each recurrence template against its claimed Boolean meaning."""
    templates = (
        (((-4, 3), (4, -3)), lambda a, b, x: x),
        (
            ((-1, 4), (-3, 4), (-4, 1, 3)),
            lambda a, b, x: a or x,
        ),
        (
            ((-4, 2), (-4, 3), (4, -2, -3)),
            lambda a, b, x: b and x,
        ),
        (
            ((-1, 4), (-2, -3, 4), (-4, 1, 2), (-4, 1, 3)),
            lambda a, b, x: a or (b and x),
        ),
    )
    for clauses, meaning in templates:
        for a, b, x, current in itertools.product((False, True), repeat=4):
            values = {1: a, 2: b, 3: x, 4: current}
            observed = all(clause_satisfied(clause, values) for clause in clauses)
            if observed != (current == meaning(a, b, x)):
                raise AssertionError(
                    f"counter template has a bad row: {clauses}, {values}"
                )


def relation_clauses(variables: Sequence[int]) -> Iterator[Clause]:
    """Derive clauses for y1-y2-first+last=0 from its complete truth table."""
    if len(variables) != 4 or len(set(variables)) != 4:
        raise ValueError("overlap relation needs four distinct variables")
    for row in itertools.product((False, True), repeat=4):
        y1, y2, first, last = map(int, row)
        if y1 - y2 - first + last:
            yield tuple(
                -variable if bit else variable
                for variable, bit in zip(variables, row)
            )


def audit_relation_truth_table() -> None:
    variables = (1, 2, 3, 4)
    clauses = tuple(relation_clauses(variables))
    if len(clauses) != 10:
        raise AssertionError("overlap relation must exclude ten rows")
    for row in itertools.product((False, True), repeat=4):
        values = dict(zip(variables, row))
        observed = all(clause_satisfied(clause, values) for clause in clauses)
        y1, y2, first, last = map(int, row)
        expected = y1 - y2 - first + last == 0
        if observed != expected:
            raise AssertionError(f"bad overlap row: {row}")


def progressions(n: int, k: int) -> Iterator[tuple[int, int, tuple[int, ...]]]:
    """Enumerate (start, difference, positions) without production imports."""
    difference = 1
    while 1 + (k - 1) * difference <= n:
        final_start = n - (k - 1) * difference
        for start in range(1, final_start + 1):
            positions = tuple(
                start + offset * difference for offset in range(k)
            )
            yield start, difference, positions
        difference += 1


def audit_chain_cover(n: int, k: int) -> tuple[int, int, int]:
    """Check roots and successor edges form one path cover of all AP starts."""
    progression_keys = {
        (start, difference)
        for start, difference, _ in progressions(n, k)
    }
    roots: set[tuple[int, int]] = set()
    edges: dict[tuple[int, int], tuple[int, int]] = {}
    maximum_difference = (n - 1) // (k - 1) if n else 0
    for difference in range(1, maximum_difference + 1):
        final_start = n - (k - 1) * difference
        roots.update(
            (start, difference)
            for start in range(1, min(difference, final_start) + 1)
        )
        for start in range(1, final_start - difference + 1):
            edges[(start + difference, difference)] = (start, difference)

    if not roots <= progression_keys:
        raise AssertionError("chain root is not a progression")
    if set(edges) & roots:
        raise AssertionError("chain root unexpectedly has a predecessor")
    if progression_keys != roots | set(edges):
        raise AssertionError("roots and successor edges do not cover every AP")

    for key in progression_keys:
        seen: set[tuple[int, int]] = set()
        current = key
        while current not in roots:
            if current in seen or current not in edges:
                raise AssertionError(f"bad predecessor chain at {key}")
            seen.add(current)
            current = edges[current]
    return len(progression_keys), len(roots), len(edges)


def exact_counter_clauses(
    literals: Sequence[int],
    target: int,
    next_variable: int,
) -> Iterator[Union[Clause, int]]:
    """Yield recurrence clauses and finally the updated variable counter.

    The final yielded integer is control metadata, never a DIMACS clause.
    """
    limit = target + 1
    states: dict[tuple[int, int], int] = {}
    for prefix, literal in enumerate(literals, start=1):
        for threshold in range(1, min(prefix, limit) + 1):
            next_variable += 1
            current = next_variable
            states[prefix, threshold] = current
            same = states.get((prefix - 1, threshold))
            lower = states.get((prefix - 1, threshold - 1))
            if threshold == 1:
                if same is None:
                    yield (-current, literal)
                    yield (current, -literal)
                else:
                    yield (-same, current)
                    yield (-literal, current)
                    yield (-current, same, literal)
            elif same is None:
                if lower is None:
                    raise AssertionError("missing lower counter state")
                yield (-current, lower)
                yield (-current, literal)
                yield (current, -lower, -literal)
            else:
                if lower is None:
                    raise AssertionError("missing lower counter state")
                yield (-same, current)
                yield (-lower, -literal, current)
                yield (-current, same, lower)
                yield (-current, same, literal)
    yield (states[len(literals), target],)
    yield (-states[len(literals), target + 1],)
    yield next_variable


def expected_clauses(
    n: int, k: int, ell: int, fix_first: bool
) -> Iterator[Clause]:
    if ell != 2 or k % 2 == 0:
        raise ValueError("compact encoding requires odd k and ell=2")
    progression_list = list(progressions(n, k))
    state = {
        (start, difference): n + index
        for index, (start, difference, _) in enumerate(
            progression_list, start=1
        )
    }
    next_variable = n + len(progression_list)
    target = (k + 1) // 2
    maximum_difference = (n - 1) // (k - 1) if n else 0

    for difference in range(1, maximum_difference + 1):
        final_start = n - (k - 1) * difference
        for start in range(1, min(difference, final_start) + 1):
            positions = tuple(
                start + offset * difference for offset in range(k)
            )
            generated = exact_counter_clauses(
                (*positions, -state[(start, difference)]),
                target,
                next_variable,
            )
            for item in generated:
                if isinstance(item, int):
                    next_variable = item
                else:
                    yield item

    for difference in range(1, maximum_difference + 1):
        final_start = n - (k - 1) * difference
        for start in range(1, final_start - difference + 1):
            yield from relation_clauses(
                (
                    state[(start, difference)],
                    state[(start + difference, difference)],
                    start,
                    start + k * difference,
                )
            )
    if fix_first and n:
        yield (1,)


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
) -> dict[str, object]:
    audit_local_counter_gadgets()
    audit_relation_truth_table()
    num_progressions, num_roots, num_edges = audit_chain_cover(n, k)

    with path.open("r", encoding="ascii") as stream:
        lines = data_lines(stream)
        try:
            header = next(lines)
        except StopIteration as error:
            raise ValueError("empty DIMACS") from error
        fields = header.split()
        if len(fields) != 4 or fields[:2] != ["p", "cnf"]:
            raise ValueError(f"invalid DIMACS header: {header!r}")
        declared_variables, declared_clauses = map(int, fields[2:])

        maximum_variable = 0
        count = 0
        for count, expected in enumerate(
            expected_clauses(n, k, ell, fix_first), start=1
        ):
            try:
                line = next(lines)
            except StopIteration as error:
                raise ValueError(
                    f"DIMACS ended before expected clause {count}"
                ) from error
            tokens = tuple(map(int, line.split()))
            if not tokens or tokens[-1] != 0 or 0 in tokens[:-1]:
                raise ValueError(f"bad terminator at clause {count}")
            actual = tokens[:-1]
            if actual != expected:
                raise ValueError(
                    f"clause {count} differs: expected {expected}, got {actual}"
                )
            maximum_variable = max(
                maximum_variable, *(abs(literal) for literal in expected)
            )
        try:
            extra = next(lines)
        except StopIteration:
            extra = None
        if extra is not None:
            raise ValueError(f"unexpected extra DIMACS line: {extra!r}")

    if declared_clauses != count:
        raise ValueError(
            f"header has {declared_clauses} clauses; audited {count}"
        )
    if declared_variables != maximum_variable:
        raise ValueError(
            f"header has {declared_variables} variables; "
            f"audited maximum is {maximum_variable}"
        )
    return {
        "schema": "erdos176.independent-sliding-cnf-audit.v1",
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "n": n,
        "k": k,
        "ell": ell,
        "fix_first": fix_first,
        "variables": declared_variables,
        "clauses": declared_clauses,
        "progressions": num_progressions,
        "chain_roots": num_roots,
        "overlap_edges": num_edges,
        "local_counter_truth_tables": "PASS",
        "overlap_relation_truth_table": "PASS",
        "chain_partition": "PASS",
        "exact_clause_stream": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cnf", type=Path)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--ell", type=int, default=2)
    parser.add_argument("--fix-first", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(
        args.cnf,
        n=args.n,
        k=args.k,
        ell=args.ell,
        fix_first=args.fix_first,
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
