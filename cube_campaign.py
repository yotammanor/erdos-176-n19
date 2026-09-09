#!/usr/bin/env python3
"""Run a resumable, proof-producing cube-and-conquer campaign."""

from __future__ import annotations

import argparse
import concurrent.futures
import errno
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterable, Sequence

import adaptive_cube_tree
import nk2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_header(path: Path) -> tuple[int, int]:
    with path.open("r", encoding="ascii") as stream:
        for line in stream:
            if line.startswith("p cnf "):
                _, _, variables, clauses = line.split()
                return int(variables), int(clauses)
    raise ValueError(f"no DIMACS header in {path}")


def rank_original_variables(path: Path, n_original: int) -> list[tuple[int, int]]:
    counts = [0] * (n_original + 1)
    with path.open("r", encoding="ascii") as stream:
        for line in stream:
            if not line or line[0] in "cp":
                continue
            for token in line.split():
                literal = int(token)
                if 0 < abs(literal) <= n_original:
                    counts[abs(literal)] += 1
    return sorted(
        ((count, variable) for variable, count in enumerate(counts) if variable > 1),
        key=lambda item: (-item[0], item[1]),
    )


def cube_literals(split_variables: Sequence[int], index: int) -> tuple[int, ...]:
    return tuple(
        variable if (index >> bit) & 1 else -variable
        for bit, variable in enumerate(split_variables)
    )


def write_cube_cnf(base: Path, output: Path, literals: Sequence[int]) -> None:
    _, nclauses = read_header(base)
    found_header = False
    with base.open("r", encoding="ascii") as source, output.open(
        "w", encoding="ascii", newline="\n"
    ) as target:
        for line in source:
            if line.startswith("p cnf "):
                _, _, nvars, _ = line.split()
                target.write(f"p cnf {nvars} {nclauses + len(literals)}\n")
                found_header = True
            else:
                target.write(line)
        if not found_header:
            raise ValueError(f"no DIMACS header in {base}")
        for literal in literals:
            target.write(f"{literal} 0\n")


def parse_indices(specification: str | None, count: int) -> list[int]:
    if specification is None:
        return list(range(count))
    selected: set[int] = set()
    for part in specification.split(","):
        if ":" in part:
            start_text, stop_text = part.split(":", 1)
            start = int(start_text) if start_text else 0
            stop = int(stop_text) if stop_text else count
            selected.update(range(start, stop))
        else:
            selected.add(int(part))
    invalid = sorted(index for index in selected if not 0 <= index < count)
    if invalid:
        raise ValueError(f"cube indices out of range: {invalid}")
    return sorted(selected)


def previous_completed(
    *paths: Path,
    defer_check: bool,
) -> set[int]:
    """Return cubes whose latest solver/checker state is complete."""
    latest: dict[int, str] = {}
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            verdict = json.loads(line)
            latest[int(verdict["cube"])] = str(verdict["status"])
    accepted = {"VERIFIED", "SAT"}
    if defer_check:
        accepted.add("UNVERIFIED")
    return {cube for cube, status in latest.items() if status in accepted}


