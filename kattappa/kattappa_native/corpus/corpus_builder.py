#!/usr/bin/env python3
"""
KM-5.0.5 — Corpus Builder Orchestrator
========================================
Runs the full corpus acquisition pipeline end-to-end:

    download → preprocess → dedup → budget report

Usage:
    # Fast synthetic-only run (no network required, ~30 seconds)
    PYTHONPATH=. python3 kattappa_native/corpus/corpus_builder.py --sources synthetic

    # Full run (network required, ~30-60 minutes)
    PYTHONPATH=. python3 kattappa_native/corpus/corpus_builder.py \\
        --sources wikipedia_en wikipedia_te gutenberg synthetic \\
        --max-articles 3000

    # Wikipedia English only (fastest meaningful corpus)
    PYTHONPATH=. python3 kattappa_native/corpus/corpus_builder.py \\
        --sources wikipedia_en --max-articles 5000
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

WORKSPACE_ROOT  = Path(__file__).parent.parent.parent
CORPUS_DIR      = Path(__file__).parent
RAW_DIR         = CORPUS_DIR / "raw"
PROCESSED_DIR   = CORPUS_DIR / "processed"
DEDUPED_DIR     = CORPUS_DIR / "deduped"
MANIFEST_PATH   = CORPUS_DIR / "corpus_manifest.json"


def run_step(step_name: str, module: str, extra_args: list[str]) -> bool:
    """Run a corpus pipeline step as a subprocess."""
    print(f"\n{'='*60}")
    print(f"  ▶  {step_name}")
    print(f"{'='*60}")
    cmd = [
        sys.executable, "-m", module
    ] + extra_args
    # Use module-path style: replace . with /
    cmd = [sys.executable, str(CORPUS_DIR / f"{module}.py")] + extra_args
    result = subprocess.run(cmd, cwd=str(WORKSPACE_ROOT), env={
        **__import__("os").environ, "PYTHONPATH": str(WORKSPACE_ROOT)
    })
    if result.returncode != 0:
        print(f"\n  ❌  Step '{step_name}' failed.")
        return False
    return True


def print_final_summary():
    """Print token budget summary from all deduped files."""
    from kattappa_native.corpus.token_budget_planner import scan_workspace, compute_gap

    manifest = json.loads(MANIFEST_PATH.read_text())
    available, file_reports = scan_workspace(WORKSPACE_ROOT)

    total_available = sum(available.values())
    alpha_target = manifest["alpha_run"]["target_total_tokens"]
    pct = round(100 * total_available / alpha_target, 2)

    print(f"\n{'='*60}")
    print(f"  📊  CORPUS BUILD COMPLETE")
    print(f"{'='*60}")
    print(f"  Total tokens available : {total_available:>15,}")
    print(f"  Alpha target           : {alpha_target:>15,}")
    print(f"  Fill rate              : {pct:>15.2f}%")

    if pct >= 33:
        print(f"\n  ✅  Corpus is sufficient for tokenizer training (>33% of target).")
        print(f"  ✅  Corpus is sufficient for Kattappa-20M Alpha run.")
        if pct >= 100:
            print(f"  ✅  Full Alpha run can begin.")
    else:
        print(f"\n  ⚠  More data needed before tokenizer training.")
        print(f"      Run again with --max-articles 5000 or add more sources.")

    print(f"\n  Next steps:")
    print(f"    1. pip install sentencepiece")
    print(f"    2. python3 kattappa_native/tokenizer/train_tokenizer.py")
    print(f"    3. python3 kattappa_native/tokenizer/tokenizer_eval.py")
    print(f"    4. python3 kattappa_native/training/trainer.py \\")
    print(f"           --n-layers 6 --n-heads 6 --d-model 384 --steps 5000")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Kattappa Corpus Builder")
    parser.add_argument(
        "--sources", nargs="+",
        choices=["wikipedia_en", "wikipedia_te", "gutenberg", "synthetic", "workspace_code"],
        default=["synthetic", "workspace_code"],
        help="Data sources to download (default: synthetic and workspace_code)",
    )
    parser.add_argument("--max-articles",    type=int, default=2000)
    parser.add_argument("--max-books",       type=int, default=30)
    parser.add_argument("--synthetic-count", type=int, default=2000)
    parser.add_argument("--skip-download",   action="store_true",
                        help="Skip download step (use existing raw/ files)")
    parser.add_argument("--skip-preprocess", action="store_true",
                        help="Skip preprocess step (use existing processed/ files)")
    args = parser.parse_args()

    print(f"\n🚀  Kattappa Corpus Builder")
    print(f"    Sources          : {args.sources}")
    print(f"    Max articles     : {args.max_articles}")
    print(f"    Synthetic count  : {args.synthetic_count}")
    print(f"    Started at       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Step 1: Download ──────────────────────────────────────────────────────
    if not args.skip_download:
        ok = run_step(
            "Step 1/3: Downloading source data",
            "downloader",
            [
                "--sources", *args.sources,
                "--output-dir", str(RAW_DIR),
                "--max-articles", str(args.max_articles),
                "--max-books",    str(args.max_books),
                "--synthetic-count", str(args.synthetic_count),
            ],
        )
        if not ok:
            sys.exit(1)
    else:
        print(f"\n  ⏭  Skipping download (--skip-download)")

    # ── Step 2: Preprocess ────────────────────────────────────────────────────
    if not args.skip_preprocess:
        ok = run_step(
            "Step 2/3: Preprocessing (clean + chunk)",
            "preprocessor",
            [
                "--input-dir",  str(RAW_DIR),
                "--output-dir", str(PROCESSED_DIR),
            ],
        )
        if not ok:
            sys.exit(1)
    else:
        print(f"\n  ⏭  Skipping preprocess (--skip-preprocess)")

    # ── Step 3: Deduplication ─────────────────────────────────────────────────
    ok = run_step(
        "Step 3/3: Deduplication",
        "deduplicator",
        [
            "--input-dir",  str(PROCESSED_DIR),
            "--output-dir", str(DEDUPED_DIR),
        ],
    )
    if not ok:
        sys.exit(1)

    # ── Final summary ─────────────────────────────────────────────────────────
    print_final_summary()


if __name__ == "__main__":
    main()
