#!/usr/bin/env python3
"""Create a fail-closed release manifest from a verified proof job."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nk2


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": display_path(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-status", type=Path, required=True)
    parser.add_argument(
        "--witness",
        type=Path,
        default=Path("witnesses/k19_N343.txt"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("certificate_manifest.json"),
    )
    args = parser.parse_args()

    status_path = args.job_status.resolve()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("state") != "VERIFIED_UNSAT":
        raise ValueError(
            f"proof job is not VERIFIED_UNSAT: {status.get('state')!r}"
        )
    if status.get("checker_rc") != 0:
        raise ValueError("proof job checker did not return zero")

    label = str(status["label"])
    job_dir = status_path.parent
    solver_log = job_dir / f"{label}.solver.log"
    checker_log = job_dir / f"{label}.checker.log"
    checker_output = checker_log.read_text(encoding="utf-8", errors="replace")
    expected_marker = (
        "s VERIFIED"
        if status["backend"] in ("kissat", "cadical")
        else "s VERIFIED UNSATISFIABLE"
    )
    if expected_marker not in checker_output:
        raise ValueError("checker log lacks the required verification marker")

    witness_path = args.witness.resolve()
    coloring = nk2.parse_coloring(witness_path)
    witness_verdict = nk2.verify_coloring(coloring, 19, 2)
    if len(coloring) != 343 or not witness_verdict["avoids"]:
        raise ValueError("lower-bound witness did not pass verification")

    files = {
        "instance": artifact(Path(status["instance"])),
        "proof": artifact(Path(status["proof"])),
        "solver_log": artifact(solver_log),
        "checker_log": artifact(checker_log),
        "proof_job_status": artifact(status_path),
        "lower_bound_witness": artifact(witness_path),
    }
    if files["instance"]["sha256"] != status["instance_sha256"]:
        raise ValueError("instance changed after the proof job")
    if files["proof"]["sha256"] != status["proof_sha256"]:
        raise ValueError("proof changed after verification")

    manifest = {
        "schema": "erdos176.certificate-release.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim": {
            "problem": "Erdos Problem 176",
            "k": 19,
            "ell": 2,
            "value": 344,
            "lower_bound": {
                "witness_length": 343,
                "progressions_checked": witness_verdict["num_aps"],
                "maximum_discrepancy": witness_verdict["max_abs_sum"],
            },
            "upper_bound": {
                "instance_n": 344,
                "proof_backend": status["backend"],
                "checker_rc": status["checker_rc"],
                "checker_marker": expected_marker,
            },
        },
        "commands": {
            "solver": status["solver_command"],
            "checker": status["checker_command"],
        },
        "tools": {
            "solver": {
                "path": status.get("solver", status["solver_command"][0]),
                "sha256": status.get("solver_sha256"),
            },
            "checker": {
                "path": status.get("checker", status["checker_command"][0]),
                "sha256": status.get("checker_sha256"),
            },
        },
        "files": files,
    }

    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
