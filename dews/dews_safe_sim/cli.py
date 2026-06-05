from __future__ import annotations

import argparse
from pathlib import Path

from .data import load_readings
from .engine import SafetySimulation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DEWS safe-domain simulation CLI")
    parser.add_argument("--readings", default="data/sample-readings.json", help="Sensor reading JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    path = Path(args.readings)
    if not path.is_absolute():
        path = root / path
    readings = load_readings(path)
    findings = SafetySimulation().analyze(readings)
    if not findings:
        print("No safety findings from the provided readings.")
        return 0
    for finding in findings:
        print(f"[{finding.level.upper()}] {finding.metric}: {finding.message}")
        print(f"Observed: {finding.observed}")
        print(f"Protective action: {finding.protective_action}")
        print(f"Recommendation: {finding.recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
