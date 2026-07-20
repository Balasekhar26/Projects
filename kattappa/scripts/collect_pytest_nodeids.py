"""Collect exact pytest node IDs for reproducible suite-diff evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest


class NodeIdCollector:
    """Pytest plugin that records the final post-filter collection."""

    def __init__(self) -> None:
        self.node_ids: tuple[str, ...] = ()
        self.markers_by_node_id: dict[str, frozenset[str]] = {}

    def pytest_collection_finish(self, session: Any) -> None:
        """Capture node IDs after collection and marker deselection."""

        self.node_ids = tuple(item.nodeid for item in session.items)
        self.markers_by_node_id = {
            item.nodeid: frozenset(marker.name for marker in item.iter_markers())
            for item in session.items
        }


def build_parser() -> argparse.ArgumentParser:
    """Build the node-ID evidence command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Optional pytest collection paths")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument(
        "--marker-expression",
        help="Optional pytest -m expression applied before node IDs are saved",
    )
    return parser


def main() -> int:
    """Collect tests and atomically publish sorted, unique node IDs."""

    args = build_parser().parse_args()
    collector = NodeIdCollector()
    pytest_args = [*args.paths, "--collect-only", "-qq"]
    if args.marker_expression:
        pytest_args.extend(("-m", args.marker_expression))
    exit_code = int(pytest.main(pytest_args, plugins=[collector]))
    if exit_code != int(pytest.ExitCode.OK):
        return exit_code

    node_ids = sorted(collector.node_ids)
    if len(node_ids) != len(set(node_ids)):
        raise RuntimeError("duplicate pytest node IDs were collected")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary_path.write_text("\n".join(node_ids) + "\n", encoding="utf-8")
    temporary_path.replace(args.output)
    if args.audit_output is not None:
        audit = build_classification_audit(collector.markers_by_node_id)
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        audit_temporary_path = args.audit_output.with_suffix(
            args.audit_output.suffix + ".tmp"
        )
        audit_temporary_path.write_text(
            json.dumps(audit, indent=2) + "\n",
            encoding="utf-8",
        )
        audit_temporary_path.replace(args.audit_output)
    print(f"Saved {len(node_ids)} node IDs to {args.output}")
    return 0


def build_classification_audit(
    markers_by_node_id: dict[str, frozenset[str]],
) -> dict[str, Any]:
    """Summarize primary classification coverage and secondary traits."""

    primary_names = frozenset({"unit", "integration", "evaluation"})
    secondary_names = frozenset(
        {"safety", "performance", "slow", "network", "hardware", "mutation"}
    )
    primary_counts: Counter[str] = Counter()
    secondary_counts: Counter[str] = Counter()
    missing_primary: list[str] = []
    multiple_primary: dict[str, list[str]] = {}
    for node_id, markers in markers_by_node_id.items():
        primary = sorted(markers & primary_names)
        if not primary:
            missing_primary.append(node_id)
        elif len(primary) > 1:
            multiple_primary[node_id] = primary
        for marker in primary:
            primary_counts[marker] += 1
        for marker in markers & secondary_names:
            secondary_counts[marker] += 1
    return {
        "total": len(markers_by_node_id),
        "primary_counts": dict(sorted(primary_counts.items())),
        "secondary_counts": dict(sorted(secondary_counts.items())),
        "missing_primary_count": len(missing_primary),
        "missing_primary_node_ids": sorted(missing_primary),
        "multiple_primary_count": len(multiple_primary),
        "multiple_primary_node_ids": dict(sorted(multiple_primary.items())),
    }


if __name__ == "__main__":
    raise SystemExit(main())
