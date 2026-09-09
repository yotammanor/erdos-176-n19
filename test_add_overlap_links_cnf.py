"""Tests for redundant overlap identities in the threshold CNF."""

from __future__ import annotations

import itertools
import unittest

import add_overlap_links_cnf as overlap


class OverlapRelationTests(unittest.TestCase):
    def test_truth_table_is_exact(self) -> None:
        variables = (1, 2, 3, 4)
        clauses = list(overlap.relation_clauses(variables))
        self.assertEqual(len(clauses), 10)

        for bits in itertools.product((0, 1), repeat=4):
            assignment = dict(zip(variables, bits))
            satisfies = all(
                any(
                    assignment[abs(literal)] == int(literal > 0)
                    for literal in clause
                )
                for clause in clauses
            )
            y1, y2, first, last = bits
            self.assertEqual(
                satisfies,
                y1 - y2 - first + last == 0,
            )

    def test_sign_variable_matches_threshold_layout(self) -> None:
        self.assertEqual(overlap.states_per_progression(19, 2), 154)
        self.assertEqual(overlap.sign_variable(344, 19, 2, 0), 497)
        self.assertEqual(overlap.sign_variable(344, 19, 2, 3115), 480207)

    def test_full_instance_overlap_clause_count(self) -> None:
        self.assertEqual(
            sum(1 for _ in overlap.overlap_clauses(344, 19, 2)),
            29_430,
        )


if __name__ == "__main__":
    unittest.main()
