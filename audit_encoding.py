#!/usr/bin/env python3
"""End-to-end audit of the custom encoding on known exact cases."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import nk2


CASES = (
    # (N, k, expected CNF status)
    (2, 2, "SAT"),
    (3, 2, "UNSAT"),
    (8, 3, "SAT"),
    (9, 3, "UNSAT"),
    (21, 5, "SAT"),
    (22, 5, "UNSAT"),
    (48, 7, "SAT"),
    (49, 7, "UNSAT"),
)


def parse_original_model(output: str, n: int) -> tuple[int, ...]:
    assignments: dict[int, bool] = {}
    for line in output.splitlines():
        if not line.startswith("v "):
            continue
        for token in line[2:].split():
            literal = int(token)
            if literal:
                assignments[abs(literal)] = literal > 0
    missing = [variable for variable in range(1, n + 1) if variable not in assignments]
    if missing:
        raise AssertionError(f"SAT output omitted original variables: {missing}")
    return tuple(1 if assignments[i] else -1 for i in range(1, n + 1))


def run_case(
    workdir: Path,
    solver: Path,
    checker: Path,
    encoding: str,
    canonical_reversal: bool,
    n: int,
    k: int,
    expected: str,
) -> None:
    clauses, nvars = nk2.build_cnf(
        n,
        k,
        2,
        fix_first=True,
        encoding=encoding,
        canonical_reversal=canonical_reversal,
    )
    symmetry = "orbit" if canonical_reversal else "x1"
    stem = f"k{k}_N{n}_{symmetry}_{encoding}"
    cnf = workdir / f"{stem}.cnf"
    proof = workdir / f"{stem}.drat"
    nk2.write_dimacs(cnf, clauses, nvars, comments=(f"audit {stem}",))

    result = subprocess.run(
        (str(solver), str(cnf), str(proof)),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    actual = {10: "SAT", 20: "UNSAT"}.get(result.returncode, "ERROR")
    if actual != expected:
        raise AssertionError(
            f"{stem}: expected {expected}, got rc={result.returncode}\n{result.stdout}"
        )

    if actual == "SAT":
        coloring = parse_original_model(result.stdout, n)
        verification = nk2.verify_coloring(coloring, k, 2)
        if not verification["avoids"]:
            raise AssertionError(f"{stem}: solver model fails exact evaluator")
    else:
        checked = subprocess.run(
            (str(checker), str(cnf), str(proof)),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if checked.returncode != 0 or "s VERIFIED" not in checked.stdout:
            raise AssertionError(
                f"{stem}: proof did not verify\n{checked.stdout}"
            )

    print(
        f"PASS {stem}: {actual}; vars={nvars}; clauses={len(clauses)}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, default=Path("audit"))
    args = parser.parse_args()

    args.workdir.mkdir(parents=True, exist_ok=True)
    variants = (
        (encoding, canonical_reversal)
        for encoding in ("threshold", "totalizer")
        for canonical_reversal in (False, True)
    )
    for encoding, canonical_reversal in variants:
        for n, k, expected in CASES:
            run_case(
                args.workdir,
                args.solver,
                args.checker,
                encoding,
                canonical_reversal,
                n,
                k,
                expected,
            )
    print(f"OVERALL PASS: {4 * len(CASES)} known-case checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
