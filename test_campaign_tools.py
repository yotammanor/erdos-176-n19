from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import adaptive_cube_tree
import cube_campaign
import gate_campaign
import verify_campaign


class AdaptiveCampaignTests(unittest.TestCase):
    def make_campaign(
        self,
        root: Path,
    ) -> tuple[Path, Path, dict[str, object]]:
        base = root / "base.cnf"
        base.write_text("p cnf 1 1\n1 0\n", encoding="ascii")
        tree_path = root / "tree.json"
        tree = adaptive_cube_tree.reconstruct_tree(((1,), (-1,)), nvars=1)
        tree_path.write_text(
            json.dumps(tree, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        campaign = root / "campaign"
        campaign.mkdir()
        (campaign / "verdicts.jsonl").write_text(
            "\n".join(
                (
                    json.dumps({"cube": 0, "status": "VERIFIED"}),
                    json.dumps({"cube": 1, "status": "VERIFIED"}),
                    "",
                )
            ),
            encoding="utf-8",
        )
        solver = root / "solver"
        checker = root / "checker"
        solver.write_text("solver\n", encoding="ascii")
        checker.write_text("checker\n", encoding="ascii")
        arguments = [
            "cube_campaign.py",
            "--base",
            str(base),
            "--solver",
            str(solver),
            "--checker",
            str(checker),
            "--campaign",
            str(campaign),
            "--n-original",
            "1",
            "--k",
            "3",
            "--tree",
            str(tree_path),
        ]
        with mock.patch.object(sys, "argv", arguments):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, cube_campaign.main())
        manifest = json.loads(
            (campaign / "manifest.json").read_text(encoding="utf-8")
        )
        return campaign, tree_path, manifest

    def test_run_cube_stages_proof_outside_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base.cnf"
            base.write_text("p cnf 1 1\n1 0\n", encoding="ascii")
            solver = root / "solver"
            solver.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$2\" > \"$2\"\nexit 20\n",
                encoding="ascii",
            )
            solver.chmod(0o755)
            campaign = root / "campaign"
            proof_dir = campaign / "drat"
            log_dir = campaign / "logs"
            proof_dir.mkdir(parents=True)
            log_dir.mkdir()
            transient = root / "transient"
            transient.mkdir()

            verdict = cube_campaign.run_cube(
                index=0,
                literals=(1,),
                base=base,
                solver=solver,
                checker=solver,
                proof_dir=proof_dir,
                log_dir=log_dir,
                temporary_dir=transient,
                timeout=10,
                checker_timeout=None,
                defer_check=True,
                solver_args=(),
                proof_suffix=".drat",
                n_original=1,
                k=3,
            )

            proof = proof_dir / "cube_0.drat"
            staged_path = Path(proof.read_text(encoding="ascii").strip())
            self.assertEqual("UNVERIFIED", verdict["status"])
            self.assertEqual(transient, staged_path.parent)
            self.assertFalse(staged_path.exists())

    def test_run_cube_can_discard_partial_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base.cnf"
            base.write_text("p cnf 1 1\n1 0\n", encoding="ascii")
            solver = root / "solver"
            solver.write_text(
                "#!/bin/sh\nprintf 'partial\\n' > \"$2\"\nexit 0\n",
                encoding="ascii",
            )
            solver.chmod(0o755)
            proof_dir = root / "campaign" / "drat"
            log_dir = root / "campaign" / "logs"
            proof_dir.mkdir(parents=True)
            log_dir.mkdir()
            transient = root / "transient"
            transient.mkdir()

            verdict = cube_campaign.run_cube(
                index=0,
                literals=(1,),
                base=base,
                solver=solver,
                checker=solver,
                proof_dir=proof_dir,
                log_dir=log_dir,
                temporary_dir=transient,
                timeout=10,
                checker_timeout=None,
                defer_check=True,
                solver_args=(),
                proof_suffix=".drat",
                n_original=1,
                k=3,
                retain_partial_proofs=False,
            )

            self.assertEqual("UNKNOWN", verdict["status"])
            self.assertFalse((proof_dir / "cube_0.partial.drat").exists())
            self.assertEqual([], list(transient.iterdir()))

    def test_adaptive_manifest_and_complete_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign, _, manifest = self.make_campaign(root)
            self.assertEqual(
                "erdos176.adaptive-cube-campaign.v1",
                manifest["schema"],
            )
            proof_dir = campaign / "drat"
            proof_dir.mkdir(exist_ok=True)
            checker_log_dir = campaign / "checker-logs"
            checker_log_dir.mkdir()
            verdicts = []
            for index in range(2):
                proof = proof_dir / f"cube_{index}.drat"
                proof.write_text(f"proof {index}\n", encoding="ascii")
                checker_log = (
                    checker_log_dir / f"cube_{index}.checker.log"
                )
                checker_log.write_text("s VERIFIED\n", encoding="ascii")
                verdicts.append(
                    {
                        "cube": index,
                        "status": "VERIFIED",
                        "checker_rc": 0,
                        "checker_output_tail": "s VERIFIED\n",
                        "checker_log": str(checker_log),
                        "checker_log_sha256": cube_campaign.sha256(checker_log),
                        "proof_sha256": cube_campaign.sha256(proof),
                    }
                )
            (campaign / "proof_verdicts.jsonl").write_text(
                "".join(json.dumps(verdict) + "\n" for verdict in verdicts),
                encoding="utf-8",
            )

            output = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                ["gate_campaign.py", "--campaign", str(campaign)],
            ):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, gate_campaign.main())
            report = json.loads(output.getvalue())
            self.assertTrue(report["complete"])
            self.assertEqual(2, report["tree_summary"]["leaves"])

    def test_tree_tampering_closes_the_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            campaign, tree_path, _ = self.make_campaign(Path(temporary))
            tree_path.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(
                sys,
                "argv",
                ["gate_campaign.py", "--campaign", str(campaign)],
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(1, gate_campaign.main())

    def test_later_failed_check_revokes_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof_verdicts.jsonl"
            path.write_text(
                "\n".join(
                    (
                        json.dumps({"cube": 4, "status": "VERIFIED"}),
                        json.dumps({"cube": 4, "status": "CHECK_FAILED"}),
                        "",
                    )
                ),
                encoding="utf-8",
            )
            self.assertEqual(set(), verify_campaign.completed_indices(path))

    def test_parallel_verification_records_each_cube(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            campaign, _, manifest = self.make_campaign(Path(temporary))
            checker = Path(str(manifest["checker"]))
            checker.write_text(
                "#!/bin/sh\necho 's VERIFIED'\n", encoding="ascii"
            )
            checker.chmod(0o755)
            manifest["checker_sha256"] = cube_campaign.sha256(checker)
            (campaign / "manifest.json").write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )
            proof_dir = campaign / "drat"
            proof_dir.mkdir(exist_ok=True)
            for index in range(2):
                (proof_dir / f"cube_{index}.drat").write_text(
                    f"proof {index}\n", encoding="ascii"
                )

            arguments = [
                "verify_campaign.py",
                "--campaign",
                str(campaign),
                "--checker",
                str(checker),
                "--jobs",
                "2",
                "--recheck",
            ]
            with mock.patch.object(sys, "argv", arguments):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, verify_campaign.main())
            verdicts = [
                json.loads(line)
                for line in (campaign / "proof_verdicts.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual({0, 1}, {item["cube"] for item in verdicts})
            self.assertTrue(
                all(item["status"] == "VERIFIED" for item in verdicts)
            )

    def test_tampered_assembly_provenance_closes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            campaign, tree_path, manifest = self.make_campaign(
                Path(temporary)
            )
            assembly_path = campaign / "assembly.json"
            assembly_path.write_text(
                json.dumps(
                    {
                        "schema": "erdos176.adaptive-campaign-assembly.v1",
                        "destination": str(campaign),
                        "tree_sha256": cube_campaign.sha256(tree_path),
                        "covered_leaves": 2,
                        "missing_leaves": [],
                        "complete": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manifest["assembly"] = str(assembly_path)
            manifest["assembly_sha256"] = cube_campaign.sha256(assembly_path)
            (campaign / "manifest.json").write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )
            assembly_path.write_text("tampered\n", encoding="utf-8")

            output = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                ["gate_campaign.py", "--campaign", str(campaign)],
            ):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(1, gate_campaign.main())
            report = json.loads(output.getvalue())
            self.assertIn(
                "campaign assembly file is missing or changed",
                report["failures"],
            )

    def test_tampered_solver_inventory_closes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign, _, manifest = self.make_campaign(root)
            second_solver = root / "second-solver"
            second_solver.write_text("second solver\n", encoding="ascii")
            manifest["solvers"] = [
                {
                    "path": str(second_solver),
                    "sha256": "0" * 64,
                }
            ]
            (campaign / "manifest.json").write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )

            output = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                ["gate_campaign.py", "--campaign", str(campaign)],
            ):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(1, gate_campaign.main())
            report = json.loads(output.getvalue())
            self.assertIn(
                f"solver inventory SHA-256 mismatch: {second_solver}",
                report["failures"],
            )


if __name__ == "__main__":
    unittest.main()
