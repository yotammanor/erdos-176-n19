#!/usr/bin/env python3
"""Refine many audited adaptive-tree leaves with parallel cuber runs."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import tempfile
from pathlib import Path

import adaptive_cube_tree
from cube_campaign import parse_indices, read_header, sha256, write_cube_cnf


def compress_indices(indices: list[int]) -> str:
    """Encode sorted indices using cube_campaign's half-open range syntax."""
    if not indices:
        return ""
    parts: list[str] = []
    start = previous = indices[0]
    for index in indices[1:]:
        if index == previous + 1:
            previous = index
            continue
        parts.append(str(start) if start == previous else f"{start}:{previous + 1}")
        start = previous = index
    parts.append(str(start) if start == previous else f"{start}:{previous + 1}")
    return ",".join(parts)


def generate_refinement(
    *,
    leaf_id: int,
    prefix: tuple[int, ...],
    base: Path,
    cuber: Path,
    depth: int,
    maximum_variable: int | None,
    nvars: int,
    temporary_root: Path | None,
) -> tuple[int, list[tuple[int, ...]]]:
    with tempfile.TemporaryDirectory(
        prefix=f"erdos176-bulk-refine-{leaf_id}-",
        dir=temporary_root,
    ) as directory:
        temporary = Path(directory)
        cubed_base = temporary / "leaf.cnf"
        generated_path = temporary / "cubes.json"
        write_cube_cnf(base, cubed_base, prefix)
        command = [
            str(cuber),
            str(cubed_base),
            str(depth),
            str(generated_path),
        ]
        if maximum_variable is not None:
            command.extend(["0", str(maximum_variable)])
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(
                f"cuber failed for leaf {leaf_id} with "
                f"exit {completed.returncode}: {completed.stdout}"
            )
        payload = json.loads(generated_path.read_text(encoding="utf-8"))
        relative = [
            adaptive_cube_tree.normalize_cube(cube)
            for cube in adaptive_cube_tree.cubes_from_payload(
                payload,
                nvars=nvars,
            )
        ]
        if not relative:
            raise RuntimeError(f"cuber returned no cubes for leaf {leaf_id}")
        return leaf_id, relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument(
        "--leaf",
        type=int,
        action="append",
        help="leaf ID to refine; repeat as needed",
    )
    targets.add_argument(
        "--indices",
        help="comma-separated leaf IDs and half-open ranges",
    )
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument(
        "--cuber",
        type=Path,
        default=Path("tools/bin/cadical-generate-cubes"),
    )
    parser.add_argument("--cuber-max-variable", type=int)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--temporary-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-output", type=Path, required=True)
    args = parser.parse_args()

    if args.depth < 1:
        raise ValueError("--depth must be positive")
    if args.jobs < 1:
        raise ValueError("--jobs must be positive")
    if args.leaf is not None and len(args.leaf) != len(set(args.leaf)):
        raise ValueError("duplicate --leaf")
    for output in (args.output, args.plan_output):
        if output.exists():
            raise FileExistsError(f"refusing to overwrite {output}")

    base = args.base.resolve()
    tree_path = args.tree.resolve()
    cuber = args.cuber.resolve()
    temporary_root = (
        args.temporary_dir.resolve() if args.temporary_dir is not None else None
    )
    if temporary_root is not None:
        temporary_root.mkdir(parents=True, exist_ok=True)
    nvars, _ = read_header(base)
    if (
        args.cuber_max_variable is not None
        and not 1 <= args.cuber_max_variable <= nvars
    ):
        raise ValueError("--cuber-max-variable is outside the CNF variable range")

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    before = adaptive_cube_tree.audit_tree(tree, nvars=nvars)
    leaves = adaptive_cube_tree.leaf_cubes(tree)
    target_ids = (
        sorted(args.leaf)
        if args.leaf is not None
        else parse_indices(args.indices, before["leaves"])
    )
    absent = sorted(set(target_ids) - set(leaves))
    if absent:
        raise ValueError(f"leaves absent from input tree: {absent}")
    prefixes = {leaf_id: leaves[leaf_id] for leaf_id in target_ids}

    refinements: dict[int, list[tuple[int, ...]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(
                generate_refinement,
                leaf_id=leaf_id,
                prefix=prefix,
                base=base,
                cuber=cuber,
                depth=args.depth,
                maximum_variable=args.cuber_max_variable,
                nvars=nvars,
                temporary_root=temporary_root,
            ): leaf_id
            for leaf_id, prefix in prefixes.items()
        }
        for completed_count, future in enumerate(
            concurrent.futures.as_completed(futures),
            start=1,
        ):
            leaf_id, relative = future.result()
            refinements[leaf_id] = relative
            print(
                json.dumps(
                    {
                        "completed": completed_count,
                        "leaf": leaf_id,
                        "relative_cubes": len(relative),
                        "total": len(futures),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    refined = adaptive_cube_tree.refine_leaves(tree, refinements)
    after = adaptive_cube_tree.audit_tree(refined, nvars=nvars)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(refined, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    refined_leaves = adaptive_cube_tree.leaf_cubes(refined)
    details: list[dict[str, object]] = []
    selected: set[int] = set()
    for leaf_id, prefix in prefixes.items():
        new_ids = [
            new_id
            for new_id, literals in refined_leaves.items()
            if literals[: len(prefix)] == prefix
        ]
        if not new_ids:
            raise RuntimeError(f"refined prefix for leaf {leaf_id} disappeared")
        selected.update(new_ids)
        details.append(
            {
                "input_leaf": leaf_id,
                "input_literals": list(prefix),
                "relative_returned_cubes": len(refinements[leaf_id]),
                "output_leaves": new_ids,
            }
        )
    selected_indices = sorted(selected)
    report: dict[str, object] = {
        "schema": "erdos176.bulk-adaptive-refinement.v1",
        "base": str(base),
        "base_sha256": sha256(base),
        "input_tree": str(tree_path),
        "input_tree_sha256": sha256(tree_path),
        "output_tree": str(args.output.resolve()),
        "output_tree_sha256": sha256(args.output),
        "cuber": str(cuber),
        "cuber_sha256": sha256(cuber),
        "depth": args.depth,
        "cuber_max_variable": args.cuber_max_variable,
        "before": before,
        "after": after,
        "refined_input_leaves": len(prefixes),
        "selected_output_leaves": len(selected_indices),
        "indices": selected_indices,
        "indices_spec": compress_indices(selected_indices),
        "refinements": details,
    }
    args.plan_output.parent.mkdir(parents=True, exist_ok=True)
    args.plan_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
