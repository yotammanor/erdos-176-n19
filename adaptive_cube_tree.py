#!/usr/bin/env python3
"""Reconstruct and audit a complete tree from ordered adaptive cubes.

Look-ahead cubers commonly omit branches closed by propagation.  The returned
cube list alone therefore need not cover every assignment.  This module uses
the literal order in each returned cube to reconstruct the decision tree and
adds each omitted sibling as an explicit gap leaf.  If every resulting leaf is
later proved UNSAT, the complete binary tree gives a checkable case split.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


SCHEMA = "erdos176.adaptive-cube-tree.v1"


class CubeTreeError(ValueError):
    """The cubes or serialized tree do not define a valid partition."""


def require_integer(value: object, description: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CubeTreeError(f"{description} must be an integer")
    return value


def normalize_cube(cube: Sequence[int]) -> tuple[int, ...]:
    if isinstance(cube, (str, bytes)):
        raise CubeTreeError("a cube must be an array of integer literals")
    literals = tuple(
        require_integer(literal, "cube literal") for literal in cube
    )
    seen: set[int] = set()
    for literal in literals:
        variable = abs(literal)
        if not variable:
            raise CubeTreeError("cube literals must be nonzero")
        if variable in seen:
            raise CubeTreeError(
                f"cube repeats variable {variable}: {list(literals)}"
            )
        seen.add(variable)
    return literals


def reconstruct_tree(
    cubes: Sequence[Sequence[int]],
    *,
    nvars: int | None = None,
) -> dict[str, object]:
    """Complete the adaptive decision tree represented by ordered leaf cubes."""
    normalized = [normalize_cube(cube) for cube in cubes]
    if not normalized:
        raise CubeTreeError("cannot reconstruct a tree from no cubes")
    if nvars is not None:
        nvars = require_integer(nvars, "nvars")
        if nvars < 1:
            raise CubeTreeError("nvars must be positive")
        if any(abs(literal) > nvars for cube in normalized for literal in cube):
            raise CubeTreeError("returned cube uses a variable above nvars")

    nodes: list[dict[str, object]] = []
    next_leaf = 0

    def add_leaf(literals: tuple[int, ...], origin: str) -> int:
        nonlocal next_leaf
        node_id = len(nodes)
        nodes.append(
            {
                "id": node_id,
                "type": "leaf",
                "leaf_id": next_leaf,
                "origin": origin,
                "literals": list(literals),
            }
        )
        next_leaf += 1
        return node_id

    def build(
        suffixes: list[tuple[int, ...]],
        prefix: tuple[int, ...],
    ) -> int:
        empty = [suffix for suffix in suffixes if not suffix]
        if empty:
            if len(suffixes) != 1:
                raise CubeTreeError(
                    "a returned cube is both a leaf and an ancestor"
                )
            return add_leaf(prefix, "generator")

        variables = {abs(suffix[0]) for suffix in suffixes}
        if len(variables) != 1:
            raise CubeTreeError(
                "returned cubes disagree on the next split after "
                f"{list(prefix)}: {sorted(variables)}"
            )
        variable = variables.pop()
        if variable in {abs(literal) for literal in prefix}:
            raise CubeTreeError(
                f"split variable {variable} repeats after {list(prefix)}"
            )

        node_id = len(nodes)
        nodes.append({})
        children: dict[str, int] = {}
        for name, literal in (("negative", -variable), ("positive", variable)):
            matching = [
                suffix[1:] for suffix in suffixes if suffix[0] == literal
            ]
            child_prefix = (*prefix, literal)
            children[name] = (
                build(matching, child_prefix)
                if matching
                else add_leaf(child_prefix, "filled-gap")
            )
        nodes[node_id] = {
            "id": node_id,
            "type": "split",
            "variable": variable,
            **children,
        }
        return node_id

    root = build(normalized, ())
    tree: dict[str, object] = {
        "schema": SCHEMA,
        "root": root,
        "nodes": nodes,
        "returned_cube_count": len(normalized),
        "leaf_count": next_leaf,
        "partition_argument": (
            "Every split node has both Boolean children. Therefore its leaf "
            "paths partition all assignments, including explicit leaves added "
            "for branches omitted by the look-ahead cube generator."
        ),
    }
    if nvars is not None:
        tree["nvars"] = nvars
    audit_tree(tree, nvars=nvars)
    return tree


def audit_tree(
    tree: dict[str, object],
    *,
    nvars: int | None = None,
) -> dict[str, int]:
    """Fail closed unless a serialized tree is a complete Boolean partition."""
    if tree.get("schema") != SCHEMA:
        raise CubeTreeError(f"unsupported tree schema: {tree.get('schema')!r}")
    declared_nvars = tree.get("nvars")
    if declared_nvars is not None:
        declared_nvars = require_integer(
            declared_nvars,
            "declared nvars",
        )
        if declared_nvars < 1:
            raise CubeTreeError("declared nvars must be positive")
        if nvars is not None and declared_nvars != nvars:
            raise CubeTreeError("declared nvars differs from the audited formula")
        nvars = declared_nvars
    raw_nodes = tree.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise CubeTreeError("tree nodes must be a nonempty list")
    if any(not isinstance(node, dict) for node in raw_nodes):
        raise CubeTreeError("every tree node must be an object")

    nodes = {
        require_integer(node.get("id"), "tree node ID"): node
        for node in raw_nodes
    }
    expected_ids = set(range(len(raw_nodes)))
    if set(nodes) != expected_ids:
        raise CubeTreeError("tree node IDs must be unique and contiguous")
    root = require_integer(tree.get("root"), "tree root")
    if root not in nodes:
        raise CubeTreeError("tree root is missing")

    visited: set[int] = set()
    leaf_ids: set[int] = set()
    origins: dict[str, int] = {"generator": 0, "filled-gap": 0}
    maximum_depth = 0

    def visit(
        node_id: int,
        path: tuple[int, ...],
        ancestors: frozenset[int],
    ) -> None:
        nonlocal maximum_depth
        if node_id in ancestors:
            raise CubeTreeError(f"cycle reaches node {node_id}")
        if node_id in visited:
            raise CubeTreeError(f"node {node_id} has multiple parents")
        visited.add(node_id)
        node = nodes[node_id]
        kind = node.get("type")
        if kind == "leaf":
            leaf_id = require_integer(node.get("leaf_id"), "leaf ID")
            if leaf_id < 0 or leaf_id in leaf_ids:
                raise CubeTreeError(f"invalid or duplicate leaf ID {leaf_id}")
            leaf_ids.add(leaf_id)
            literals = node.get("literals")
            if literals != list(path):
                raise CubeTreeError(
                    f"leaf {leaf_id} literals disagree with its tree path"
                )
            origin = str(node.get("origin"))
            if origin not in origins:
                raise CubeTreeError(f"leaf {leaf_id} has invalid origin")
            origins[origin] += 1
            maximum_depth = max(maximum_depth, len(path))
            return
        if kind != "split":
            raise CubeTreeError(f"node {node_id} has invalid type {kind!r}")

        variable = require_integer(node.get("variable"), "split variable")
        if variable <= 0 or (nvars is not None and variable > nvars):
            raise CubeTreeError(f"node {node_id} has invalid split variable")
        if variable in {abs(literal) for literal in path}:
            raise CubeTreeError(
                f"node {node_id} repeats split variable {variable}"
            )
        negative = require_integer(node.get("negative"), "negative child")
        positive = require_integer(node.get("positive"), "positive child")
        if negative not in nodes or positive not in nodes or negative == positive:
            raise CubeTreeError(f"node {node_id} has invalid children")
        next_ancestors = ancestors | {node_id}
        visit(negative, (*path, -variable), next_ancestors)
        visit(positive, (*path, variable), next_ancestors)

    visit(root, (), frozenset())
    if visited != expected_ids:
        raise CubeTreeError(
            f"tree has unreachable nodes: {sorted(expected_ids - visited)}"
        )
    if leaf_ids != set(range(len(leaf_ids))):
        raise CubeTreeError("leaf IDs must be unique and contiguous")
    leaf_count = require_integer(tree.get("leaf_count"), "declared leaf count")
    if leaf_count != len(leaf_ids):
        raise CubeTreeError("declared leaf count does not match the tree")
    returned_count = require_integer(
        tree.get("returned_cube_count"),
        "declared returned-cube count",
    )
    if returned_count != origins["generator"]:
        raise CubeTreeError("declared returned-cube count does not match leaves")

    return {
        "nodes": len(nodes),
        "leaves": len(leaf_ids),
        "generator_leaves": origins["generator"],
        "gap_leaves": origins["filled-gap"],
        "maximum_depth": maximum_depth,
    }


def leaf_cubes(tree: dict[str, object]) -> dict[int, tuple[int, ...]]:
    """Return leaf ID to path literals after auditing the tree."""
    audit_tree(tree)
    return {
        node["leaf_id"]: tuple(node["literals"])
        for node in tree["nodes"]
        if node["type"] == "leaf"
    }


def refine_leaf(
    tree: dict[str, object],
    leaf_id: int,
    refinements: Sequence[Sequence[int]],
) -> dict[str, object]:
    """Replace one leaf by a relative adaptive partition below that leaf."""
    summary = audit_tree(tree)
    leaf_id = require_integer(leaf_id, "refined leaf ID")
    leaves = leaf_cubes(tree)
    if leaf_id not in leaves:
        raise CubeTreeError(f"refined leaf ID {leaf_id} does not exist")
    normalized = [normalize_cube(cube) for cube in refinements]
    if not normalized:
        raise CubeTreeError("cannot refine a leaf from no cubes")

    prefix = leaves[leaf_id]
    fixed = {abs(literal) for literal in prefix}
    repeated = sorted(
        {
            abs(literal)
            for cube in normalized
            for literal in cube
            if abs(literal) in fixed
        }
    )
    if repeated:
        raise CubeTreeError(
            f"refinement repeats fixed path variables: {repeated}"
        )

    combined: list[tuple[int, ...]] = []
    for current_id in range(summary["leaves"]):
        if current_id == leaf_id:
            combined.extend((*prefix, *cube) for cube in normalized)
        else:
            combined.append(leaves[current_id])
    declared_nvars = tree.get("nvars")
    nvars = (
        require_integer(declared_nvars, "declared nvars")
        if declared_nvars is not None
        else None
    )
    return reconstruct_tree(combined, nvars=nvars)


def refine_leaves(
    tree: dict[str, object],
    refinements_by_leaf: dict[int, Sequence[Sequence[int]]],
) -> dict[str, object]:
    """Replace several audited leaves by independent relative partitions."""
    summary = audit_tree(tree)
    if not refinements_by_leaf:
        raise CubeTreeError("cannot refine no leaves")
    leaves = leaf_cubes(tree)
    normalized_by_leaf: dict[int, list[tuple[int, ...]]] = {}
    for raw_leaf_id, refinements in refinements_by_leaf.items():
        leaf_id = require_integer(raw_leaf_id, "refined leaf ID")
        if leaf_id not in leaves:
            raise CubeTreeError(f"refined leaf ID {leaf_id} does not exist")
        normalized = [normalize_cube(cube) for cube in refinements]
        if not normalized:
            raise CubeTreeError(
                f"cannot refine leaf {leaf_id} from no cubes"
            )
        fixed = {abs(literal) for literal in leaves[leaf_id]}
        repeated = sorted(
            {
                abs(literal)
                for cube in normalized
                for literal in cube
                if abs(literal) in fixed
            }
        )
        if repeated:
            raise CubeTreeError(
                f"refinement repeats fixed path variables: {repeated}"
            )
        normalized_by_leaf[leaf_id] = normalized

    combined: list[tuple[int, ...]] = []
    for current_id in range(summary["leaves"]):
        if current_id in normalized_by_leaf:
            prefix = leaves[current_id]
            combined.extend(
                (*prefix, *cube)
                for cube in normalized_by_leaf[current_id]
            )
        else:
            combined.append(leaves[current_id])
    declared_nvars = tree.get("nvars")
    nvars = (
        require_integer(declared_nvars, "declared nvars")
        if declared_nvars is not None
        else None
    )
    return reconstruct_tree(combined, nvars=nvars)


def refine_subtree(
    tree: dict[str, object],
    prefix: Sequence[int],
    refinements: Sequence[Sequence[int]],
) -> dict[str, object]:
    """Replace the complete subtree rooted at an exact path prefix."""
    summary = audit_tree(tree)
    normalized_prefix = normalize_cube(prefix)
    normalized = [normalize_cube(cube) for cube in refinements]
    if not normalized:
        raise CubeTreeError("cannot refine a subtree from no cubes")

    nodes = {int(node["id"]): node for node in tree["nodes"]}
    node_id = require_integer(tree.get("root"), "tree root")
    for literal in normalized_prefix:
        node = nodes[node_id]
        if node.get("type") != "split":
            raise CubeTreeError("subtree prefix descends beyond a leaf")
        variable = require_integer(node.get("variable"), "split variable")
        if abs(literal) != variable:
            raise CubeTreeError(
                "subtree prefix disagrees with the next tree split: "
                f"expected variable {variable}, got {abs(literal)}"
            )
        child = "positive" if literal > 0 else "negative"
        node_id = require_integer(node.get(child), f"{child} child")

    target_leaf_ids: set[int] = set()

    def collect(current_id: int) -> None:
        node = nodes[current_id]
        if node.get("type") == "leaf":
            target_leaf_ids.add(
                require_integer(node.get("leaf_id"), "leaf ID")
            )
            return
        collect(require_integer(node.get("negative"), "negative child"))
        collect(require_integer(node.get("positive"), "positive child"))

    collect(node_id)
    fixed = {abs(literal) for literal in normalized_prefix}
    repeated = sorted(
        {
            abs(literal)
            for cube in normalized
            for literal in cube
            if abs(literal) in fixed
        }
    )
    if repeated:
        raise CubeTreeError(
            f"refinement repeats fixed path variables: {repeated}"
        )

    leaves = leaf_cubes(tree)
    combined: list[tuple[int, ...]] = []
    inserted = False
    for current_id in range(summary["leaves"]):
        if current_id in target_leaf_ids:
            if not inserted:
                combined.extend(
                    (*normalized_prefix, *cube) for cube in normalized
                )
                inserted = True
        else:
            combined.append(leaves[current_id])
    declared_nvars = tree.get("nvars")
    nvars = (
        require_integer(declared_nvars, "declared nvars")
        if declared_nvars is not None
        else None
    )
    return reconstruct_tree(combined, nvars=nvars)


def cubes_from_payload(
    payload: object,
    *,
    nvars: int,
) -> list[Sequence[int]]:
    """Validate a cuber JSON envelope and return its relative cubes."""
    if isinstance(payload, dict):
        if "status" in payload:
            status = require_integer(payload["status"], "cube generator status")
            if status != 0:
                raise CubeTreeError(
                    f"cube generator status is {status!r}, not 0"
                )
        if (
            "nvars" in payload
            and require_integer(payload["nvars"], "generator nvars") != nvars
        ):
            raise CubeTreeError(
                "cube generator nvars differs from the audited formula"
            )
        try:
            raw_cubes = payload["cubes"]
        except KeyError as error:
            raise CubeTreeError("cubes JSON object lacks a cubes array") from error
    else:
        raw_cubes = payload
    if not isinstance(raw_cubes, list):
        raise CubeTreeError("cubes JSON must contain an array")
    return raw_cubes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cubes", type=Path, help="JSON object with a cubes array")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nvars", type=int, required=True)
    args = parser.parse_args()

    try:
        payload = json.loads(args.cubes.read_text(encoding="utf-8"))
        raw_cubes = cubes_from_payload(payload, nvars=args.nvars)
    except (TypeError, json.JSONDecodeError) as error:
        raise CubeTreeError("invalid cubes JSON payload") from error
    tree = reconstruct_tree(raw_cubes, nvars=args.nvars)
    summary = audit_tree(tree, nvars=args.nvars)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.write_text(
        json.dumps(tree, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
