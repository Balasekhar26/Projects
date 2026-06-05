from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import load_board, load_measurements
from .engine import DiagnosticEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PCB Doctor diagnostic CLI")
    parser.add_argument("--board", default="data/sample-board.json", help="Board model JSON")
    parser.add_argument("--measurements", default="data/sample-measurements.json", help="Measurements JSON")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    board_path = _resolve(root, args.board)
    measurements_path = _resolve(root, args.measurements)

    board = load_board(board_path)
    measurements = load_measurements(measurements_path)
    report = DiagnosticEngine(board).diagnose(measurements)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    print(report.summary)
    if report.root_cause_path:
        print("Trace:", " -> ".join(report.root_cause_path))
    for finding in report.findings:
        print(f"\n[{finding.severity.upper()}] {finding.node_id}: {finding.message}")
        print(f"Kind: {finding.kind} | Score: {finding.score}")
        print("Probable causes:", ", ".join(finding.probable_causes))
        for step in finding.next_steps:
            print(f"- {step}")
    return 0 if report.findings else 0


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


if __name__ == "__main__":
    raise SystemExit(main())
