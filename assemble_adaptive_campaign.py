#!/usr/bin/env python3
"""Assemble final adaptive-tree proofs from compatible source campaigns."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Iterable

import adaptive_cube_tree
from cube_campaign import read_header, sha256


ACCEPTED = {"UNVERIFIED", "VERIFIED"}
INSTANCE_COMPATIBILITY_FIELDS = (
    "base",
    "base_sha256",
    "checker",
    "checker_sha256",
    "nvars",
    "nclauses",
    "n_original",
    "k",
    "ell",
)


def records(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def latest_records(path: Path) -> dict[int, dict[str, object]]:
    latest: dict[int, dict[str, object]] = {}
    for record in records(path):
        latest[int(record["cube"])] = record
    return latest


def checked_manifest(campaign: Path) -> dict[str, object]:
    manifest_path = campaign / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "erdos176.adaptive-cube-campaign.v1":
        raise ValueError(f"source campaign is not adaptive: {campaign}")

    base = Path(str(manifest["base"]))
    tree_path = Path(str(manifest["tree"]))
    solver = Path(str(manifest["solver"]))
    checker = Path(str(manifest["checker"]))
    for label, path, digest in (
        ("base CNF", base, manifest["base_sha256"]),
        ("adaptive tree", tree_path, manifest["tree_sha256"]),
        ("solver", solver, manifest["solver_sha256"]),
        ("checker", checker, manifest["checker_sha256"]),
    ):
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"{label} is missing or changed for {campaign}")
    if read_header(base) != (
        int(manifest["nvars"]),
        int(manifest["nclauses"]),
    ):
        raise ValueError(f"base header differs from manifest for {campaign}")

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    summary = adaptive_cube_tree.audit_tree(
        tree, nvars=int(manifest["nvars"])
    )
    if summary["leaves"] != int(manifest["cube_count"]):
        raise ValueError(f"source tree leaf count differs for {campaign}")
    return manifest


def compatible(reference: dict[str, object], other: dict[str, object]) -> bool:
    return (
        str(reference.get("proof_suffix", ".drat"))
        == str(other.get("proof_suffix", ".drat"))
        and all(
            reference.get(field) == other.get(field)
            for field in INSTANCE_COMPATIBILITY_FIELDS
        )
    )


def source_candidates(
    reference_campaign: Path,
    campaigns: Iterable[Path],
) -> tuple[
    dict[str, object],
    dict[tuple[int, ...], dict[str, object]],
    list[dict[str, object]],
]:
    reference_campaign = reference_campaign.resolve()
    reference = checked_manifest(reference_campaign)
    candidates: dict[tuple[int, ...], dict[str, object]] = {}
    source_reports: list[dict[str, object]] = []

    source_paths = {path.resolve() for path in campaigns}
    source_paths.add(reference_campaign)
    for campaign in sorted(source_paths):
        raw_manifest = json.loads(
            (campaign / "manifest.json").read_text(encoding="utf-8")
        )
        if (
            raw_manifest.get("schema")
            != "erdos176.adaptive-cube-campaign.v1"
            or not compatible(reference, raw_manifest)
        ):
            source_reports.append(
                {
                    "campaign": str(campaign),
                    "status": "SKIPPED_INCOMPATIBLE",
                }
            )
            continue
        manifest = checked_manifest(campaign)

        tree_path = Path(str(manifest["tree"]))
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        cube_map = adaptive_cube_tree.leaf_cubes(tree)
        proof_suffix = str(manifest.get("proof_suffix", ".drat"))
        accepted = 0
        for source_index, verdict in latest_records(
            campaign / "verdicts.jsonl"
        ).items():
            if (
                verdict.get("status") not in ACCEPTED
                or verdict.get("solver_rc") != 20
                or not isinstance(verdict.get("proof_sha256"), str)
            ):
                continue
            if source_index not in cube_map:
                raise ValueError(
                    f"source verdict has unknown cube {source_index}: {campaign}"
                )
            raw_literals = verdict.get("literals")
            if not isinstance(raw_literals, list) or any(
                type(literal) is not int for literal in raw_literals
            ):
                raise ValueError(
                    f"source verdict has invalid literals for cube "
                    f"{source_index}: {campaign}"
                )
            literals = tuple(raw_literals)
            if literals != cube_map[source_index]:
                raise ValueError(
                    f"source verdict literals differ for cube {source_index}: "
                    f"{campaign}"
                )

            proof = campaign / "drat" / f"cube_{source_index}{proof_suffix}"
            solver_log = campaign / "logs" / f"cube_{source_index}.solver.log"
            solver = Path(str(verdict.get("solver", "")))
            if (
                not proof.is_file()
                or sha256(proof) != verdict["proof_sha256"]
                or not solver_log.is_file()
                or not solver.is_file()
                or sha256(solver) != verdict.get("solver_sha256")
            ):
                raise ValueError(
                    f"source artifacts are missing or changed for cube "
                    f"{source_index}: {campaign}"
                )

            candidate = {
                "campaign": campaign,
                "manifest": campaign / "manifest.json",
                "source_cube": source_index,
                "proof": proof,
                "solver_log": solver_log,
                "solver_log_sha256": sha256(solver_log),
                "verdict": verdict,
            }
            previous = candidates.get(literals)
            if previous is None or (
                proof.stat().st_size,
                str(campaign),
                source_index,
            ) < (
                Path(str(previous["proof"])).stat().st_size,
                str(previous["campaign"]),
                int(previous["source_cube"]),
            ):
                candidates[literals] = candidate
            accepted += 1
        source_reports.append(
            {
                "campaign": str(campaign),
                "status": "ACCEPTED",
                "manifest_sha256": sha256(campaign / "manifest.json"),
                "accepted_records": accepted,
            }
        )

    return reference, candidates, source_reports


def copy_checked(
    source: Path, destination: Path, *, expected_sha256: str
) -> str:
    before = sha256(source)
    if before != expected_sha256:
        raise ValueError(f"source changed before assembly: {source}")
    shutil.copy2(source, destination)
    after = sha256(source)
    copied = sha256(destination)
    if after != before or copied != before:
        raise ValueError(f"source changed while assembling: {source}")
    return copied


def assemble(
    *,
    tree_path: Path,
    reference_campaign: Path,
    campaigns: Iterable[Path],
    destination: Path | None,
) -> dict[str, object]:
    tree_path = tree_path.resolve()
    reference, candidates, source_reports = source_candidates(
        reference_campaign, campaigns
    )
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    summary = adaptive_cube_tree.audit_tree(
        tree, nvars=int(reference["nvars"])
    )
    cube_map = adaptive_cube_tree.leaf_cubes(tree)
    missing = [
        index for index, literals in cube_map.items() if literals not in candidates
    ]
    covered = [
        candidates[literals]
        for literals in cube_map.values()
        if literals in candidates
    ]
    report: dict[str, object] = {
        "schema": "erdos176.adaptive-campaign-assembly.v1",
        "tree": str(tree_path),
        "tree_sha256": sha256(tree_path),
        "tree_summary": summary,
        "covered_leaves": len(cube_map) - len(missing),
        "covered_proof_bytes": sum(
            Path(str(candidate["proof"])).stat().st_size
            for candidate in covered
        ),
        "covered_solver_log_bytes": sum(
            Path(str(candidate["solver_log"])).stat().st_size
            for candidate in covered
        ),
        "missing_leaves": missing,
        "complete": not missing,
        "sources": source_reports,
    }
    if missing or destination is None:
        return report

    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    selected_counts: Counter[str] = Counter()
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}-assemble-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / destination.name
        proof_dir = staged / "drat"
        log_dir = staged / "logs"
        proof_dir.mkdir(parents=True)
        log_dir.mkdir()
        verdicts: list[dict[str, object]] = []
        proof_suffix = str(reference.get("proof_suffix", ".drat"))
        for index, literals in cube_map.items():
            candidate = candidates[literals]
            source_campaign = Path(str(candidate["campaign"]))
            source_cube = int(candidate["source_cube"])
            source_proof = Path(str(candidate["proof"]))
            source_log = Path(str(candidate["solver_log"]))
            proof = proof_dir / f"cube_{index}{proof_suffix}"
            solver_log = log_dir / f"cube_{index}.solver.log"
            proof_sha256 = copy_checked(
                source_proof,
                proof,
                expected_sha256=str(
                    dict(candidate["verdict"])["proof_sha256"]
                ),
            )
            solver_log_sha256 = copy_checked(
                source_log,
                solver_log,
                expected_sha256=str(candidate["solver_log_sha256"]),
            )

            verdict = dict(candidate["verdict"])
            verdict.update(
                {
                    "cube": index,
                    "literals": literals,
                    "source_campaign": str(source_campaign),
                    "source_cube": source_cube,
                    "source_manifest_sha256": sha256(
                        Path(str(candidate["manifest"]))
                    ),
                    "proof_sha256": proof_sha256,
                    "solver_log": str(
                        destination / "logs" / solver_log.name
                    ),
                    "solver_log_bytes": solver_log.stat().st_size,
                    "solver_log_sha256": solver_log_sha256,
                }
            )
            verdicts.append(verdict)
            selected_counts[str(source_campaign)] += 1

        manifest = {
            field: reference[field] for field in INSTANCE_COMPATIBILITY_FIELDS
        }
        manifest["solver"] = reference["solver"]
        manifest["solver_sha256"] = reference["solver_sha256"]
        solvers = {
            (str(verdict["solver"]), str(verdict["solver_sha256"]))
            for verdict in verdicts
        }
        manifest["solvers"] = [
            {"path": path, "sha256": digest}
            for path, digest in sorted(solvers)
        ]
        manifest.update(
            {
                "schema": "erdos176.adaptive-cube-campaign.v1",
                "cube_count": len(cube_map),
                "tree": str(tree_path),
                "tree_sha256": sha256(tree_path),
                "cube_convention": "leaf ID and literals from audited tree",
            }
        )
        if "proof_suffix" in reference:
            manifest["proof_suffix"] = reference["proof_suffix"]
        if len(solvers) == 1 and "solver_args" in reference:
            manifest["solver_args"] = reference["solver_args"]
        elif len(solvers) > 1:
            manifest["solver_provenance"] = "per-cube verdict records"
        (staged / "verdicts.jsonl").write_text(
            "".join(
                json.dumps(verdict, sort_keys=True) + "\n"
                for verdict in verdicts
            ),
            encoding="utf-8",
        )
        report["destination"] = str(destination)
        report["selected_source_counts"] = dict(
            sorted(selected_counts.items())
        )
        assembly_path = staged / "assembly.json"
        assembly_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest["assembly"] = str(destination / "assembly.json")
        manifest["assembly_sha256"] = sha256(assembly_path)
        (staged / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staged.replace(destination)
    return report


def discover_campaigns(roots: Iterable[Path]) -> list[Path]:
    campaigns: list[Path] = []
    for root in roots:
        campaigns.extend(
            manifest.parent
            for manifest in root.resolve().glob("*/manifest.json")
        )
    return sorted(set(campaigns))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        action="append",
        required=True,
        help="directory whose immediate child campaigns are searched",
    )
    parser.add_argument(
        "--reference-campaign",
        type=Path,
        required=True,
        help="compatible campaign defining the base and tool provenance",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = assemble(
        tree_path=args.tree,
        reference_campaign=args.reference_campaign,
        campaigns=discover_campaigns(args.source_root),
        destination=args.output,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
