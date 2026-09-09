#!/usr/bin/env python3
"""Certified-computation helpers for Erdős Problem 176.

N(k, ell) is the least N such that every coloring f: [N] -> {-1, +1}
has a k-term arithmetic progression P with

    abs(sum(f(i) for i in P)) >= ell.

The encoders and witness verifier use only the Python standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterable, Iterator, Sequence


Coloring = tuple[int, ...]
Progression = tuple[int, ...]


def iter_aps(n: int, k: int) -> Iterator[Progression]:
    """Yield all k-term APs in [1, n], ordered by difference then start."""
    if n < 0 or k < 2:
        raise ValueError("require n >= 0 and k >= 2")
    for difference in range(1, (n - 1) // (k - 1) + 1):
        for start in range(1, n - (k - 1) * difference + 1):
            yield tuple(start + offset * difference for offset in range(k))


def num_aps(n: int, k: int) -> int:
    """Count k-term APs in [1, n] without enumerating their terms."""
    max_difference = (n - 1) // (k - 1) if n >= 1 else 0
    return (
        max_difference * n
        - (k - 1) * max_difference * (max_difference + 1) // 2
    )


def parse_coloring(path: Path) -> Coloring:
    """Parse a +/- witness, ignoring blank and #-comment lines."""
    symbols: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.partition("#")[0]
        symbols.extend(char for char in line if not char.isspace())
    invalid = sorted(set(symbols) - {"+", "-"})
    if invalid:
        raise ValueError(f"invalid witness symbols: {invalid}")
    return tuple(1 if symbol == "+" else -1 for symbol in symbols)


def verify_coloring(
    coloring: Sequence[int], k: int, ell: int = 2
) -> dict[str, object]:
    """Exhaustively verify an avoidance witness using exact integer sums."""
    if any(value not in (-1, 1) for value in coloring):
        raise ValueError("coloring values must all be -1 or +1")
    n = len(coloring)
    histogram: dict[int, int] = {}
    max_abs_sum = -1
    first_bad: dict[str, object] | None = None

    for progression in iter_aps(n, k):
        total = sum(coloring[position - 1] for position in progression)
        histogram[total] = histogram.get(total, 0) + 1
        max_abs_sum = max(max_abs_sum, abs(total))
        if first_bad is None and abs(total) >= ell:
            first_bad = {
                "start": progression[0],
                "difference": progression[1] - progression[0],
                "sum": total,
                "progression": progression,
            }

    return {
        "n": n,
        "k": k,
        "ell": ell,
        "num_aps": num_aps(n, k),
        "max_abs_sum": max_abs_sum,
        "sum_histogram": dict(sorted(histogram.items())),
        "avoids": first_bad is None,
        "first_bad": first_bad,
    }


def threshold(k: int, ell: int) -> int:
    """Smallest number of one color forcing discrepancy at least ell."""
    if k < 2 or not 1 <= ell <= k:
        raise ValueError("require k >= 2 and 1 <= ell <= k")
    return (k + ell + 1) // 2


