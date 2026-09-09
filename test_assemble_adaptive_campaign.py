from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import adaptive_cube_tree
import assemble_adaptive_campaign
from cube_campaign import sha256


class AssembleAdaptiveCampaignTests(unittest.TestCase):
    def make_fixture(
        self, root: Path
    ) -> tuple[
        Path,
        Path,
        Path,
        Path,
        dict[int, tuple[int, ...]],
    ]:
        base = root / "base.cnf"
        base.write_text("p cnf 1 1\n1 0\n", encoding="ascii")
        solver = root / "solver"
        checker = root / "checker"
        solver.write_text("solver\n", encoding="ascii")
        checker.write_text("checker\n", encoding="ascii")
        tree_path = root / "tree.json"
        tree = adaptive_cube_tree.reconstruct_tree(((1,), (-1,)), nvars=1)
        tree_path.write_text(
            json.dumps(tree, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return (
            base,
            solver,
            checker,
            tree_path,
            adaptive_cube_tree.leaf_cubes(tree),
        )

    def make_source(
        self,
        root: Path,
        name: str,
        *,
        base: Path,
        solver: Path,
        checker: Path,
        tree_path: Path,
        cube_map: dict[int, tuple[int, ...]],
        solved: set[int],
    ) -> Path:
        campaign = root / name
        proof_dir = campaign / "drat"
        log_dir = campaign / "logs"
        proof_dir.mkdir(parents=True)
        log_dir.mkdir()
        manifest = {
            "schema": "erdos176.adaptive-cube-campaign.v1",
            "base": str(base),
            "base_sha256": sha256(base),
            "solver": str(solver),
            "solver_sha256": sha256(solver),
            "checker": str(checker),
            "checker_sha256": sha256(checker),
            "nvars": 1,
            "nclauses": 1,
            "n_original": 1,
            "k": 3,
            "ell": 2,
            "cube_count": len(cube_map),
            "tree": str(tree_path),
            "tree_sha256": sha256(tree_path),
            "cube_convention": "leaf ID and literals from audited tree",
        }
        (campaign / "manifest.json").write_text(
            json.dumps(manifest) + "\n", encoding="utf-8"
        )
        verdicts = []
        for index in sorted(solved):
            proof = proof_dir / f"cube_{index}.drat"
            proof.write_text(f"proof {name} {index}\n", encoding="ascii")
            (log_dir / f"cube_{index}.solver.log").write_text(
                f"log {name} {index}\n", encoding="ascii"
            )
            verdicts.append(
                {
                    "cube": index,
                    "literals": cube_map[index],
                    "status": "UNVERIFIED",
                    "solver_rc": 20,
                    "solver": str(solver),
                    "solver_sha256": sha256(solver),
                    "proof_sha256": sha256(proof),
                    "proof_bytes": proof.stat().st_size,
                }
            )
        (campaign / "verdicts.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in verdicts),
            encoding="utf-8",
        )
        return campaign

    def test_assembles_exact_leaf_proofs_from_multiple_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, solver, checker, tree_path, cube_map = self.make_fixture(root)
            first, second = sorted(cube_map)
            source_a = self.make_source(
                root,
                "source-a",
                base=base,
                solver=solver,
                checker=checker,
                tree_path=tree_path,
                cube_map=cube_map,
                solved={first},
            )
            source_b = self.make_source(
                root,
                "source-b",
                base=base,
                solver=solver,
                checker=checker,
                tree_path=tree_path,
                cube_map=cube_map,
                solved={second},
            )
            destination = root / "assembled"
            report = assemble_adaptive_campaign.assemble(
                tree_path=tree_path,
                reference_campaign=source_a,
                campaigns=(source_a, source_b),
                destination=destination,
            )

            self.assertTrue(report["complete"])
            self.assertEqual(2, report["covered_leaves"])
            self.assertEqual(
                sum(
                    (destination / "drat" / f"cube_{index}.drat").stat().st_size
                    for index in cube_map
                ),
                report["covered_proof_bytes"],
            )
            self.assertEqual(
                sum(
                    (
                        destination
                        / "logs"
                        / f"cube_{index}.solver.log"
                    ).stat().st_size
                    for index in cube_map
                ),
                report["covered_solver_log_bytes"],
            )
            manifest = json.loads(
                (destination / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(2, manifest["cube_count"])
            verdicts = assemble_adaptive_campaign.records(
                destination / "verdicts.jsonl"
            )
            self.assertEqual([first, second], [item["cube"] for item in verdicts])
            self.assertTrue(
                all("source_campaign" in item for item in verdicts)
            )
            for index in cube_map:
                assembled_proof = (
                    destination / "drat" / f"cube_{index}.drat"
                )
                self.assertTrue(assembled_proof.is_file())
                self.assertTrue(
                    (
                        destination
                        / "logs"
                        / f"cube_{index}.solver.log"
                    ).is_file()
                )
                source = source_a if index == first else source_b
                source_proof = source / "drat" / f"cube_{index}.drat"
                self.assertNotEqual(
                    source_proof.stat().st_ino,
                    assembled_proof.stat().st_ino,
                )

    def test_assembles_proofs_from_different_solvers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, solver_a, checker, tree_path, cube_map = self.make_fixture(root)
            solver_b = root / "solver-b"
            solver_b.write_text("different solver\n", encoding="ascii")
            first, second = sorted(cube_map)
            source_a = self.make_source(
                root,
                "source-a",
                base=base,
                solver=solver_a,
                checker=checker,
                tree_path=tree_path,
                cube_map=cube_map,
                solved={first},
            )
            source_b = self.make_source(
                root,
                "source-b",
                base=base,
                solver=solver_b,
                checker=checker,
                tree_path=tree_path,
                cube_map=cube_map,
                solved={second},
            )

            destination = root / "assembled"
            report = assemble_adaptive_campaign.assemble(
                tree_path=tree_path,
                reference_campaign=source_a,
                campaigns=(source_a, source_b),
                destination=destination,
            )

            self.assertTrue(report["complete"])
            manifest = json.loads(
                (destination / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                {
                    (str(solver_a), sha256(solver_a)),
                    (str(solver_b), sha256(solver_b)),
                },
                {
                    (item["path"], item["sha256"])
                    for item in manifest["solvers"]
                },
            )

    def test_incomplete_coverage_does_not_create_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, solver, checker, tree_path, cube_map = self.make_fixture(root)
            source = self.make_source(
                root,
                "source",
                base=base,
                solver=solver,
                checker=checker,
                tree_path=tree_path,
                cube_map=cube_map,
                solved={min(cube_map)},
            )
            destination = root / "assembled"
            report = assemble_adaptive_campaign.assemble(
                tree_path=tree_path,
                reference_campaign=source,
                campaigns=(source,),
                destination=destination,
            )

            self.assertFalse(report["complete"])
            self.assertGreater(report["covered_proof_bytes"], 0)
            self.assertGreater(report["covered_solver_log_bytes"], 0)
            self.assertEqual(1, len(report["missing_leaves"]))
            self.assertFalse(destination.exists())

    def test_changed_source_proof_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, solver, checker, tree_path, cube_map = self.make_fixture(root)
            index = min(cube_map)
            source = self.make_source(
                root,
                "source",
                base=base,
                solver=solver,
                checker=checker,
                tree_path=tree_path,
                cube_map=cube_map,
                solved={index},
            )
            (source / "drat" / f"cube_{index}.drat").write_text(
                "tampered\n", encoding="ascii"
            )
            with self.assertRaisesRegex(
                ValueError, "source artifacts are missing or changed"
            ):
                assemble_adaptive_campaign.assemble(
                    tree_path=tree_path,
                    reference_campaign=source,
                    campaigns=(source,),
                    destination=root / "assembled",
                )


if __name__ == "__main__":
    unittest.main()
