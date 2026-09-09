#!/usr/bin/env python3
"""Retry one adaptive-campaign leaf with recorded per-attempt solver options."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import adaptive_cube_tree
from cube_campaign import run_cube, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--cube", type=int, required=True)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--checker-timeout", type=float)
    parser.add_argument(
        "--solver",
        type=Path,
        help="solver override for this attempt; its hash is recorded",
    )
    parser.add_argument("--solver-arg", action="append")
    parser.add_argument("--defer-check", action="store_true")
    args = parser.parse_args()

    campaign = args.campaign.resolve()
    manifest = json.loads((campaign / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "erdos176.adaptive-cube-campaign.v1":
        raise ValueError("retry requires an adaptive campaign")
    base = Path(str(manifest["base"]))
    manifest_solver = Path(str(manifest["solver"]))
    checker = Path(str(manifest["checker"]))
    tree_path = Path(str(manifest["tree"]))
    for path, digest, description in (
        (base, manifest["base_sha256"], "base CNF"),
        (manifest_solver, manifest["solver_sha256"], "solver"),
        (checker, manifest["checker_sha256"], "checker"),
        (tree_path, manifest["tree_sha256"], "adaptive tree"),
    ):
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"{description} is absent or changed")
    solver = args.solver.resolve() if args.solver else manifest_solver
    if not solver.is_file():
        raise FileNotFoundError(f"solver override is missing: {solver}")

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    adaptive_cube_tree.audit_tree(tree, nvars=int(manifest["nvars"]))
    cube_map = adaptive_cube_tree.leaf_cubes(tree)
    if args.cube not in cube_map:
        raise ValueError(f"cube {args.cube} is outside the adaptive tree")
    solver_args = tuple(
        args.solver_arg
        or manifest.get("solver_args")
        or ("--unsat",)
    )

    proof_dir = campaign / "drat"
    log_dir = campaign / "logs"
    with tempfile.TemporaryDirectory(
        prefix="retry-cube-",
        dir=campaign,
    ) as temporary:
        verdict = run_cube(
            index=args.cube,
            literals=cube_map[args.cube],
            base=base,
            solver=solver,
            checker=checker,
            proof_dir=proof_dir,
            log_dir=log_dir,
            temporary_dir=Path(temporary),
            timeout=args.timeout,
            checker_timeout=args.checker_timeout,
            defer_check=args.defer_check,
            solver_args=solver_args,
            proof_suffix=str(manifest.get("proof_suffix", ".drat")),
            n_original=int(manifest["n_original"]),
            k=int(manifest["k"]),
        )

    with (campaign / "verdicts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(verdict, sort_keys=True) + "\n")
    print(json.dumps(verdict, sort_keys=True))
    return 0 if verdict["status"] in ("VERIFIED", "UNVERIFIED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