def build_threshold_cnf(
    n: int, k: int, ell: int = 2, *, fix_first: bool = False
) -> tuple[list[list[int]], int]:
    """Encode existence of an avoiding coloring with threshold counters.

    Original variable x_i means f(i)=+1. For each AP, if
    u=ceil((k+ell)/2), avoidance is equivalent to

        k-u+1 <= #plus <= u-1.

    For each AP, s[i,j] means "at least j of the first i literals are true."
    The recurrence

        s[i,j] <-> s[i-1,j] OR (s[i-1,j-1] AND x_i)

    is encoded in both directions, with fresh variables per progression.
    Only thresholds through u are needed. This implementation is deliberately
    self-contained so the mathematical encoding is auditable without trusting
    a third-party cardinality generator.

    When fix_first is true, x_1 is fixed positive. This preserves
    satisfiability because global color complementation is a symmetry.
    """
    u = threshold(k, ell)
    lower = k - u + 1
    clauses: list[list[int]] = []
    top_id = n

    for progression in iter_aps(n, k):
        states: dict[tuple[int, int], int] = {}
        for i, literal in enumerate(progression, start=1):
            for j in range(1, min(i, u) + 1):
                top_id += 1
                current = top_id
                states[i, j] = current

                previous_same = states.get((i - 1, j))  # absent means False
                if j == 1:
                    # s[i,1] <-> s[i-1,1] OR literal. At i=1 the
                    # previous state is False, so this reduces to equality.
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
                    continue

                previous_lower = states[i - 1, j - 1]
                if previous_same is None:
                    # s[i,i] <-> s[i-1,i-1] AND literal.
                    clauses.extend(
                        (
                            [-current, previous_lower],
                            [-current, literal],
                            [current, -previous_lower, -literal],
                        )
                    )
                else:
                    # Full equivalence with A=previous_same,
                    # B=previous_lower, and X=literal:
                    # current <-> A OR (B AND X).
                    clauses.extend(
                        (
                            [-previous_same, current],
                            [-previous_lower, -literal, current],
                            [-current, previous_same, previous_lower],
                            [-current, previous_same, literal],
                        )
                    )

        clauses.append([states[k, lower]])
        clauses.append([-states[k, u]])

    if fix_first and n:
        clauses.append([1])
    return clauses, top_id


def build_totalizer_cnf(
    n: int, k: int, ell: int = 2, *, fix_first: bool = False
) -> tuple[list[list[int]], int]:
    """Encode avoidance with two truncated totalizers per progression.

    A totalizer output ``o_j`` means that at least ``j`` input literals are
    true.  Only forward implications are needed for an at-most constraint:
    every pair of child thresholds implies the corresponding parent threshold.
    Forbidding output ``bound + 1`` therefore enforces the bound.  Applying the
    same construction to the negated literals supplies the lower bound.
    """
    bound = threshold(k, ell) - 1
    clauses: list[list[int]] = []
    top_id = n

    def at_most(literals: Sequence[int]) -> None:
        nonlocal top_id

        def node(inputs: Sequence[int]) -> list[int]:
            nonlocal top_id
            if len(inputs) == 1:
                return [inputs[0]]

            split = len(inputs) // 2
            left = node(inputs[:split])
            right = node(inputs[split:])
            width = min(len(inputs), bound + 1)
            output: list[int] = []
            for _ in range(width):
                top_id += 1
                output.append(top_id)

            for left_count in range(len(left) + 1):
                for right_count in range(len(right) + 1):
                    total = left_count + right_count
                    if not 1 <= total <= width:
                        continue
                    clause: list[int] = []
                    if left_count:
                        clause.append(-left[left_count - 1])
                    if right_count:
                        clause.append(-right[right_count - 1])
                    clause.append(output[total - 1])
                    clauses.append(clause)
            return output

        if bound < 0:
            clauses.append([])
        elif bound == 0:
            clauses.extend([-literal] for literal in literals)
        elif bound < len(literals):
            root = node(literals)
            clauses.append([-root[bound]])

    for progression in iter_aps(n, k):
        at_most(progression)
        at_most(tuple(-position for position in progression))

    if fix_first and n:
        clauses.append([1])
    return clauses, top_id


