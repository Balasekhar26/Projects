"""CLI entry point for the Action Runtime performance gate."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from backend.core.action.benchmark import ActionBenchmarkConfig, ActionRuntimeBenchmark


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--runs", type=int, default=11)
    parser.add_argument("--tolerance", type=float, default=0.15)
    parser.add_argument("--memory-ceiling-mb", type=float, default=8192.0)
    parser.add_argument("--record", action="store_true")
    return parser


def main() -> int:
    """Run the benchmark, write its report, and return gate status."""

    args = build_parser().parse_args()
    config = ActionBenchmarkConfig(
        warmup_runs=args.warmups,
        sample_runs=args.runs,
        regression_tolerance=args.tolerance,
        memory_ceiling_mb=args.memory_ceiling_mb,
    )
    with tempfile.TemporaryDirectory(prefix="kattappa-action-benchmark-") as directory:
        benchmark = ActionRuntimeBenchmark(directory, config=config)
        result = benchmark.run(args.history)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        if args.record and args.history is not None and result.passed:
            benchmark.record(result, args.history)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
