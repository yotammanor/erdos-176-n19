#!/usr/bin/env python3
"""Verify the retained DRAT proofs from a cube campaign."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import tempfile
import time
from pathlib import Path

import adaptive_cube_tree
from cube_campaign import parse_indices, sha256, write_cube_cnf


def completed_indices(path: Path) -> set[int]:
    latest: dict[int, str] = {}
    if not path.exists():
        return set()
    for line in path.read_text(encoding="utf-8").splitlines():
        verdict = json.loads(line)
        latest[int(verdict["cube"])] = str(verdict["status"])
    return {index for index, status in latest.items() if status == "VERIFIED"}


def verify_one(
    *,
    index: int,
    literals: tuple[int, ...],
    base: Path,
    proof: Path,
    checker: Path,
    checker_args: tuple[str, ...],
    checker_log: Path,
    temporary_dir: Path,
    timeout: float | None,
) -> dict[str, object]:
    cube_cnf = temporary_dir / f"cube_{index}.cnf"
    started = time.monotonic()
    checker_rc: int | None = None
    if not proof.exists():
        status = "MISSING"
        output = "proof file is absent"
    else:
        write_cube_cnf(base, cube_cnf, literals)
        try:
            checked = subprocess.run(
                (
                    str(checker),
                    *checker_args,
                    str(cube_cnf),
                    str(proof),
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
                text=True,
            )
            checker_rc = checked.returncode
            output = checked.stdout
            status = (
                "VERIFIED"
                if checker_rc in (0, 20) and "s VERIFIED" in output
                else "CHECK_FAILED"
            )
        except subprocess.TimeoutExpired as error:
            status = "CHECK_TIMEOUT"
            output = (
                error.stdout.decode(errors="replace")
                if isinstance(error.stdout, bytes)
                else (error.stdout or "")
            )
    checker_log.write_text(output, encoding="utf-8")
    return {
        "cube": index,
        "status": status,
        "checker_rc": checker_rc,
        "wall_seconds": round(time.monotonic() - started, 3),
        "proof_bytes": proof.stat().st_size if proof.exists() else None,
        "proof_sha256": sha256(proof) if proof.exists() else None,
        "checker_log": str(checker_log),
        "checker_log_bytes": checker_log.stat().st_size,
        "checker_log_sha256": sha256(checker_log),
        "checker_output_tail": output[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--indices", type=str)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--recheck",
        action="store_true",
        help="check requested proofs again even if a verified record exists",
    )
    parser.add_argument(
        "--checker-arg",
        action="append",
        default=[],
        help="argument appended to the checker command (repeatable)",
    )
    args = parser.parse_args()
    if args.jobs < 1:
        raise ValueError("--jobs must be positive")

    campaign = args.campaign.resolve()
    checker = args.checker.resolve()
    manifest = json.loads((campaign / "manifest.json").read_text(encoding="utf-8"))
    base = Path(manifest["base"])
    if not base.is_file() or sha256(base) != manifest.get("base_sha256"):
        raise ValueError("base CNF is missing or its SHA-256 differs")
    if (
        "checker_sha256" in manifest
        and (
            not checker.is_file()
            or sha256(checker) != manifest["checker_sha256"]
        )
    ):
        raise ValueError("checker binary is missing or its SHA-256 differs")
    schema = manifest.get("schema")
    if schema == "erdos176.cube-campaign.v1":
        split_variables = tuple(
            int(item) for item in manifest["split_variables"]
        )
        cube_map = {
            index: tuple(
                variable if (index >> bit) & 1 else -variable
                for bit, variable in enumerate(split_variables)
            )
            for index in range(int(manifest["cube_count"]))
        }
    elif schema == "erdos176.adaptive-cube-campaign.v1":
        tree_path = Path(str(manifest["tree"]))
        if sha256(tree_path) != manifest.get("tree_sha256"):
            raise ValueError("adaptive tree SHA-256 mismatch")
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        adaptive_cube_tree.audit_tree(tree, nvars=int(manifest["nvars"]))
        cube_map = adaptive_cube_tree.leaf_cubes(tree)
        if len(cube_map) != int(manifest["cube_count"]):
            raise ValueError("adaptive tree leaf count differs from manifest")
    else:
        raise ValueError(f"unsupported campaign schema: {schema!r}")
    proof_suffix = str(manifest.get("proof_suffix", ".drat"))
    requested = parse_indices(args.indices, int(manifest["cube_count"]))
    verdict_path = campaign / "proof_verdicts.jsonl"
    checker_log_dir = campaign / "checker-logs"
    checker_log_dir.mkdir(parents=True, exist_ok=True)
    pending = (
        requested
        if args.recheck
        else [
            index
            for index in requested
            if index not in completed_indices(verdict_path)
        ]
    )

    failed = False
    with tempfile.TemporaryDirectory(
        prefix="verify-campaign-", dir=campaign
    ) as temporary:
        temporary_dir = Path(temporary)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.jobs
        ) as executor:
            futures = {
                executor.submit(
                    verify_one,
                    index=index,
                    literals=cube_map[index],
                    base=base,
                    proof=(
                        campaign
                        / "drat"
                        / f"cube_{index}{proof_suffix}"
                    ),
                    checker=checker,
                    checker_args=tuple(args.checker_arg),
                    checker_log=(
                        checker_log_dir / f"cube_{index}.checker.log"
                    ),
                    temporary_dir=temporary_dir,
                    timeout=args.timeout,
                ): index
                for index in pending
            }
            for future in concurrent.futures.as_completed(futures):
                verdict = future.result()
                with verdict_path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(verdict, sort_keys=True) + "\n"
                    )
                print(json.dumps(verdict, sort_keys=True), flush=True)
                if verdict["status"] != "VERIFIED":
                    failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