def build_cnf(
    n: int,
    k: int,
    ell: int = 2,
    *,
    fix_first: bool = False,
    encoding: str = "threshold",
    canonical_reversal: bool = False,
) -> tuple[list[list[int]], int]:
    """Encode existence of an avoiding coloring with the selected encoding."""
    if encoding == "threshold":
        clauses, top_id = build_threshold_cnf(
            n, k, ell, fix_first=fix_first
        )
    elif encoding == "totalizer":
        clauses, top_id = build_totalizer_cnf(
            n, k, ell, fix_first=fix_first
        )
    else:
        raise ValueError(f"unknown encoding: {encoding}")

    if not canonical_reversal:
        return clauses, top_id
    if not fix_first:
        raise ValueError("canonical_reversal requires fix_first")

    def add_lex_leq(left: Sequence[int], right: Sequence[int]) -> None:
        """Add ``left <=lex right``; each element is a signed Boolean literal."""
        nonlocal top_id
        equal_prefix: int | None = None  # None denotes the true empty prefix.

        if len(left) != len(right):
            raise ValueError("lexicographic vectors must have equal length")
        for index, (left_lit, right_lit) in enumerate(zip(left, right)):
            lex_clause = [-left_lit, right_lit]
            if equal_prefix is not None:
                lex_clause.insert(0, -equal_prefix)
            clauses.append(lex_clause)

            if index == len(left) - 1:
                continue
            top_id += 1
            current = top_id
            if equal_prefix is not None:
                clauses.append([-current, equal_prefix])
                prefix_guard = [-equal_prefix]
            else:
                prefix_guard = []

            # current -> (left_lit == right_lit)
            clauses.append([-current, -left_lit, right_lit])
            clauses.append([-current, left_lit, -right_lit])
            # previous equality and either common bit value -> current
            clauses.append(prefix_guard + [-left_lit, -right_lit, current])
            clauses.append(prefix_guard + [left_lit, right_lit, current])
            equal_prefix = current

    original = tuple(range(1, n + 1))
    reversed_original = tuple(range(n, 0, -1))
    complemented_reversal = tuple(-variable for variable in reversed_original)

    # With x_1=true, these select the lexicographically greatest member of
    # every orbit under color complementation and interval reversal.
    add_lex_leq(reversed_original, original)
    add_lex_leq(complemented_reversal, original)
    return clauses, top_id


