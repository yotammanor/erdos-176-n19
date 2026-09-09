#!/usr/bin/env python3
"""Run one persistent proof-producing solver job and verify its certificate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_status(path: Path, status: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_logged(command: Sequence[str], log: Path) -> int:
    with log.open("w", encoding="utf-8") as output:
        completed = subprocess.run(
            tuple(command),
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("kissat", "cadical", "roundingsat", "roundingsat-soplex"),
        required=True,
    )
    parser.add_argument("--label", required=True)
    parser.add_argument("--seconds", type=int, default=21_600)
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("proofs/portfolio"))
    parser.add_argument(
        "--solver-arg",
        action="append",
        default=[],
        help="extra solver option placed before the instance (repeatable)",
    )
    args = parser.parse_args()

    instance = args.instance.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / f"{args.label}.status.json"
    solver_log = output_dir / f"{args.label}.solver.log"
    checker_log = output_dir / f"{args.label}.checker.log"
    proof_suffix = ".drat" if args.backend in ("kissat", "cadical") else ".pbp"
    proof = output_dir / f"{args.label}{proof_suffix}"
    for path in (status_path, solver_log, checker_log, proof):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
    if not instance.is_file():
        raise FileNotFoundError(instance)

    if args.backend == "kissat":
        solver = (ROOT / "tools/bin/kissat").resolve()
        checker = (ROOT / "tools/bin/drat-trim").resolve()
        solver_command = (
            str(solver),
            *args.solver_arg,
            "--unsat",
            f"--time={args.seconds}",
            str(instance),
            str(proof),
        )
        checker_command = (str(checker), str(instance), str(proof))
    elif args.backend == "cadical":
        solver = (ROOT / "tools/bin/cadical").resolve()
        checker = (ROOT / "tools/bin/drat-trim").resolve()
        solver_command = (
            str(solver),
            *args.solver_arg,
            "--unsat",
            "-t",
            str(args.seconds),
            str(instance),
            str(proof),
        )
        checker_command = (str(checker), str(instance), str(proof))
    else:
        solver_name = (
            "roundingsat-soplex"
            if args.backend == "roundingsat-soplex"
            else "roundingsat"
        )
        solver = (ROOT / "tools/bin" / solver_name).resolve()
        checker = (ROOT / "tools/veripb/bin/veripb").resolve()
        solver_command = (
            str(solver),
            *args.solver_arg,
            f"--time-limit={args.seconds}",
            "--print-sol=1",
            f"--proof-log={proof}",
            str(instance),
        )
        checker_command = (str(checker), str(instance), str(proof))

    started = time.monotonic()
    status: dict[str, Any] = {
        "schema": "erdos176.proof-job.v1",
        "label": args.label,
        "backend": args.backend,
        "state": "SOLVING",
        "started_at": utc_now(),
        "cursor_sandbox": os.environ.get("CURSOR_SANDBOX"),
        "instance": str(instance),
        "instance_bytes": instance.stat().st_size,
        "instance_sha256": sha256(instance),
        "proof": str(proof),
        "solver": str(solver),
        "solver_sha256": sha256(solver),
        "checker": str(checker),
        "checker_sha256": sha256(checker),
        "solver_command": list(solver_command),
        "checker_command": list(checker_command),
    }
    write_status(status_path, status)

    try:
        solver_rc = run_logged(solver_command, solver_log)
        solver_output = solver_log.read_text(encoding="utf-8", errors="replace")
        status.update(
            solver_rc=solver_rc,
            solver_finished_at=utc_now(),
            solver_wall_seconds=round(time.monotonic() - started, 3),
            proof_bytes=proof.stat().st_size if proof.exists() else None,
        )
        if args.backend in ("kissat", "cadical"):
            unsat = solver_rc == 20 and "s UNSATISFIABLE" in solver_output
            sat = solver_rc == 10 and "s SATISFIABLE" in solver_output
        else:
            unsat = solver_rc == 0 and "s UNSATISFIABLE" in solver_output
            sat = solver_rc == 0 and "s SATISFIABLE" in solver_output

        if sat:
            status["state"] = "SAT"
            write_status(status_path, status)
            return 10
        if not unsat:
            status["state"] = "UNKNOWN"
            write_status(status_path, status)
            return solver_rc or 2

        status["state"] = "CHECKING"
        write_status(status_path, status)
        checker_rc = run_logged(checker_command, checker_log)
        checker_output = checker_log.read_text(encoding="utf-8", errors="replace")
        verified_marker = (
            "s VERIFIED"
            if args.backend in ("kissat", "cadical")
            else "s VERIFIED UNSATISFIABLE"
        )
        verified = checker_rc == 0 and verified_marker in checker_output
        status.update(
            checker_rc=checker_rc,
            checker_finished_at=utc_now(),
            wall_seconds=round(time.monotonic() - started, 3),
            proof_bytes=proof.stat().st_size,
            proof_sha256=sha256(proof) if verified else None,
            state="VERIFIED_UNSAT" if verified else "CHECK_FAILED",
        )
        write_status(status_path, status)
        return 0 if verified else 1
    except BaseException as error:
        status.update(
            state="ERROR",
            failed_at=utc_now(),
            error=f"{type(error).__name__}: {error}",
            wall_seconds=round(time.monotonic() - started, 3),
        )
        write_status(status_path, status)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
