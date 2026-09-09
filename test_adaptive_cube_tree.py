#!/usr/bin/env python3
"""Tests for independently auditable adaptive cube partitions."""

from __future__ import annotations

import copy
import itertools
import unittest

import adaptive_cube_tree as cubes


def matching_leaves(
    leaves: dict[int, tuple[int, ...]],
    assignment: tuple[bool, ...],
) -> int:
    return sum(
        all(assignment[abs(literal) - 1] == (literal > 0) for literal in cube)
        for cube in leaves.values()
    )


class AdaptiveCubeTreeTests(unittest.TestCase):
    def assert_partitions_assignments(
        self,
        tree: dict[str, object],
        nvars: int,
    ) -> None:
        leaves = cubes.leaf_cubes(tree)
        for assignment in itertools.product((False, True), repeat=nvars):
            self.assertEqual(
                1,
                matching_leaves(leaves, assignment),
                assignment,
            )

    def test_complete_adaptive_paths_need_no_gap_leaves(self) -> None:
        tree = cubes.reconstruct_tree(
            ((1, 2), (1, -2), (-1, 3), (-1, -3))
        )
        summary = cubes.audit_tree(tree, nvars=3)
        self.assertEqual(4, summary["generator_leaves"])
        self.assertEqual(0, summary["gap_leaves"])
        self.assert_partitions_assignments(tree, 3)

    def test_omitted_conflict_branches_become_explicit_leaves(self) -> None:
        tree = cubes.reconstruct_tree(((1, 2), (1, -2), (-1, 3)))
        summary = cubes.audit_tree(tree, nvars=3)
        self.assertEqual(3, summary["generator_leaves"])
        self.assertEqual(1, summary["gap_leaves"])
        self.assertIn((-1, -3), cubes.leaf_cubes(tree).values())
        self.assert_partitions_assignments(tree, 3)

    def test_missing_root_branch_becomes_a_short_leaf(self) -> None:
        tree = cubes.reconstruct_tree(((1, 2), (1, -2)))
        self.assertIn((-1,), cubes.leaf_cubes(tree).values())
        self.assert_partitions_assignments(tree, 2)

    def test_empty_returned_cube_covers_every_assignment(self) -> None:
        tree = cubes.reconstruct_tree(((),))
        self.assertEqual({0: ()}, cubes.leaf_cubes(tree))
        self.assert_partitions_assignments(tree, 3)

    def test_one_leaf_can_be_refined_without_changing_others(self) -> None:
        tree = cubes.reconstruct_tree(((1,), (-1,)), nvars=2)
        refined = cubes.refine_leaf(tree, 1, ((2,), (-2,)))
        self.assertEqual(
            {(-1,), (1, -2), (1, 2)},
            set(cubes.leaf_cubes(refined).values()),
        )
        self.assert_partitions_assignments(refined, 2)

    def test_refinement_cannot_repeat_a_fixed_path_variable(self) -> None:
        tree = cubes.reconstruct_tree(((1,), (-1,)), nvars=2)
        with self.assertRaisesRegex(cubes.CubeTreeError, "fixed path"):
            cubes.refine_leaf(tree, 1, ((1,),))

    def test_multiple_leaves_can_be_refined_in_one_reconstruction(self) -> None:
        tree = cubes.reconstruct_tree(((-1,), (1,)), nvars=3)
        refined = cubes.refine_leaves(
            tree,
            {
                0: ((-2,), (2,)),
                1: ((-3,), (3,)),
            },
        )
        self.assertEqual(
            {
                (-1, -2),
                (-1, 2),
                (1, -3),
                (1, 3),
            },
            set(cubes.leaf_cubes(refined).values()),
        )
        self.assert_partitions_assignments(refined, 3)

    def test_complete_subtree_can_be_repartitioned(self) -> None:
        tree = cubes.reconstruct_tree(
            ((-1,), (1, -2, -3), (1, -2, 3), (1, 2)),
            nvars=4,
        )
        refined = cubes.refine_subtree(
            tree,
            (1, -2),
            ((-4,), (4,)),
        )
        self.assertEqual(
            {
                (-1,),
                (1, -2, -4),
                (1, -2, 4),
                (1, 2),
            },
            set(cubes.leaf_cubes(refined).values()),
        )
        self.assert_partitions_assignments(refined, 4)

    def test_subtree_prefix_must_follow_exact_tree_path(self) -> None:
        tree = cubes.reconstruct_tree(((-1,), (1,)), nvars=2)
        with self.assertRaisesRegex(cubes.CubeTreeError, "next tree split"):
            cubes.refine_subtree(tree, (2,), ((1,),))

    def test_subtree_refinement_cannot_repeat_prefix_variable(self) -> None:
        tree = cubes.reconstruct_tree(((-1,), (1,)), nvars=2)
        with self.assertRaisesRegex(cubes.CubeTreeError, "fixed path"):
            cubes.refine_subtree(tree, (1,), ((-1,),))

    def test_cuber_envelope_status_and_variable_count_are_checked(self) -> None:
        with self.assertRaisesRegex(cubes.CubeTreeError, "status is 20"):
            cubes.cubes_from_payload(
                {"status": 20, "nvars": 3, "cubes": []},
                nvars=3,
            )
        with self.assertRaisesRegex(cubes.CubeTreeError, "nvars differs"):
            cubes.cubes_from_payload(
                {"status": 0, "nvars": 4, "cubes": []},
                nvars=3,
            )

    def test_inconsistent_next_split_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            cubes.CubeTreeError,
            "disagree on the next split",
        ):
            cubes.reconstruct_tree(((1, 2), (1, 3)))

    def test_repeated_variable_is_rejected(self) -> None:
        with self.assertRaisesRegex(cubes.CubeTreeError, "repeats variable"):
            cubes.reconstruct_tree(((1, -1),))

    def test_literals_and_metadata_are_strict_integers(self) -> None:
        for literal in ("1", 1.0, True):
            with self.subTest(literal=literal):
                with self.assertRaisesRegex(
                    cubes.CubeTreeError,
                    "cube literal must be an integer",
                ):
                    cubes.reconstruct_tree(((literal,),))

        tree = cubes.reconstruct_tree(((1,), (-1,)), nvars=1)
        tampered = copy.deepcopy(tree)
        tampered["nodes"][0]["id"] = "0"
        with self.assertRaisesRegex(cubes.CubeTreeError, "node ID"):
            cubes.audit_tree(tampered)

    def test_empty_cube_list_is_rejected(self) -> None:
        with self.assertRaisesRegex(cubes.CubeTreeError, "from no cubes"):
            cubes.reconstruct_tree(())

    def test_leaf_cannot_also_be_an_ancestor(self) -> None:
        with self.assertRaisesRegex(
            cubes.CubeTreeError,
            "both a leaf and an ancestor",
        ):
            cubes.reconstruct_tree(((1,), (1, 2)))

    def test_formula_variable_bound_is_enforced(self) -> None:
        with self.assertRaisesRegex(cubes.CubeTreeError, "above nvars"):
            cubes.reconstruct_tree(((4,),), nvars=3)
        tree = cubes.reconstruct_tree(((3,), (-3,)), nvars=3)
        with self.assertRaisesRegex(
            cubes.CubeTreeError,
            "differs from the audited formula",
        ):
            cubes.audit_tree(tree, nvars=4)

    def test_leaf_path_tampering_is_rejected(self) -> None:
        tree = cubes.reconstruct_tree(((1,), (-1,)))
        tampered = copy.deepcopy(tree)
        leaf = next(
            node for node in tampered["nodes"] if node["type"] == "leaf"
        )
        leaf["literals"] = [2]
        with self.assertRaisesRegex(
            cubes.CubeTreeError,
            "literals disagree",
        ):
            cubes.audit_tree(tampered, nvars=2)

    def test_missing_child_is_rejected(self) -> None:
        tree = cubes.reconstruct_tree(((1,), (-1,)))
        tampered = copy.deepcopy(tree)
        tampered["nodes"][0]["negative"] = 999
        with self.assertRaisesRegex(cubes.CubeTreeError, "invalid children"):
            cubes.audit_tree(tampered, nvars=2)

    def test_declared_counts_are_audited(self) -> None:
        tree = cubes.reconstruct_tree(((1,), (-1,)))
        bad_leaf_count = copy.deepcopy(tree)
        bad_leaf_count["leaf_count"] = 3
        with self.assertRaisesRegex(cubes.CubeTreeError, "leaf count"):
            cubes.audit_tree(bad_leaf_count, nvars=1)

        bad_returned_count = copy.deepcopy(tree)
        bad_returned_count["returned_cube_count"] = 1
        with self.assertRaisesRegex(cubes.CubeTreeError, "returned-cube count"):
            cubes.audit_tree(bad_returned_count, nvars=1)

    def test_shared_child_is_rejected(self) -> None:
        tree = cubes.reconstruct_tree(((1,), (-1,)))
        tampered = copy.deepcopy(tree)
        tampered["nodes"][0]["positive"] = tampered["nodes"][0]["negative"]
        with self.assertRaisesRegex(cubes.CubeTreeError, "invalid children"):
            cubes.audit_tree(tampered, nvars=1)

    def test_invalid_origin_and_schema_are_rejected(self) -> None:
        tree = cubes.reconstruct_tree(((),))
        bad_origin = copy.deepcopy(tree)
        bad_origin["nodes"][0]["origin"] = "untrusted"
        with self.assertRaisesRegex(cubes.CubeTreeError, "invalid origin"):
            cubes.audit_tree(bad_origin)

        bad_schema = copy.deepcopy(tree)
        bad_schema["schema"] = "unknown"
        with self.assertRaisesRegex(cubes.CubeTreeError, "unsupported"):
            cubes.audit_tree(bad_schema)

    def test_unreachable_node_is_rejected(self) -> None:
        tree = cubes.reconstruct_tree(((1,), (-1,)))
        tampered = copy.deepcopy(tree)
        node_id = len(tampered["nodes"])
        tampered["nodes"].append(
            {
                "id": node_id,
                "type": "leaf",
                "leaf_id": 2,
                "origin": "filled-gap",
                "literals": [],
            }
        )
        tampered["leaf_count"] = 3
        with self.assertRaisesRegex(cubes.CubeTreeError, "unreachable"):
            cubes.audit_tree(tampered, nvars=2)


if __name__ == "__main__":
    unittest.main()