def write_dimacs(
    path: Path,
    clauses: Iterable[Sequence[int]],
    nvars: int,
    *,
    comments: Sequence[str] = (),
) -> dict[str, object]:
    """Write deterministic DIMACS and return a hash manifest."""
    materialized = [list(clause) for clause in clauses]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as stream:
        for comment in comments:
            stream.write(f"c {comment}\n")
        stream.write(f"p cnf {nvars} {len(materialized)}\n")
        for clause in materialized:
            stream.write(" ".join(map(str, clause)))
            stream.write(" 0\n")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": str(path),
        "nvars": nvars,
        "nclauses": len(materialized),
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def write_opb(
    path: Path,
    n: int,
    k: int,
    ell: int = 2,
    *,
    fix_first: bool = False,
) -> dict[str, object]:
    """Write the avoidance problem directly as pseudo-Boolean constraints."""
    upper = threshold(k, ell) - 1
    lower = k - upper
    progressions = list(iter_aps(n, k))
    nconstraints = 2 * len(progressions) + int(fix_first and n > 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write(
            f"* #variable= {n} #constraint= {nconstraints} "
            "#equal= 0 intsize= 32\n"
        )
        stream.write(f"* N={n} k={k} ell={ell}; x_i=1 means f(i)=+1\n")
        for progression in progressions:
            positive = " ".join(f"+1 x{position}" for position in progression)
            negative = " ".join(f"-1 x{position}" for position in progression)
            stream.write(f"{positive} >= {lower};\n")
            stream.write(f"{negative} >= {-upper};\n")
        if fix_first and n:
            stream.write("+1 x1 >= 1;\n")

    return {
        "path": str(path),
        "nvars": n,
        "nconstraints": nconstraints,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "n": n,
        "k": k,
        "ell": ell,
        "num_aps": len(progressions),
        "fix_first": fix_first,
        "encoding": "direct OPB cardinality bounds",
    }


def write_state_opb(
    path: Path,
    n: int,
    k: int,
    ell: int = 2,
    *,
    fix_first: bool = False,
) -> dict[str, object]:
    """Write an equivalent OPB exposing each AP's two allowed sums.

    For odd ``k`` and ``ell=2``, every avoiding AP has either ``(k-1)/2``
    or ``(k+1)/2`` positive entries.  A fresh Boolean state ``y_P`` selects
    which count by enforcing ``sum(x_i for i in P) - y_P = (k-1)/2``.
    Redundant four-variable equations expose the exact relation between
    consecutive overlapping APs of the same difference.
    """
    if ell != 2 or k % 2 == 0:
        raise ValueError("state OPB requires odd k and ell=2")
    progressions = list(iter_aps(n, k))
    lower = (k - 1) // 2
    state_variable: dict[tuple[int, int], int] = {}
    for index, progression in enumerate(progressions, start=1):
        difference = progression[1] - progression[0]
        state_variable[(progression[0], difference)] = n + index

    overlap_links: list[tuple[int, int, int, int]] = []
    max_difference = (n - 1) // (k - 1) if n else 0
    for difference in range(1, max_difference + 1):
        last_start = n - (k - 1) * difference
        for start in range(1, last_start - difference + 1):
            overlap_links.append(
                (
                    state_variable[(start, difference)],
                    state_variable[(start + difference, difference)],
                    start,
                    start + k * difference,
                )
            )

    nvars = n + len(progressions)
    nconstraints = (
        2 * len(progressions)
        + 2 * len(overlap_links)
        + int(fix_first and n > 0)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write(
            f"* #variable= {nvars} #constraint= {nconstraints} "
            "#equal= 0 intsize= 32\n"
        )
        stream.write(
            f"* N={n} k={k} ell={ell}; x1..x{n} are colors; "
            "remaining variables are AP sum states\n"
        )
        for progression in progressions:
            difference = progression[1] - progression[0]
            state = state_variable[(progression[0], difference)]
            positive = " ".join(
                [*(f"+1 x{position}" for position in progression), f"-1 x{state}"]
            )
            negative = " ".join(
                [*(f"-1 x{position}" for position in progression), f"+1 x{state}"]
            )
            stream.write(f"{positive} >= {lower};\n")
            stream.write(f"{negative} >= {-lower};\n")
        for first_state, second_state, first, last in overlap_links:
            stream.write(
                f"+1 x{first_state} -1 x{second_state} "
                f"-1 x{first} +1 x{last} >= 0;\n"
            )
            stream.write(
                f"-1 x{first_state} +1 x{second_state} "
                f"+1 x{first} -1 x{last} >= 0;\n"
            )
        if fix_first and n:
            stream.write("+1 x1 >= 1;\n")

    return {
        "path": str(path),
        "nvars": nvars,
        "nconstraints": nconstraints,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "n": n,
        "k": k,
        "ell": ell,
        "num_aps": len(progressions),
        "overlap_links": len(overlap_links),
        "fix_first": fix_first,
        "encoding": "AP-state equations with explicit overlap links",
    }


def brute_force_avoider(n: int, k: int, ell: int = 2) -> Coloring | None:
    """Return an avoider by exhaustive enumeration; intended for small tests."""
    for coloring in itertools.product((-1, 1), repeat=n):
        if verify_coloring(coloring, k, ell)["avoids"]:
            return coloring
    return None


def prime_lower_bound_witness(prime: int) -> Coloring:
    """Construct an avoider of length p(p-1)+1 for an odd prime p.

    Start with the p-periodic coloring whose positive residues are
    1,...,(p+1)/2.  Among the p entries congruent to 1, flip the final
    (p-1)/2 entries.  Every p-AP with difference below p meets each residue
    exactly once, and the sole p-AP of difference p is balanced by the flips.
    """
    if prime < 3 or prime % 2 == 0 or any(
        prime % divisor == 0
        for divisor in range(3, int(prime**0.5) + 1, 2)
    ):
        raise ValueError("prime must be an odd prime")

    midpoint = (prime + 1) // 2
    n = prime * (prime - 1) + 1
    coloring: list[int] = []
    for position in range(1, n + 1):
        residue = (position - 1) % prime + 1
        value = 1 if residue <= midpoint else -1
        if residue == 1 and (position - 1) // prime >= midpoint:
            value = -1
        coloring.append(value)
    return tuple(coloring)


def command_verify(args: argparse.Namespace) -> int:
    result = verify_coloring(parse_coloring(args.witness), args.k, args.ell)
    print(json.dumps(result, indent=2))
    return 0 if result["avoids"] else 1


def command_generate(args: argparse.Namespace) -> int:
    clauses, nvars = build_cnf(
        args.n,
        args.k,
        args.ell,
        fix_first=args.fix_first,
        encoding=args.encoding,
        canonical_reversal=args.canonical_reversal,
    )
    manifest = write_dimacs(
        args.output,
        clauses,
        nvars,
        comments=(
            "Erdos Problem 176 avoidance instance",
            f"N={args.n} k={args.k} ell={args.ell}",
            "x_i=true means f(i)=+1",
                f"encoding: {args.encoding}",
            f"global color-swap break x_1=+1: {args.fix_first}",
                f"full complement/reversal canonicalization: {args.canonical_reversal}",
        ),
    )
    manifest.update(
        {
            "n": args.n,
            "k": args.k,
            "ell": args.ell,
            "num_aps": num_aps(args.n, args.k),
            "fix_first": args.fix_first,
            "canonical_reversal": args.canonical_reversal,
            "encoding": args.encoding,
        }
    )
    print(json.dumps(manifest, indent=2))
    return 0


def command_generate_opb(args: argparse.Namespace) -> int:
    manifest = write_opb(
        args.output,
        args.n,
        args.k,
        args.ell,
        fix_first=args.fix_first,
    )
    print(json.dumps(manifest, indent=2))
    return 0


def command_generate_state_opb(args: argparse.Namespace) -> int:
    manifest = write_state_opb(
        args.output,
        args.n,
        args.k,
        args.ell,
        fix_first=args.fix_first,
    )
    print(json.dumps(manifest, indent=2))
    return 0


def command_prime_witness(args: argparse.Namespace) -> int:
    coloring = prime_lower_bound_witness(args.prime)
    text = "".join("+" if value == 1 else "-" for value in coloring)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"# p={args.prime}, N={len(coloring)}, ell=2\n{text}\n",
        encoding="ascii",
    )
    result = verify_coloring(coloring, args.prime, 2)
    result["path"] = str(args.output)
    result["sha256"] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps(result, indent=2))
    return 0 if result["avoids"] else 1


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="verify a +/- witness")
    verify.add_argument("witness", type=Path)
    verify.add_argument("--k", type=int, required=True)
    verify.add_argument("--ell", type=int, default=2)
    verify.set_defaults(func=command_verify)

    generate = subparsers.add_parser("generate", help="generate a DIMACS CNF")
    generate.add_argument("--n", type=int, required=True)
    generate.add_argument("--k", type=int, required=True)
    generate.add_argument("--ell", type=int, default=2)
    generate.add_argument("--fix-first", action="store_true")
    generate.add_argument(
        "--canonical-reversal",
        action="store_true",
        help="with --fix-first, choose one representative under reversal",
    )
    generate.add_argument(
        "--encoding",
        choices=("threshold", "totalizer"),
        default="threshold",
    )
    generate.add_argument("--output", type=Path, required=True)
    generate.set_defaults(func=command_generate)

    generate_opb = subparsers.add_parser(
        "generate-opb", help="generate a direct pseudo-Boolean instance"
    )
    generate_opb.add_argument("--n", type=int, required=True)
    generate_opb.add_argument("--k", type=int, required=True)
    generate_opb.add_argument("--ell", type=int, default=2)
    generate_opb.add_argument("--fix-first", action="store_true")
    generate_opb.add_argument("--output", type=Path, required=True)
    generate_opb.set_defaults(func=command_generate_opb)

    generate_state_opb = subparsers.add_parser(
        "generate-state-opb",
        help="generate an AP-state pseudo-Boolean instance",
    )
    generate_state_opb.add_argument("--n", type=int, required=True)
    generate_state_opb.add_argument("--k", type=int, required=True)
    generate_state_opb.add_argument("--ell", type=int, default=2)
    generate_state_opb.add_argument("--fix-first", action="store_true")
    generate_state_opb.add_argument("--output", type=Path, required=True)
    generate_state_opb.set_defaults(func=command_generate_state_opb)

    prime_witness = subparsers.add_parser(
        "prime-witness", help="construct the p(p-1)+1 lower-bound witness"
    )
    prime_witness.add_argument("--prime", type=int, required=True)
    prime_witness.add_argument("--output", type=Path, required=True)
    prime_witness.set_defaults(func=command_prime_witness)

    return parser


def main() -> int:
    args = make_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