def publish_artifact(staged: Path, destination: Path) -> None:
    """Publish a staged artifact atomically when both paths share a device."""
    try:
        os.replace(staged, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        copying = destination.with_name(
            f".{destination.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            shutil.copy2(staged, copying)
            os.replace(copying, destination)
            staged.unlink()
        finally:
            try:
                copying.unlink()
            except FileNotFoundError:
                pass


def run_cube(
    *,
    index: int,
    literals: Sequence[int],
    base: Path,
    solver: Path,
    checker: Path,
    proof_dir: Path,
    log_dir: Path,
    temporary_dir: Path,
    timeout: float | None,
    checker_timeout: float | None,
    defer_check: bool,
    solver_args: Sequence[str],
    proof_suffix: str,
    n_original: int,
    k: int,
    retain_partial_proofs: bool = True,
) -> dict[str, object]:
    literals = tuple(literals)
    cube_cnf = temporary_dir / f"cube_{index}.cnf"
    proof = proof_dir / f"cube_{index}{proof_suffix}"
    staged_proof = temporary_dir / f"cube_{index}{proof_suffix}"
    partial_proof = proof.with_name(f"{proof.stem}.partial{proof.suffix}")
    solver_log = log_dir / f"cube_{index}.solver.log"
    checker_log = log_dir / f"cube_{index}.checker.log"
    write_cube_cnf(base, cube_cnf, literals)

    started = time.monotonic()
    status = "ERROR"
    solver_rc: int | None = None
    checker_rc: int | None = None
    missing_model_variables: list[int] = []
    phase = "solver"
    try:
        with solver_log.open("w", encoding="utf-8") as output:
            solved = subprocess.run(
                (
                    str(solver),
                    *solver_args,
                    str(cube_cnf),
                    str(staged_proof),
                ),
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
                text=True,
            )
        solver_rc = solved.returncode
        if solver_rc == 20:
            if defer_check:
                status = "UNVERIFIED"
            else:
                phase = "checker"
                with checker_log.open("w", encoding="utf-8") as output:
                    checked = subprocess.run(
                        (str(checker), str(cube_cnf), str(staged_proof)),
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        timeout=checker_timeout,
                        check=False,
                        text=True,
                    )
                checker_rc = checked.returncode
                checker_text = checker_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                status = (
                    "VERIFIED"
                    if checker_rc in (0, 20) and "s VERIFIED" in checker_text
                    else "CHECK_FAILED"
                )
            if not staged_proof.is_file():
                status = "MISSING_PROOF"
            else:
                publish_artifact(staged_proof, proof)
        elif solver_rc == 10:
            model_text = solver_log.read_text(encoding="utf-8", errors="replace")
            values: dict[int, bool] = {}
            for line in model_text.splitlines():
                if line.startswith("v "):
                    for token in line[2:].split():
                        literal = int(token)
                        if literal:
                            values[abs(literal)] = literal > 0
            missing_model_variables = [
                variable
                for variable in range(1, n_original + 1)
                if variable not in values
            ]
            if missing_model_variables:
                status = "BAD_MODEL"
            else:
                coloring = tuple(
                    1 if values[variable] else -1
                    for variable in range(1, n_original + 1)
                )
                status = (
                    "SAT"
                    if nk2.verify_coloring(coloring, k, 2)["avoids"]
                    else "BAD_MODEL"
                )
        elif solver_rc == 0:
            status = "UNKNOWN"
            if retain_partial_proofs and staged_proof.exists():
                publish_artifact(staged_proof, partial_proof)
    except subprocess.TimeoutExpired:
        status = "TIMEOUT" if phase == "solver" else "CHECK_TIMEOUT"
        if staged_proof.exists() and (
            phase != "solver" or retain_partial_proofs
        ):
            publish_artifact(
                staged_proof,
                partial_proof if phase == "solver" else proof,
            )
    finally:
        for temporary_path in (cube_cnf, staged_proof):
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    elapsed = time.monotonic() - started
    return {
        "cube": index,
        "literals": literals,
        "status": status,
        "solver_rc": solver_rc,
        "checker_rc": checker_rc,
        "solver": str(solver),
        "solver_sha256": sha256(solver),
        "solver_args": list(solver_args),
        "missing_model_variables": missing_model_variables[:20],
        "wall_seconds": round(elapsed, 3),
        "proof_bytes": proof.stat().st_size if proof.exists() else None,
        "proof_sha256": (
            sha256(proof)
            if proof.exists()
            and status in ("VERIFIED", "UNVERIFIED", "CHECK_TIMEOUT", "CHECK_FAILED")
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--n-original", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--split", type=str)
    parser.add_argument(
        "--tree",
        type=Path,
        help="audited adaptive tree; leaf IDs replace fixed-depth cube indices",
    )
    parser.add_argument("--indices", type=str)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=float)
    parser.add_argument(
        "--solver-arg",
        action="append",
        help="solver option placed before the CNF and proof paths (repeatable)",
    )
    parser.add_argument("--proof-suffix", default=".drat")
    parser.add_argument("--checker-timeout", type=float)
    parser.add_argument(
        "--defer-check",
        action="store_true",
        help="retain complete UNSAT proofs for a separate verification pass",
    )
    parser.add_argument(
        "--discard-partial-proofs",
        action="store_true",
        help="delete incomplete solver proofs after UNKNOWN or timeout",
    )
    args = parser.parse_args()
    if not args.proof_suffix.startswith("."):
        raise ValueError("proof suffix must begin with a dot")
    solver_args = tuple(args.solver_arg or ("--unsat",))

    base = args.base.resolve()
    solver = args.solver.resolve()
    checker = args.checker.resolve()
    campaign = args.campaign.resolve()
    for description, path in (
        ("base CNF", base),
        ("solver", solver),
        ("checker", checker),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{description} is missing: {path}")
    proof_dir = campaign / "drat"
    log_dir = campaign / "logs"
    proof_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    nvars, nclauses = read_header(base)
    if args.tree:
        if args.split:
            raise ValueError("--split and --tree are mutually exclusive")
        tree_path = args.tree.resolve()
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        adaptive_cube_tree.audit_tree(tree, nvars=nvars)
        cube_map = adaptive_cube_tree.leaf_cubes(tree)
        split_variables: tuple[int, ...] = ()
        campaign_kind = "adaptive"
    else:
        if args.split:
            split_variables = tuple(int(item) for item in args.split.split(","))
        else:
            ranking = rank_original_variables(base, args.n_original)
            split_variables = tuple(
                variable for _, variable in ranking[: args.depth]
            )
        if len(set(split_variables)) != len(split_variables):
            raise ValueError("split variables must be distinct")
        if any(
            not 1 <= variable <= args.n_original
            for variable in split_variables
        ):
            raise ValueError("split variables must be original coloring variables")
        cube_map = {
            index: cube_literals(split_variables, index)
            for index in range(1 << len(split_variables))
        }
        campaign_kind = "fixed"

    cube_count = len(cube_map)
    requested = parse_indices(args.indices, cube_count)
    verdict_path = campaign / "verdicts.jsonl"
    completed = previous_completed(
        verdict_path,
        campaign / "proof_verdicts.jsonl",
        defer_check=args.defer_check,
    )
    pending = [index for index in requested if index not in completed]

    manifest = {
        "schema": (
            "erdos176.adaptive-cube-campaign.v1"
            if campaign_kind == "adaptive"
            else "erdos176.cube-campaign.v1"
        ),
        "base": str(base),
        "base_sha256": sha256(base),
        "solver": str(solver),
        "solver_sha256": sha256(solver),
        "checker": str(checker),
        "checker_sha256": sha256(checker),
        "nvars": nvars,
        "nclauses": nclauses,
        "n_original": args.n_original,
        "k": args.k,
        "ell": 2,
        "cube_count": cube_count,
    }
    if campaign_kind == "adaptive":
        manifest.update(
            {
                "tree": str(tree_path),
                "tree_sha256": sha256(tree_path),
                "cube_convention": "leaf ID and literals from audited tree",
            }
        )
    else:
        manifest.update(
            {
                "split_variables": list(split_variables),
                "cube_convention": "bit j set -> positive split_variables[j]",
            }
        )
    if solver_args != ("--unsat",):
        manifest["solver_args"] = list(solver_args)
    if args.proof_suffix != ".drat":
        manifest["proof_suffix"] = args.proof_suffix
    manifest_path = campaign / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise ValueError("existing campaign manifest differs")
    else:
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    print(
        f"kind={campaign_kind} split={list(split_variables)} cubes={cube_count} "
        f"requested={len(requested)} pending={len(pending)} jobs={args.jobs}",
        flush=True,
    )
    if not pending:
        return 0

    write_lock = threading.Lock()
    with tempfile.TemporaryDirectory(prefix="cube-campaign-") as temporary:
        temporary_dir = Path(temporary)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    run_cube,
                    index=index,
                    literals=cube_map[index],
                    base=base,
                    solver=solver,
                    checker=checker,
                    proof_dir=proof_dir,
                    log_dir=log_dir,
                    temporary_dir=temporary_dir,
                    timeout=args.timeout,
                    checker_timeout=args.checker_timeout,
                    defer_check=args.defer_check,
                    solver_args=solver_args,
                    proof_suffix=args.proof_suffix,
                    n_original=args.n_original,
                    k=args.k,
                    retain_partial_proofs=not args.discard_partial_proofs,
                ): index
                for index in pending
            }
            for future in concurrent.futures.as_completed(futures):
                verdict = future.result()
                line = json.dumps(verdict, sort_keys=True)
                with write_lock:
                    with verdict_path.open("a", encoding="utf-8") as output:
                        output.write(line + "\n")
                    print(line, flush=True)
                if verdict["status"] in ("SAT", "BAD_MODEL"):
                    for other in futures:
                        other.cancel()
                    return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
