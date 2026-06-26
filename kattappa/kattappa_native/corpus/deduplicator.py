#!/usr/bin/env python3
"""
KM-5.0.5 — Corpus Deduplicator
================================
Removes duplicate text chunks from the processed corpus using
a truncated SHA-256 fingerprint set (in-memory bloom-filter-style).

Features:
  - Idempotent: safe to re-run on partially-processed data
  - Per-file and global deduplication
  - Reports dedup ratio per source

Usage:
    PYTHONPATH=. python3 kattappa_native/corpus/deduplicator.py \\
        --input-dir  kattappa_native/corpus/processed \\
        --output-dir kattappa_native/corpus/deduped
"""

import re
import json
import hashlib
import argparse
from pathlib import Path
from typing import Set

# Characters to normalise before hashing (collapse whitespace, lowercase)
_NORM_RE = re.compile(r"\s+")


def fingerprint(text: str, length: int = 16) -> str:
    """
    Compute a truncated SHA-256 fingerprint of normalised text.
    length=16 bytes → 128-bit hash → collision probability negligible
    for corpus sizes < 1B records.
    """
    normalised = _NORM_RE.sub(" ", text.lower()).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:length * 2]


def dedup_file(input_path: Path, output_path: Path,
               global_seen: Set[str]) -> tuple[int, int]:
    """
    Deduplicates one JSONL file against global_seen fingerprint set.
    Returns (total_read, total_written).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_read = 0
    total_written = 0

    with open(input_path, "r", encoding="utf-8", errors="replace") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:

        for line in fin:
            line = line.strip()
            if not line:
                continue
            total_read += 1

            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            text = rec.get("text", "")
            if len(text) < 20:
                continue

            fp = fingerprint(text)
            if fp in global_seen:
                continue  # duplicate — skip

            global_seen.add(fp)
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total_written += 1

    return total_read, total_written


def run_dedup(input_dir: Path, output_dir: Path) -> int:
    """Deduplicates all JSONL files in input_dir, writing to output_dir."""
    jsonl_files = sorted(input_dir.rglob("*.jsonl"))
    if not jsonl_files:
        print(f"  ⚠  No JSONL files found in {input_dir}")
        return 0

    global_seen: Set[str] = set()
    total_written = 0
    total_read    = 0

    print(f"\n  {'File':<48} {'Read':>8} {'Written':>8} {'Dedup%':>8}")
    print(f"  {'-'*48} {'-'*8} {'-'*8} {'-'*8}")

    for path in jsonl_files:
        rel = path.relative_to(input_dir)
        out_path = output_dir / rel
        n_read, n_written = dedup_file(path, out_path, global_seen)
        dedup_ratio = 100 * (1 - n_written / max(n_read, 1))
        print(f"  {str(rel):<48} {n_read:>8,} {n_written:>8,} {dedup_ratio:>7.1f}%")
        total_read    += n_read
        total_written += n_written

    overall_ratio = 100 * (1 - total_written / max(total_read, 1))
    print(f"\n  {'TOTAL':<48} {total_read:>8,} {total_written:>8,} {overall_ratio:>7.1f}%")
    print(f"\n  Unique fingerprints retained: {len(global_seen):,}")
    return total_written


def main():
    parser = argparse.ArgumentParser(description="Kattappa Corpus Deduplicator")
    parser.add_argument("--input-dir",  default="kattappa_native/corpus/processed")
    parser.add_argument("--output-dir", default="kattappa_native/corpus/deduped")
    args = parser.parse_args()

    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    print(f"\n🔁  Kattappa Corpus Deduplicator")
    print(f"    Input : {input_dir}")
    print(f"    Output: {output_dir}\n")

    total = run_dedup(input_dir, output_dir)
    print(f"\n✅  Deduplication complete. {total:,} unique training chunks.\n")


if __name__ == "__main__":
    main()
