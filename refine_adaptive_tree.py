#!/usr/bin/env python3
"""Graft a relative cuber result below an audited tree leaf or subtree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import adaptive_cube_tree


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--leaf", type=int)
    target.add_argument(
        "--prefix-literals",
        help="comma-separated exact root-to-subtree path literals",
    )
    parser.add_argument("--cubes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tree = json.loads(args.tree.read_text(encoding="utf-8"))
    adaptive_cube_tree.audit_tree(tree)
    nvars = adaptive_cube_tree.require_integer(
        tree.get("nvars"),
        "declared nvars",
    )
    payload = json.loads(args.cubes.read_text(encoding="utf-8"))
    relative_cubes = adaptive_cube_tree.cubes_from_payload(
        payload,
        nvars=nvars,
    )
    if args.leaf is not None:
        refined = adaptive_cube_tree.refine_leaf(
            tree,
            args.leaf,
            relative_cubes,
        )
    else:
        prefix = tuple(
            int(item)
            for item in str(args.prefix_literals).split(",")
            if item
        )
        refined = adaptive_cube_tree.refine_subtree(
            tree,
            prefix,
            relative_cubes,
        )
    summary = adaptive_cube_tree.audit_tree(refined, nvars=nvars)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(refined, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
