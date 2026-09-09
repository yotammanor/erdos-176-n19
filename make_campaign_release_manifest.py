#!/usr/bin/env python3
"""Create a fail-closed release manifest for a verified cube campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import independent_audit_cnf
import independent_audit_sliding_cnf
import nk2


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
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
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument(
        "--witness",
        type=Path,
        default=Path("witnesses/k19_N343.txt"),
    )
    parser.add_argument(
        "--cnf-audit",
        type=Path,
        default=Path("proofs/adaptive/k19_N344_x1.cnf.audit.json"),
    )
    parser.add_argument(
        "--witness-audit",
        type=Path,
        default=Path("proofs/adaptive/k19_N343.witness.audit.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("certificate_manifest.json"),
    )
    args = parser.parse_args()

    campaign = args.campaign.resolve()
    manifest_path = campaign / "manifest.json"
    campaign_manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    gate_command = (
        sys.executable,
        str(ROOT / "gate_campaign.py"),
        "--campaign",
        str(campaign),
    )
    gated = subprocess.run(
        gate_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        text=True,
    )
    if gated.returncode:
        raise ValueError(f"campaign gate failed:\n{gated.stdout}")
    gate_report = json.loads(gated.stdout)
    if not gate_report.get("complete"):
        raise ValueError("campaign gate did not report complete")

    for field, expected in (
        ("n_original", 344),
        ("k", 19),
        ("ell", 2),
    ):
        if campaign_manifest.get(field) != expected:
            raise ValueError(f"unexpected campaign {field}")

    witness_path = args.witness.resolve()
    coloring = nk2.parse_coloring(witness_path)
    witness_verdict = nk2.verify_coloring(coloring, 19, 2)
    if len(coloring) != 343 or not witness_verdict["avoids"]:
        raise ValueError("lower-bound witness did not pass verification")
    witness_audit_path = args.witness_audit.resolve()
    witness_audit = json.loads(
        witness_audit_path.read_text(encoding="utf-8")
    )
    for field, expected in (
        ("n", 343),
        ("k", 19),
        ("ell", 2),
        ("checked_progressions", 3097),
        ("avoids", True),
        ("first_bad", None),
    ):
        if witness_audit.get(field) != expected:
            raise ValueError(f"witness audit has unexpected {field}")
    if witness_audit.get("witness_sha256") != sha256(witness_path):
        raise ValueError("witness audit is for a different file")

    audit_path = args.cnf_audit.resolve()
    cnf_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    common_audit_fields = (
        ("n", 344),
        ("k", 19),
        ("ell", 2),
        ("fix_first", True),
        ("exact_clause_stream", "PASS"),
    )
    for field, expected in common_audit_fields:
        if cnf_audit.get(field) != expected:
            raise ValueError(f"CNF audit has unexpected {field}")
    if cnf_audit.get("sha256") != campaign_manifest["base_sha256"]:
        raise ValueError("CNF audit is for a different base instance")
    audit_schema = cnf_audit.get("schema")
    if audit_schema == "erdos176.independent-cnf-audit.v1":
        if cnf_audit.get("local_gadget_truth_tables") != "PASS":
            raise ValueError("threshold CNF gadget audit did not pass")
        fresh_cnf_audit = independent_audit_cnf.audit(
            Path(str(campaign_manifest["base"])),
            n=344,
            k=19,
            ell=2,
            fix_first=True,
        )
    elif audit_schema == "erdos176.independent-sliding-cnf-audit.v1":
        for field in (
            "local_counter_truth_tables",
            "overlap_relation_truth_table",
            "chain_partition",
        ):
            if cnf_audit.get(field) != "PASS":
                raise ValueError(f"sliding CNF audit did not pass {field}")
        fresh_cnf_audit = independent_audit_sliding_cnf.audit(
            Path(str(campaign_manifest["base"])),
            n=344,
            k=19,
            ell=2,
            fix_first=True,
        )
    else:
        raise ValueError(f"unsupported CNF audit schema: {audit_schema!r}")
    if fresh_cnf_audit != cnf_audit:
        raise ValueError("fresh CNF audit differs from the archived audit")

    cube_count = int(campaign_manifest["cube_count"])
    proof_suffix = str(campaign_manifest.get("proof_suffix", ".drat"))
    proofs = [
        artifact(campaign / "drat" / f"cube_{index}{proof_suffix}")
        for index in range(cube_count)
    ]
    solver_logs = [
        artifact(campaign / "logs" / f"cube_{index}.solver.log")
        for index in range(cube_count)
    ]
    checker_logs = [
        artifact(campaign / "checker-logs" / f"cube_{index}.checker.log")
        for index in range(cube_count)
    ]
    tree_path = Path(str(campaign_manifest["tree"]))
    files = {
        "base_cnf": artifact(Path(str(campaign_manifest["base"]))),
        "adaptive_tree": artifact(tree_path),
        "campaign_manifest": artifact(manifest_path),
        "solver_verdicts": artifact(campaign / "verdicts.jsonl"),
        "checker_verdicts": artifact(campaign / "proof_verdicts.jsonl"),
        "independent_cnf_audit": artifact(audit_path),
        "independent_witness_audit": artifact(witness_audit_path),
        "lower_bound_witness": artifact(witness_path),
        "encoding_generator": artifact(ROOT / "sliding_state_cnf.py"),
        "encoding_auditor": artifact(
            ROOT / "independent_audit_sliding_cnf.py"
        ),
        "tree_auditor": artifact(ROOT / "adaptive_cube_tree.py"),
        "campaign_runner": artifact(ROOT / "cube_campaign.py"),
        "campaign_assembler": artifact(
            ROOT / "assemble_adaptive_campaign.py"
        ),
        "campaign_verifier": artifact(ROOT / "verify_campaign.py"),
        "campaign_gate": artifact(ROOT / "gate_campaign.py"),
        "proofs": proofs,
        "solver_logs": solver_logs,
        "checker_logs": checker_logs,
    }
    assembly_path = campaign / "assembly.json"
    if assembly_path.is_file():
        files["campaign_assembly"] = artifact(assembly_path)
    if files["base_cnf"]["sha256"] != campaign_manifest["base_sha256"]:
        raise ValueError("base CNF changed after the campaign")
    if files["adaptive_tree"]["sha256"] != campaign_manifest["tree_sha256"]:
        raise ValueError("adaptive tree changed after the campaign")

    solver_paths = {Path(str(campaign_manifest["solver"]))}
    for line in (campaign / "verdicts.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        verdict = json.loads(line)
        if (
            verdict.get("status") in ("VERIFIED", "UNVERIFIED")
            and verdict.get("proof_sha256")
            and isinstance(verdict.get("solver"), str)
        ):
            solver_path = Path(str(verdict["solver"]))
            if sha256(solver_path) != verdict.get("solver_sha256"):
                raise ValueError("per-cube solver binary changed after its run")
            solver_paths.add(solver_path)

    release = {
        "schema": "erdos176.adaptive-certificate-release.v1",
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
                "symmetry_break": "x1 = true; color complementation",
                "partition_leaves": cube_count,
                "maximum_tree_depth": gate_report["tree_summary"][
                    "maximum_depth"
                ],
                "verified_drat_proofs": gate_report["verified_cubes"],
            },
        },
        "gate": gate_report,
        "commands": {
            "verify": [
                sys.executable,
                str(ROOT / "verify_campaign.py"),
                "--campaign",
                str(campaign),
                "--checker",
                str(campaign_manifest["checker"]),
                "--recheck",
            ],
            "gate": list(gate_command),
        },
        "tools": {
            "solvers": [
                artifact(path)
                for path in sorted(solver_paths, key=lambda item: str(item))
            ],
            "checker": artifact(Path(str(campaign_manifest["checker"]))),
        },
        "files": files,
        "proof_bytes_total": sum(proof["bytes"] for proof in proofs),
    }

    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.write_text(
        json.dumps(release, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
