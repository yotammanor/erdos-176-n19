#!/usr/bin/env python3
"""Recover an adaptive-refinement queue from immutable round artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import adaptive_cube_tree
from cube_campaign import read_header, sha256


CLOSED = {"UNVERIFIED", "VERIFIED"}


def latest_verdicts(path: Path) -> dict[int, dict[str, object]]:
    latest: dict[int, dict[str, object]] = {}
    if not path.is_file():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            verdict = json.loads(line)
            latest[int(verdict["cube"])] = verdict
    return latest


def recover(
    *,
    base: Path,
    initial_tree_path: Path,
    initial_leaf_ids: list[int],
    prefix: str,
    first_round: int,
    last_round: int,
) -> dict[str, object]:
    base = base.resolve()
    nvars, _ = read_header(base)
    base_digest = sha256(base)
    root = Path(__file__).resolve().parent
    tree_path = initial_tree_path.resolve()
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    adaptive_cube_tree.audit_tree(tree, nvars=nvars)
    initial_leaves = adaptive_cube_tree.leaf_cubes(tree)
    if len(initial_leaf_ids) != len(set(initial_leaf_ids)):
        raise ValueError("duplicate initial leaf ID")
    if any(leaf_id not in initial_leaves for leaf_id in initial_leaf_ids):
        raise ValueError("initial leaf ID is absent from the initial tree")
    queue = [initial_leaves[leaf_id] for leaf_id in initial_leaf_ids]
    completed_rounds: list[dict[str, object]] = []

    for round_index in range(first_round, last_round + 1):
        if not queue:
            break
        output_tree_path = (
            root / "proofs/adaptive" / f"{prefix}-r{round_index}.tree.json"
        )
        campaign = root / "proofs/adaptive" / f"{prefix}-r{round_index}"
        manifest_path = campaign / "manifest.json"
        verdict_path = campaign / "verdicts.jsonl"
        if not (
            output_tree_path.is_file()
            and manifest_path.is_file()
            and verdict_path.is_file()
        ):
            break

        before_tree = json.loads(tree_path.read_text(encoding="utf-8"))
        adaptive_cube_tree.audit_tree(before_tree, nvars=nvars)
        before_leaves = adaptive_cube_tree.leaf_cubes(before_tree)
        target = queue[0]
        if list(before_leaves.values()).count(target) != 1:
            raise ValueError(
                f"round {round_index} target does not occur exactly once"
            )

        after_tree = json.loads(output_tree_path.read_text(encoding="utf-8"))
        adaptive_cube_tree.audit_tree(after_tree, nvars=nvars)
        after_leaves = adaptive_cube_tree.leaf_cubes(after_tree)
        unchanged = set(before_leaves.values()) - {target}
        descendants = {
            leaf_id: literals
            for leaf_id, literals in after_leaves.items()
            if len(literals) > len(target)
            and literals[: len(target)] == target
        }
        if (
            not descendants
            or not unchanged <= set(after_leaves.values())
            or set(after_leaves.values()) != unchanged | set(descendants.values())
        ):
            raise ValueError(
                f"round {round_index} is not an exact one-leaf refinement"
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("schema")
            != "erdos176.adaptive-cube-campaign.v1"
            or manifest.get("base_sha256") != base_digest
            or Path(str(manifest.get("tree"))).resolve()
            != output_tree_path.resolve()
            or manifest.get("tree_sha256") != sha256(output_tree_path)
            or manifest.get("cube_count") != len(after_leaves)
        ):
            raise ValueError(f"round {round_index} manifest is inconsistent")

        latest = latest_verdicts(verdict_path)
        if set(latest) != set(descendants):
            break
        unresolved: list[tuple[int, ...]] = []
        for leaf_id, literals in descendants.items():
            verdict = latest[leaf_id]
            raw_literals = verdict.get("literals")
            if (
                not isinstance(raw_literals, list)
                or any(type(item) is not int for item in raw_literals)
                or tuple(raw_literals) != literals
            ):
                raise ValueError(
                    f"round {round_index} verdict literals are inconsistent"
                )
            if verdict.get("status") not in CLOSED:
                unresolved.append(literals)

        queue.pop(0)
        queue.extend(unresolved)
        tree_path = output_tree_path
        completed_rounds.append(
            {
                "round": round_index,
                "tree": str(tree_path),
                "descendants": len(descendants),
                "unresolved": len(unresolved),
                "queued": len(queue),
            }
        )

    final_tree = json.loads(tree_path.read_text(encoding="utf-8"))
    final_leaves = adaptive_cube_tree.leaf_cubes(final_tree)
    queue_records = []
    for literals in queue:
        matching = [
            leaf_id
            for leaf_id, observed in final_leaves.items()
            if observed == literals
        ]
        if len(matching) != 1:
            raise ValueError("queued prefix is not a unique final-tree leaf")
        queue_records.append(
            {"leaf": matching[0], "literals": list(literals)}
        )

    next_round = (
        completed_rounds[-1]["round"] + 1
        if completed_rounds
        else first_round
    )
    return {
        "schema": "erdos176.adaptive-refinement-recovery.v1",
        "base": str(base),
        "base_sha256": base_digest,
        "tree": str(tree_path),
        "tree_sha256": sha256(tree_path),
        "completed_rounds": completed_rounds,
        "next_round": next_round,
        "queue": queue_records,
        "complete": not queue_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--initial-tree", type=Path, required=True)
    parser.add_argument(
        "--initial-leaf", type=int, action="append", required=True
    )
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--first-round", type=int, default=1)
    parser.add_argument("--last-round", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = recover(
        base=args.base,
        initial_tree_path=args.initial_tree,
        initial_leaf_ids=args.initial_leaf,
        prefix=args.prefix,
        first_round=args.first_round,
        last_round=args.last_round,
    )
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite {args.output}")
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
