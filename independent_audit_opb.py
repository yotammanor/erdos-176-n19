#!/usr/bin/env python3
"""Independently check that an OPB file encodes the stated AP problem."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path


Constraint = tuple[tuple[tuple[int, int], ...], int]
HEADER = re.compile(
    r"\* #variable= (\d+) #constraint= (\d+) #equal= (\d+) intsize= (\d+)"
)


def arithmetic_progressions(n: int, k: int) -> list[tuple[int, ...]]:
    """Enumerate APs directly, without importing the production generator."""
    progressions: list[tuple[int, ...]] = []
    difference = 1
    while 1 + (k - 1) * difference <= n:
        start = 1
        while start + (k - 1) * difference <= n:
            progressions.append(
                tuple(start + offset * difference for offset in range(k))
            )
            start += 1
        difference += 1
    return progressions


def parse_opb(path: Path) -> tuple[tuple[int, int, int, int], Counter[Constraint]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise AssertionError("OPB file is empty")
    match = HEADER.fullmatch(lines[0])
    if match is None:
        raise AssertionError(f"invalid OPB header: {lines[0]!r}")
    header = tuple(int(group) for group in match.groups())

    constraints: Counter[Constraint] = Counter()
    for line_number, line in enumerate(lines[1:], start=2):
        if not line or line.startswith("*"):
            continue
        if not line.endswith(";") or line.count(">=") != 1:
            raise AssertionError(f"line {line_number}: unsupported constraint")
        left, right = line[:-1].split(">=")
        tokens = left.split()
        if len(tokens) % 2:
            raise AssertionError(f"line {line_number}: incomplete term")
        terms: list[tuple[int, int]] = []
        seen: set[int] = set()
        for index in range(0, len(tokens), 2):
            coefficient = int(tokens[index])
            variable_token = tokens[index + 1]
            if not re.fullmatch(r"x[1-9]\d*", variable_token):
                raise AssertionError(
                    f"line {line_number}: invalid variable {variable_token!r}"
                )
            variable = int(variable_token[1:])
            if variable in seen:
                raise AssertionError(
                    f"line {line_number}: repeated variable x{variable}"
                )
            seen.add(variable)
            terms.append((coefficient, variable))
        constraints[(tuple(terms), int(right))] += 1
    return header, constraints


def expected_constraints(
    n: int,
    k: int,
    ell: int,
    fix_first: bool,
) -> Counter[Constraint]:
    allowed_counts = [
        count for count in range(k + 1) if abs(2 * count - k) < ell
    ]
    if not allowed_counts:
        raise ValueError("no color count can meet the discrepancy bound")
    lower, upper = min(allowed_counts), max(allowed_counts)

    expected: Counter[Constraint] = Counter()
    for progression in arithmetic_progressions(n, k):
        expected[(tuple((1, position) for position in progression), lower)] += 1
        expected[(tuple((-1, position) for position in progression), -upper)] += 1
    if fix_first:
        expected[(((1, 1),), 1)] += 1
    return expected


def expected_state_constraints(
    n: int,
    k: int,
    ell: int,
    fix_first: bool,
) -> tuple[int, Counter[Constraint], int]:
    allowed_counts = [
        count for count in range(k + 1) if abs(2 * count - k) < ell
    ]
    if len(allowed_counts) != 2 or allowed_counts[1] != allowed_counts[0] + 1:
        raise ValueError("state encoding requires exactly two consecutive counts")
    lower = allowed_counts[0]
    progressions = arithmetic_progressions(n, k)
    states: dict[tuple[int, int], int] = {}
    expected: Counter[Constraint] = Counter()
    for index, progression in enumerate(progressions, start=1):
        difference = progression[1] - progression[0]
        state = n + index
        states[(progression[0], difference)] = state
        expected[
            (
                tuple(
                    [*((1, position) for position in progression), (-1, state)]
                ),
                lower,
            )
        ] += 1
        expected[
            (
                tuple(
                    [*((-1, position) for position in progression), (1, state)]
                ),
                -lower,
            )
        ] += 1

    links = 0
    difference = 1
    while 1 + (k - 1) * difference <= n:
        last_start = n - (k - 1) * difference
        start = 1
        while start + difference <= last_start:
            first_state = states[(start, difference)]
            second_state = states[(start + difference, difference)]
            last = start + k * difference
            expected[
                (
                    (
                        (1, first_state),
                        (-1, second_state),
                        (-1, start),
                        (1, last),
                    ),
                    0,
                )
            ] += 1
            expected[
                (
                    (
                        (-1, first_state),
                        (1, second_state),
                        (1, start),
                        (-1, last),
                    ),
                    0,
                )
            ] += 1
            links += 1
            start += 1
        difference += 1
    if fix_first:
        expected[(((1, 1),), 1)] += 1
    return n + len(progressions), expected, links


def expected_sliding_state_constraints(
    n: int,
    k: int,
    ell: int,
    fix_first: bool,
) -> tuple[int, Counter[Constraint], int, int]:
    """Derive the root equations and complete overlap-chain equations."""
    allowed_counts = [
        count for count in range(k + 1) if abs(2 * count - k) < ell
    ]
    if len(allowed_counts) != 2 or allowed_counts[1] != allowed_counts[0] + 1:
        raise ValueError("sliding state encoding needs two consecutive counts")
    lower = allowed_counts[0]
    progressions = arithmetic_progressions(n, k)
    states = {
        (progression[0], progression[1] - progression[0]): n + index
        for index, progression in enumerate(progressions, start=1)
    }
    expected: Counter[Constraint] = Counter()
    roots = 0
    links = 0
    difference = 1
    while 1 + (k - 1) * difference <= n:
        last_start = n - (k - 1) * difference
        for start in range(1, min(difference, last_start) + 1):
            progression = tuple(
                start + offset * difference for offset in range(k)
            )
            state = states[(start, difference)]
            expected[
                (
                    tuple(
                        [*((1, position) for position in progression), (-1, state)]
                    ),
                    lower,
                )
            ] += 1
            expected[
                (
                    tuple(
                        [*((-1, position) for position in progression), (1, state)]
                    ),
                    -lower,
                )
            ] += 1
            roots += 1
        for start in range(1, last_start - difference + 1):
            first_state = states[(start, difference)]
            second_state = states[(start + difference, difference)]
            last = start + k * difference
            expected[
                (
                    (
                        (1, first_state),
                        (-1, second_state),
                        (-1, start),
                        (1, last),
                    ),
                    0,
                )
            ] += 1
            expected[
                (
                    (
                        (-1, first_state),
                        (1, second_state),
                        (1, start),
                        (-1, last),
                    ),
                    0,
                )
            ] += 1
            links += 1
        difference += 1
    if fix_first:
        expected[(((1, 1),), 1)] += 1
    return n + len(progressions), expected, roots, links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--ell", type=int, default=2)
    parser.add_argument("--fix-first", action="store_true")
    encoding = parser.add_mutually_exclusive_group()
    encoding.add_argument("--state-extended", action="store_true")
    encoding.add_argument("--sliding-state", action="store_true")
    args = parser.parse_args()

    header, observed = parse_opb(args.path)
    if args.sliding_state:
        expected_nvars, expected, roots, links = (
            expected_sliding_state_constraints(
                args.n,
                args.k,
                args.ell,
                args.fix_first,
            )
        )
    elif args.state_extended:
        expected_nvars, expected, links = expected_state_constraints(
            args.n,
            args.k,
            args.ell,
            args.fix_first,
        )
        roots = len(arithmetic_progressions(args.n, args.k))
    else:
        expected_nvars = args.n
        expected = expected_constraints(args.n, args.k, args.ell, args.fix_first)
        roots = len(arithmetic_progressions(args.n, args.k))
        links = 0
    nvars, declared_constraints, equalities, intsize = header
    failures: list[str] = []
    if nvars != expected_nvars:
        failures.append(
            f"header declares {nvars} variables, expected {expected_nvars}"
        )
    if declared_constraints != sum(observed.values()):
        failures.append(
            "header constraint count does not match parsed constraints"
        )
    if equalities != 0:
        failures.append("header declares unexpected equalities")
    if intsize < 5:
        failures.append("header intsize cannot represent the coefficients")
    used_variables = {
        variable
        for terms, _ in observed
        for _, variable in terms
    }
    if used_variables and max(used_variables) > nvars:
        failures.append("constraint uses a variable above the declared maximum")
    if observed != expected:
        missing = list((expected - observed).elements())[:3]
        extra = list((observed - expected).elements())[:3]
        failures.append(f"constraint multiset mismatch; missing={missing}, extra={extra}")

    if failures:
        raise AssertionError("; ".join(failures))
    digest = hashlib.sha256(args.path.read_bytes()).hexdigest()
    print(
        f"VERIFIED encoding: n={args.n} k={args.k} ell={args.ell} "
        f"constraints={sum(observed.values())} roots={roots} "
        f"links={links} sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
