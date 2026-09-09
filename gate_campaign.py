#!/usr/bin/env python3
"""Fail closed unless a fixed or adaptive cube campaign is fully verified."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import adaptive_cube_tree
from cube_campaign import read_header, sha256


def records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args()

    campaign = args.campaign.resolve()
    manifest = json.loads((campaign / "manifest.json").read_text(encoding="utf-8"))
    base = Path(str(manifest["base"]))
    cube_count = int(manifest["cube_count"])
    proof_suffix = str(manifest.get("proof_suffix", ".drat"))

    failures: list[str] = []
    schema = manifest.get("schema")
    split: list[int] = []
    tree_summary: dict[str, int] | None = None
    if schema == "erdos176.cube-campaign.v1":
        split = [int(variable) for variable in manifest["split_variables"]]
        if cube_count != 1 << len(split):
            failures.append("cube_count is not 2^len(split_variables)")
        if len(split) != len(set(split)):
            failures.append("split_variables contains duplicates")
        if any(
            not 1 <= variable <= int(manifest["n_original"])
            for variable in split
        ):
            failures.append("split variable is outside the original variable range")
        partition_argument = (
            "The cubes enumerate every truth assignment to the distinct split "
            "variables, so their disjunction is a tautology. If every base-plus-"
            "cube CNF is UNSAT, the base CNF is UNSAT."
        )
    elif schema == "erdos176.adaptive-cube-campaign.v1":
        tree_path = Path(str(manifest["tree"]))
        if not tree_path.is_file():
            failures.append("adaptive tree is missing")
        elif sha256(tree_path) != manifest.get("tree_sha256"):
            failures.append("adaptive tree SHA-256 mismatch")
        else:
            try:
                tree = json.loads(tree_path.read_text(encoding="utf-8"))
                tree_summary = adaptive_cube_tree.audit_tree(
                    tree,
                    nvars=int(manifest["nvars"]),
                )
                if tree_summary["leaves"] != cube_count:
                    failures.append(
                        "adaptive tree leaf count differs from cube_count"
                    )
                partition_argument = str(tree["partition_argument"])
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                failures.append(f"invalid adaptive tree: {error}")
        if tree_summary is None:
            partition_argument = "Adaptive tree validation failed."
    else:
        failures.append("unsupported manifest schema")
        partition_argument = "No partition argument for unsupported schema."
    if not base.is_file():
        failures.append("base CNF is missing")
    else:
        if sha256(base) != manifest["base_sha256"]:
            failures.append("base CNF SHA-256 mismatch")
        if read_header(base) != (
            int(manifest["nvars"]),
            int(manifest["nclauses"]),
        ):
            failures.append("base CNF header mismatch")
    for tool in ("solver", "checker"):
        path_value = manifest.get(tool)
        digest = manifest.get(f"{tool}_sha256")
        if not isinstance(path_value, str) or not isinstance(digest, str):
            failures.append(f"{tool} provenance is missing from the manifest")
            continue
        path = Path(path_value)
        if not path.is_file():
            failures.append(f"{tool} binary is missing")
        elif sha256(path) != digest:
            failures.append(f"{tool} binary SHA-256 mismatch")

    solvers = manifest.get("solvers")
    solver_inventory: set[tuple[str, str]] | None = None
    if solvers is not None:
        if not isinstance(solvers, list) or not solvers:
            failures.append("solver inventory is invalid")
        else:
            solver_inventory = set()
            for item in solvers:
                if not isinstance(item, dict):
                    failures.append("solver inventory entry is invalid")
                    continue
                path_value = item.get("path")
                digest = item.get("sha256")
                if not isinstance(path_value, str) or not isinstance(digest, str):
                    failures.append("solver inventory entry is invalid")
                    continue
                identity = (path_value, digest)
                if identity in solver_inventory:
                    failures.append("solver inventory contains duplicates")
                    continue
                solver_inventory.add(identity)
                path = Path(path_value)
                if not path.is_file():
                    failures.append(f"solver inventory binary is missing: {path}")
                elif sha256(path) != digest:
                    failures.append(
                        f"solver inventory SHA-256 mismatch: {path}"
                    )

    assembly_value = manifest.get("assembly")
    assembly_digest = manifest.get("assembly_sha256")
    if (assembly_value is None) != (assembly_digest is None):
        failures.append("campaign assembly provenance is incomplete")
    elif isinstance(assembly_value, str) and isinstance(
        assembly_digest, str
    ):
        assembly_path = campaign / "assembly.json"
        recorded_path = Path(assembly_value)
        if recorded_path.resolve() != assembly_path.resolve():
            failures.append("campaign assembly path differs from manifest")
        elif (
            not assembly_path.is_file()
            or sha256(assembly_path) != assembly_digest
        ):
            failures.append("campaign assembly file is missing or changed")
        else:
            try:
                assembly = json.loads(
                    assembly_path.read_text(encoding="utf-8")
                )
                if (
                    assembly.get("schema")
                    != "erdos176.adaptive-campaign-assembly.v1"
                    or assembly.get("complete") is not True
                    or assembly.get("missing_leaves") != []
                    or assembly.get("covered_leaves") != cube_count
                    or assembly.get("tree_sha256")
                    != manifest.get("tree_sha256")
                    or Path(str(assembly.get("destination"))).resolve()
                    != campaign
                ):
                    failures.append("campaign assembly report is inconsistent")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                failures.append(f"invalid campaign assembly report: {error}")
    elif assembly_value is not None:
        failures.append("campaign assembly provenance has invalid types")

    if solver_inventory is not None:
        latest_solver_records: dict[int, dict[str, object]] = {}
        for verdict in records(campaign / "verdicts.jsonl"):
            latest_solver_records[int(verdict["cube"])] = verdict
        out_of_range_solver_records = sorted(
            index
            for index in latest_solver_records
            if not 0 <= index < cube_count
        )
        if out_of_range_solver_records:
            failures.append(
                "solver verdicts contain out-of-range cube IDs "
                f"(first: {out_of_range_solver_records[:20]})"
            )
        missing_solver_provenance: list[int] = []
        used_solvers: set[tuple[str, str]] = set()
        for index in range(cube_count):
            verdict = latest_solver_records.get(index)
            if (
                not verdict
                or verdict.get("status") not in ("UNVERIFIED", "VERIFIED")
                or verdict.get("solver_rc") != 20
                or not isinstance(verdict.get("solver"), str)
                or not isinstance(verdict.get("solver_sha256"), str)
            ):
                missing_solver_provenance.append(index)
                continue
            identity = (
                str(verdict["solver"]),
                str(verdict["solver_sha256"]),
            )
            if identity not in solver_inventory:
                missing_solver_provenance.append(index)
                continue
            used_solvers.add(identity)
        if missing_solver_provenance:
            failures.append(
                f"{len(missing_solver_provenance)} cubes lack valid solver "
                f"provenance (first: {missing_solver_provenance[:20]})"
            )
        if used_solvers != solver_inventory:
            failures.append("solver inventory differs from per-cube provenance")

    latest: dict[int, dict[str, object]] = {}
    for verdict in records(campaign / "proof_verdicts.jsonl"):
        latest[int(verdict["cube"])] = verdict
    out_of_range = sorted(
        index for index in latest if not 0 <= index < cube_count
    )
    if out_of_range:
        failures.append(
            "proof verdicts contain out-of-range cube IDs "
            f"(first: {out_of_range[:20]})"
        )

    missing: list[int] = []
    stale: list[int] = []
    stale_checker_logs: list[int] = []
    for index in range(cube_count):
        verdict = latest.get(index)
        if (
            not verdict
            or verdict.get("status") != "VERIFIED"
            or verdict.get("checker_rc") not in (0, 20)
            or "s VERIFIED" not in str(verdict.get("checker_output_tail", ""))
        ):
            missing.append(index)
            continue
        proof = campaign / "drat" / f"cube_{index}{proof_suffix}"
        if (
            not proof.is_file()
            or sha256(proof) != verdict.get("proof_sha256")
        ):
            stale.append(index)
        checker_log = campaign / "checker-logs" / f"cube_{index}.checker.log"
        recorded_checker_log = Path(str(verdict.get("checker_log", "")))
        if (
            not checker_log.is_file()
            or recorded_checker_log.resolve() != checker_log.resolve()
            or sha256(checker_log) != verdict.get("checker_log_sha256")
            or "s VERIFIED" not in checker_log.read_text(
                encoding="utf-8",
                errors="replace",
            )
        ):
            stale_checker_logs.append(index)

    if missing:
        failures.append(
            f"{len(missing)} cubes lack a VERIFIED proof "
            f"(first: {missing[:20]})"
        )
    if stale:
        failures.append(
            f"{len(stale)} verified proof files are absent or changed "
            f"(first: {stale[:20]})"
        )
    if stale_checker_logs:
        failures.append(
            f"{len(stale_checker_logs)} checker logs are absent or changed "
            f"(first: {stale_checker_logs[:20]})"
        )

    report = {
        "campaign": str(campaign),
        "base_sha256": manifest.get("base_sha256"),
        "split_variables": split,
        "tree_summary": tree_summary,
        "cube_count": cube_count,
        "verified_cubes": cube_count - len(missing),
        "failures": failures,
        "complete": not failures,
        "partition_argument": partition_argument,
    }
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
