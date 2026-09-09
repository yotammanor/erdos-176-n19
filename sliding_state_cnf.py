#!/usr/bin/env python3
"""Generate a compact CNF for odd-k discrepancy-2 AP avoidance.

For each k-term AP P(a,d), a Boolean y(a,d) records whether P has
(k+1)/2 rather than (k-1)/2 positive entries.  One cardinality equation is
encoded at the root of each overlap chain.  Every later equation follows from

    y(a,d) - y(a+d,d) - x(a) + x(a+kd) = 0.

Thus the encoding has one counter per residue chain, not one per progression.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterator, Sequence

import nk2


def relation_clauses(variables: Sequence[int]) -> Iterator[list[int]]:
    """Encode y1 - y2 - first + last = 0 by excluding invalid rows."""
    if len(variables) != 4 or len(set(variables)) != 4:
        raise ValueError("relation requires four distinct variables")
    for bits in itertools.product((0, 1), repeat=4):
        y1, y2, first, last = bits
        if y1 - y2 - first + last == 0:
            continue
        yield [
            -variable if bit else variable
            for variable, bit in zip(variables, bits)
        ]


def append_exact_counter(
    clauses: list[list[int]],
    literals: Sequence[int],
    target: int,
    top_id: int,
) -> tuple[int, int]:
    """Append an equivalence-complete threshold counter for exact cardinality."""
    if not 0 <= target <= len(literals):
        raise ValueError("invalid exact-cardinality target")
    if not literals or target in (0, len(literals)):
        for literal in literals:
            clauses.append([literal if target else -literal])
        return top_id, 0

    limit = target + 1
    states: dict[tuple[int, int], int] = {}
    first_new_variable = top_id + 1
    for i, literal in enumerate(literals, start=1):
        for j in range(1, min(i, limit) + 1):
            top_id += 1
            current = top_id
            states[i, j] = current
            previous_same = states.get((i - 1, j))
            previous_lower = states.get((i - 1, j - 1))

            if j == 1:
                if previous_same is None:
                    clauses.extend(([-current, literal], [current, -literal]))
                else:
                    clauses.extend(
                        (
                            [-previous_same, current],
                            [-literal, current],
                            [-current, previous_same, literal],
                        )
                    )
            elif previous_same is None:
                if previous_lower is None:
                    raise AssertionError("missing lower threshold state")
                clauses.extend(
                    (
                        [-current, previous_lower],
                        [-current, literal],
                        [current, -previous_lower, -literal],
                    )
                )
            else:
                if previous_lower is None:
                    raise AssertionError("missing lower threshold state")
                clauses.extend(
                    (
                        [-previous_same, current],
                        [-previous_lower, -literal, current],
                        [-current, previous_same, previous_lower],
                        [-current, previous_same, literal],
                    )
                )

    clauses.append([states[len(literals), target]])
    clauses.append([-states[len(literals), target + 1]])
    return top_id, top_id - first_new_variable + 1


def build_cnf(
    n: int,
    k: int,
    ell: int = 2,
    *,
    fix_first: bool = False,
) -> tuple[list[list[int]], int, dict[str, int]]:
    """Build the compact overlap-chain CNF."""
    if n < 0 or k < 2:
        raise ValueError("require n >= 0 and k >= 2")
    if ell != 2 or k % 2 == 0:
        raise ValueError("sliding-state CNF requires odd k and ell=2")

    progressions = list(nk2.iter_aps(n, k))
    state_variable: dict[tuple[int, int], int] = {}
    for index, progression in enumerate(progressions, start=1):
        difference = progression[1] - progression[0]
        state_variable[(progression[0], difference)] = n + index

    clauses: list[list[int]] = []
    top_id = n + len(progressions)
    root_count = 0
    counter_variable_count = 0
    max_difference = (n - 1) // (k - 1) if n else 0
    target = (k + 1) // 2

    for difference in range(1, max_difference + 1):
        last_start = n - (k - 1) * difference
        for start in range(1, min(difference, last_start) + 1):
            progression = [
                start + offset * difference for offset in range(k)
            ]
            state = state_variable[(start, difference)]
            top_id, added_variables = append_exact_counter(
                clauses,
                [*progression, -state],
                target,
                top_id,
            )
            counter_variable_count += added_variables
            root_count += 1

    overlap_count = 0
    for difference in range(1, max_difference + 1):
        last_start = n - (k - 1) * difference
        for start in range(1, last_start - difference + 1):
            clauses.extend(
                relation_clauses(
                    (
                        state_variable[(start, difference)],
                        state_variable[(start + difference, difference)],
                        start,
                        start + k * difference,
                    )
                )
            )
            overlap_count += 1

    if fix_first and n:
        clauses.append([1])

    return clauses, top_id, {
        "progressions": len(progressions),
        "state_variables": len(progressions),
        "root_counters": root_count,
        "counter_variables": counter_variable_count,
        "overlap_relations": overlap_count,
    }


def write_dimacs(
    path: Path,
    n: int,
    k: int,
    ell: int = 2,
    *,
    fix_first: bool = False,
) -> dict[str, object]:
    """Write the compact overlap-chain encoding as deterministic DIMACS."""
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    clauses, nvars, counts = build_cnf(
        n, k, ell, fix_first=fix_first
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("wb") as stream:
        def emit(line: str) -> None:
            encoded = line.encode("ascii")
            stream.write(encoded)
            digest.update(encoded)

        emit("c compact overlap-chain AP-state encoding\n")
        emit(f"c N={n} k={k} ell={ell} fix_first={int(fix_first)}\n")
        emit(f"p cnf {nvars} {len(clauses)}\n")
        for clause in clauses:
            emit(" ".join(map(str, clause)) + " 0\n")

    return {
        "schema": "erdos176.sliding-state-cnf.v1",
        "path": str(path.resolve()),
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
        "n": n,
        "k": k,
        "ell": ell,
        "fix_first": fix_first,
        "variables": nvars,
        "clauses": len(clauses),
        **counts,
    }


def write_opb(
    path: Path,
    n: int,
    k: int,
    ell: int = 2,
    *,
    fix_first: bool = False,
) -> dict[str, object]:
    """Write the same overlap-chain reduction directly as pseudo-Boolean."""
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    if n < 0 or k < 2:
        raise ValueError("require n >= 0 and k >= 2")
    if ell != 2 or k % 2 == 0:
        raise ValueError("sliding-state OPB requires odd k and ell=2")

    progressions = list(nk2.iter_aps(n, k))
    state_variable = {
        (progression[0], progression[1] - progression[0]): n + index
        for index, progression in enumerate(progressions, start=1)
    }
    maximum_difference = (n - 1) // (k - 1) if n else 0
    roots: list[tuple[int, int]] = []
    overlaps: list[tuple[int, int]] = []
    for difference in range(1, maximum_difference + 1):
        last_start = n - (k - 1) * difference
        roots.extend(
            (start, difference)
            for start in range(1, min(difference, last_start) + 1)
        )
        overlaps.extend(
            (start, difference)
            for start in range(1, last_start - difference + 1)
        )

    nvars = n + len(progressions)
    nconstraints = 2 * (len(roots) + len(overlaps)) + int(
        fix_first and n > 0
    )
    lower = (k - 1) // 2
    digest = hashlib.sha256()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        def emit(line: str) -> None:
            encoded = line.encode("ascii")
            stream.write(encoded)
            digest.update(encoded)

        emit(
            f"* #variable= {nvars} #constraint= {nconstraints} "
            "#equal= 0 intsize= 32\n"
        )
        emit(
            f"* compact overlap-chain state encoding; "
            f"N={n} k={k} ell={ell}\n"
        )
        for start, difference in roots:
            positions = (
                start + offset * difference for offset in range(k)
            )
            state = state_variable[(start, difference)]
            positive = " ".join(
                [*(f"+1 x{position}" for position in positions), f"-1 x{state}"]
            )
            positions = (
                start + offset * difference for offset in range(k)
            )
            negative = " ".join(
                [*(f"-1 x{position}" for position in positions), f"+1 x{state}"]
            )
            emit(f"{positive} >= {lower};\n")
            emit(f"{negative} >= {-lower};\n")
        for start, difference in overlaps:
            first_state = state_variable[(start, difference)]
            second_state = state_variable[(start + difference, difference)]
            last = start + k * difference
            emit(
                f"+1 x{first_state} -1 x{second_state} "
                f"-1 x{start} +1 x{last} >= 0;\n"
            )
            emit(
                f"-1 x{first_state} +1 x{second_state} "
                f"+1 x{start} -1 x{last} >= 0;\n"
            )
        if fix_first and n:
            emit("+1 x1 >= 1;\n")

    return {
        "schema": "erdos176.sliding-state-opb.v1",
        "path": str(path.resolve()),
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
        "n": n,
        "k": k,
        "ell": ell,
        "fix_first": fix_first,
        "variables": nvars,
        "constraints": nconstraints,
        "progressions": len(progressions),
        "state_variables": len(progressions),
        "root_equations": len(roots),
        "overlap_equations": len(overlaps),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--ell", type=int, default=2)
    parser.add_argument("--fix-first", action="store_true")
    parser.add_argument("--format", choices=("cnf", "opb"), default="cnf")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    writer = write_dimacs if args.format == "cnf" else write_opb
    report = writer(
        args.output,
        args.n,
        args.k,
        args.ell,
        fix_first=args.fix_first,
    )
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        if args.report.exists():
            raise FileExistsError(f"refusing to overwrite {args.report}")
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
