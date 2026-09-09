from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import add_overlap_links_cnf
import independent_audit_cnf
import nk2


class IndependentCnfAuditTests(unittest.TestCase):
    def write_small_cnf(self, path: Path) -> None:
        clauses, nvars = nk2.build_cnf(
            9,
            3,
            2,
            fix_first=True,
            encoding="threshold",
        )
        nk2.write_dimacs(path, clauses, nvars, comments=("test fixture",))

    def test_exact_small_encoding_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "small.cnf"
            self.write_small_cnf(path)
            report = independent_audit_cnf.audit(
                path,
                n=9,
                k=3,
                ell=2,
                fix_first=True,
            )
            self.assertEqual("PASS", report["exact_clause_stream"])
            self.assertEqual("PASS", report["local_gadget_truth_tables"])

    def test_one_literal_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "small.cnf"
            self.write_small_cnf(path)
            lines = path.read_text(encoding="ascii").splitlines()
            clause_index = next(
                index
                for index, line in enumerate(lines)
                if line and line[0] not in "cp"
            )
            tokens = lines[clause_index].split()
            tokens[0] = str(-int(tokens[0]))
            lines[clause_index] = " ".join(tokens)
            path.write_text("\n".join(lines) + "\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "clause 1 differs"):
                independent_audit_cnf.audit(
                    path,
                    n=9,
                    k=3,
                    ell=2,
                    fix_first=True,
                )

    def test_overlap_linked_small_encoding_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "small.cnf"
            linked = Path(temporary) / "small-linked.cnf"
            self.write_small_cnf(base)
            add_overlap_links_cnf.augment(base, linked, 9, 3, 2)
            report = independent_audit_cnf.audit(
                linked,
                n=9,
                k=3,
                ell=2,
                fix_first=True,
                overlap_links=True,
            )
            self.assertEqual("PASS", report["overlap_links"])
            self.assertEqual("PASS", report["overlap_relation_truth_table"])


if __name__ == "__main__":
    unittest.main()
