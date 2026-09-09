#!/usr/bin/env python3

from __future__ import annotations

import itertools
import tempfile
import unittest
from pathlib import Path

import independent_audit_sliding_cnf
import independent_audit_opb
import nk2
import sliding_state_cnf


def satisfies(clauses: list[list[int]], assignment: dict[int, bool]) -> bool:
    return all(
        any(assignment[abs(literal)] == (literal > 0) for literal in clause)
        for clause in clauses
    )


class SlidingStateCnfTests(unittest.TestCase):
    def test_relation_truth_table(self) -> None:
        clauses = list(sliding_state_cnf.relation_clauses((1, 2, 3, 4)))
        self.assertEqual(len(clauses), 10)
        for bits in itertools.product((False, True), repeat=4):
            assignment = dict(enumerate(bits, start=1))
            expected = int(bits[0]) - int(bits[1]) - int(bits[2]) + int(
                bits[3]
            ) == 0
            self.assertEqual(satisfies(clauses, assignment), expected)

    def test_exact_counter_has_one_extension_exactly_at_target(self) -> None:
        clauses: list[list[int]] = []
        top_id, added = sliding_state_cnf.append_exact_counter(
            clauses, (1, 2, 3, 4), 2, 4
        )
        self.assertEqual(top_id, 13)
        self.assertEqual(added, 9)
        for inputs in itertools.product((False, True), repeat=4):
            extensions = 0
            for auxiliary in itertools.product((False, True), repeat=added):
                assignment = {
                    **dict(enumerate(inputs, start=1)),
                    **dict(enumerate(auxiliary, start=5)),
                }
                extensions += satisfies(clauses, assignment)
            self.assertEqual(extensions, int(sum(inputs) == 2))

    def test_small_formula_is_existentially_equivalent(self) -> None:
        for fix_first in (False, True):
            clauses, nvars, _ = sliding_state_cnf.build_cnf(
                4, 3, fix_first=fix_first
            )
            self.assertEqual(nvars, 15)
            for colors in itertools.product((-1, 1), repeat=4):
                original = {
                    index: color == 1
                    for index, color in enumerate(colors, start=1)
                }
                has_extension = False
                for auxiliary in itertools.product(
                    (False, True), repeat=nvars - len(colors)
                ):
                    assignment = {
                        **original,
                        **dict(enumerate(auxiliary, start=len(colors) + 1)),
                    }
                    if satisfies(clauses, assignment):
                        has_extension = True
                        break
                self.assertEqual(
                    has_extension,
                    bool(nk2.verify_coloring(colors, 3, 2)["avoids"])
                    and (not fix_first or colors[0] == 1),
                    (fix_first, colors),
                )

    def test_independent_auditor_matches_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small.cnf"
            sliding_state_cnf.write_dimacs(
                path, 8, 3, fix_first=True
            )
            report = independent_audit_sliding_cnf.audit(
                path, n=8, k=3, ell=2, fix_first=True
            )
            self.assertEqual(report["exact_clause_stream"], "PASS")

            lines = path.read_text(encoding="ascii").splitlines()
            clause_index = next(
                index
                for index, line in enumerate(lines)
                if line and line[0] not in "cp"
            )
            fields = lines[clause_index].split()
            fields[0] = str(-int(fields[0]))
            lines[clause_index] = " ".join(fields)
            path.write_text("\n".join(lines) + "\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "clause .* differs"):
                independent_audit_sliding_cnf.audit(
                    path, n=8, k=3, ell=2, fix_first=True
                )

    def test_sliding_opb_matches_independent_constraint_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small.opb"
            report = sliding_state_cnf.write_opb(
                path, 20, 5, fix_first=True
            )
            header, observed = independent_audit_opb.parse_opb(path)
            nvars, expected, roots, links = (
                independent_audit_opb.expected_sliding_state_constraints(
                    20, 5, 2, True
                )
            )
            self.assertEqual(observed, expected)
            self.assertEqual(header[:2], (nvars, sum(expected.values())))
            self.assertEqual(report["root_equations"], roots)
            self.assertEqual(report["overlap_equations"], links)

    def test_full_instance_size(self) -> None:
        clauses, nvars, counts = sliding_state_cnf.build_cnf(
            344, 19, fix_first=True
        )
        self.assertEqual(nvars, 32005)
        self.assertEqual(len(clauses), 138594)
        self.assertEqual(
            counts,
            {
                "progressions": 3116,
                "state_variables": 3116,
                "root_counters": 173,
                "counter_variables": 28545,
                "overlap_relations": 2943,
            },
        )


if __name__ == "__main__":
    unittest.main()
