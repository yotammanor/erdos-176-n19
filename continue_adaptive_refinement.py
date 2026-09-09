#!/usr/bin/env python3
"""Repeatedly refine queued unresolved leaves of an adaptive campaign."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import adaptive_cube_tree
from cube_campaign import read_header, write_cube_cnf


CLOSED = {"UNVERIFIED", "VERIFIED"}


def latest_verdicts(path: Path) -> dict[int, dict[str, object]]:
    latest: dict[int, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        verdict = json.loads(line)
        latest[int(verdict["cube"])] = verdict
    return latest


def run_checked(command: list[str]) -> None:
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise RuntimeError(
            f"command returned {completed.returncode}: {command!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument(
        "--leaf",
        type=int,
        action="append",
        required=True,
        help="unresolved leaf ID in the initial tree; repeat as needed",
    )
    parser.add_argument("--prefix", required=True)
    parser.add_argument(
        "--start-round",
        type=int,
        default=1,
        help="first output round number (useful when resuming a prior run)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=10,
        help="last output round number",
    )
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument(
        "--cuber-max-variable",
        type=int,
        help="restrict look-ahead splits to DIMACS variables at most this ID",
    )
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--solver-seconds", type=int, default=120)
    parser.add_argument("--wrapper-seconds", type=int, default=130)
    args = parser.parse_args()
    if args.start_round < 1:
        raise ValueError("--start-round must be positive")
    if args.rounds < args.start_round:
        raise ValueError("--rounds must be at least --start-round")

    root = Path(__file__).resolve().parent
    base = args.base.resolve()
    nvars, _ = read_header(base)
    if (
        args.cuber_max_variable is not None
        and not 1 <= args.cuber_max_variable <= nvars
    ):
        raise ValueError("--cuber-max-variable is outside the CNF variable range")
    tree_path = args.tree.resolve()
    initial_tree = json.loads(tree_path.read_text(encoding="utf-8"))
    adaptive_cube_tree.audit_tree(initial_tree, nvars=nvars)
    initial_leaves = adaptive_cube_tree.leaf_cubes(initial_tree)
    if len(args.leaf) != len(set(args.leaf)):
        raise ValueError("duplicate initial unresolved leaf")
    absent = [leaf_id for leaf_id in args.leaf if leaf_id not in initial_leaves]
    if absent:
        raise ValueError(f"leaves {absent} are absent from {tree_path}")
    hard_prefixes = [initial_leaves[leaf_id] for leaf_id in args.leaf]

    for round_index in range(args.start_round, args.rounds + 1):
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        before = adaptive_cube_tree.audit_tree(tree, nvars=nvars)
        leaves = adaptive_cube_tree.leaf_cubes(tree)
        target_prefix = hard_prefixes.pop(0)
        matching = [
            leaf_id
            for leaf_id, literals in leaves.items()
            if literals == target_prefix
        ]
        if len(matching) != 1:
            raise ValueError(
                f"unresolved prefix occurs {len(matching)} times in {tree_path}"
            )
        hard_leaf = matching[0]

        with tempfile.TemporaryDirectory(prefix="erdos176-refine-") as directory:
            temporary = Path(directory)
            cubed_base = temporary / "leaf.cnf"
            generated_path = temporary / "cubes.json"
            write_cube_cnf(base, cubed_base, leaves[hard_leaf])
            cuber_command = [
                str((root / "tools/bin/cadical-generate-cubes").resolve()),
                str(cubed_base),
                str(args.depth),
                str(generated_path),
            ]
            if args.cuber_max_variable is not None:
                cuber_command.extend(
                    ["0", str(args.cuber_max_variable)]
                )
            run_checked(cuber_command)
            payload = json.loads(generated_path.read_text(encoding="utf-8"))
            relative_cubes = adaptive_cube_tree.cubes_from_payload(
                payload, nvars=nvars
            )
            refined = adaptive_cube_tree.refine_leaf(
                tree, hard_leaf, relative_cubes
            )

        output_tree = (
            root
            / "proofs/adaptive"
            / f"{args.prefix}-r{round_index}.tree.json"
        )
        if output_tree.exists():
            raise FileExistsError(output_tree)
        output_tree.write_text(
            json.dumps(refined, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        after = adaptive_cube_tree.audit_tree(refined, nvars=nvars)
        inserted = after["leaves"] - before["leaves"] + 1
        first = hard_leaf
        stop = hard_leaf + inserted
        campaign = (
            root / "proofs/adaptive" / f"{args.prefix}-r{round_index}"
        )
        run_checked(
            [
                sys.executable,
                str(root / "cube_campaign.py"),
                "--base",
                str(base),
                "--tree",
                str(output_tree),
                "--solver",
                str((root / "tools/bin/cadical").resolve()),
                "--checker",
                str((root / "tools/bin/drat-trim").resolve()),
                "--campaign",
                str(campaign),
                "--n-original",
                "344",
                "--k",
                "19",
                "--indices",
                f"{first}:{stop}",
                "--jobs",
                str(args.jobs),
                "--timeout",
                str(args.wrapper_seconds),
                "--solver-arg=--unsat",
                "--solver-arg=-t",
                f"--solver-arg={args.solver_seconds}",
                "--defer-check",
            ]
        )
        latest = latest_verdicts(campaign / "verdicts.jsonl")
        unresolved = [
            index
            for index in range(first, stop)
            if latest.get(index, {}).get("status") not in CLOSED
        ]
        refined_leaves = adaptive_cube_tree.leaf_cubes(refined)
        hard_prefixes.extend(refined_leaves[index] for index in unresolved)
        print(
            json.dumps(
                {
                    "round": round_index,
                    "tree": str(output_tree),
                    "leaves": after["leaves"],
                    "maximum_depth": after["maximum_depth"],
                    "inserted_leaves": inserted,
                    "unresolved": unresolved,
                    "queued_unresolved": len(hard_prefixes),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        tree_path = output_tree
        if not hard_prefixes:
            return 0

    raise RuntimeError(
        f"still unresolved after {args.rounds} rounds: "
        f"tree={tree_path}, queued={len(hard_prefixes)}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
