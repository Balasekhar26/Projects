#!/usr/bin/env python3
"""
Offline checkpoint timing analysis — run after each test, never during.
Reads ~/Desktop/checkpoint_timing.jsonl and prints:
  - per-phase: median, p95, p99, max (seconds)
  - outlier detection: any record where any phase is > 3x its own median
  - total duration trend: first 10% vs last 10% of records (drift check)

Usage:
    python3 analyze_checkpoint_timing.py
    python3 analyze_checkpoint_timing.py --tail 20   # last 20 records only
    python3 analyze_checkpoint_timing.py --json       # machine-readable output
"""

import argparse
import json
import os
import sys
from pathlib import Path


PHASES = [
    "gpu_sync_s",
    "model_state_dict_s",
    "optimizer_state_dict_s",
    "state_to_cpu_s",
    "object_assembly_s",
    "torch_save_s",
    "fsync_s",
    "checkpoint_total_s",
]

PHASE_LABELS = {
    "gpu_sync_s":              "GPU synchronize       ",
    "model_state_dict_s":      "model.state_dict()    ",
    "optimizer_state_dict_s":  "optimizer.state_dict()",
    "state_to_cpu_s":          "state_to_cpu() [DMA]  ",
    "object_assembly_s":       "Python obj assembly   ",
    "torch_save_s":            "torch.save() [disk]   ",
    "fsync_s":                 "os.fsync()            ",
    "checkpoint_total_s":      "TOTAL                 ",
}


def percentile(values, p):
    if not values:
        return float("nan")
    s = sorted(values)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def load_records(path: Path, tail: int = None):
    if not path.exists():
        print(f"ERROR: {path} not found. Has a checkpoint test been run yet?")
        sys.exit(1)
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if tail is not None:
        records = records[-tail:]
    return records


def analyze(records, as_json=False):
    if not records:
        print("No records found.")
        return

    phase_values = {p: [] for p in PHASES}
    for r in records:
        for p in PHASES:
            if p in r:
                phase_values[p].append(r[p])

    stats = {}
    for p in PHASES:
        vals = phase_values[p]
        if not vals:
            continue
        stats[p] = {
            "n":      len(vals),
            "median": percentile(vals, 50),
            "p95":    percentile(vals, 95),
            "p99":    percentile(vals, 99),
            "max":    max(vals),
            "min":    min(vals),
        }

    if as_json:
        print(json.dumps(stats, indent=2))
        return

    # ── Header ────────────────────────────────────────────────────────────────
    n_records = len(records)
    steps = [r.get("step", "?") for r in records]
    step_range = f"{steps[0]} → {steps[-1]}" if steps else "?"
    print(f"\n{'='*70}")
    print(f"  Checkpoint Timing Analysis")
    print(f"  Records: {n_records}   Steps: {step_range}")
    print(f"{'='*70}")

    # ── Per-phase table ────────────────────────────────────────────────────────
    print(f"\n  {'Phase':<26}  {'n':>5}  {'median':>8}  {'p95':>8}  {'p99':>8}  {'max':>8}")
    print(f"  {'-'*26}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for p in PHASES:
        if p not in stats:
            continue
        s = stats[p]
        label = PHASE_LABELS.get(p, p)
        flag = "  ⚠" if s["max"] > s["median"] * 3 and s["median"] > 0.01 else ""
        print(f"  {label}  {s['n']:>5d}  {s['median']:>7.3f}s  {s['p95']:>7.3f}s  {s['p99']:>7.3f}s  {s['max']:>7.3f}s{flag}")

    # ── Outlier detection ─────────────────────────────────────────────────────
    outliers = []
    medians = {p: stats[p]["median"] for p in stats}
    for r in records:
        flags = []
        for p in PHASES:
            if p not in r or p not in medians:
                continue
            if medians[p] > 0.01 and r[p] > medians[p] * 3:
                flags.append(f"{PHASE_LABELS.get(p,p).strip()}={r[p]:.3f}s ({r[p]/medians[p]:.1f}×median)")
        if flags:
            outliers.append((r.get("step", "?"), r.get("timestamp", ""), flags))

    if outliers:
        print(f"\n  ⚠  OUTLIERS DETECTED ({len(outliers)} records with any phase > 3× its median):")
        for step, ts, flags in outliers[-10:]:  # show last 10 at most
            print(f"     step={step}  ts={ts}")
            for f in flags:
                print(f"       → {f}")
    else:
        print(f"\n  ✅  No outliers detected (all phases within 3× their own median).")

    # ── Drift check: first 10% vs last 10% ────────────────────────────────────
    n10 = max(1, n_records // 10)
    early = records[:n10]
    late  = records[-n10:]

    print(f"\n  Drift check (first {n10} vs last {n10} records):")
    print(f"  {'Phase':<26}  {'early median':>13}  {'late median':>12}  {'drift':>8}")
    print(f"  {'-'*26}  {'-'*13}  {'-'*12}  {'-'*8}")
    for p in PHASES:
        early_vals = [r[p] for r in early if p in r]
        late_vals  = [r[p] for r in late  if p in r]
        if not early_vals or not late_vals:
            continue
        em = percentile(early_vals, 50)
        lm = percentile(late_vals, 50)
        drift = lm - em
        drift_flag = "  ⚠ GROWING" if drift > 0.5 else ("  ⚠ shrinking" if drift < -0.5 else "")
        print(f"  {PHASE_LABELS.get(p,p)}  {em:>12.3f}s  {lm:>11.3f}s  {drift:>+7.3f}s{drift_flag}")

    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Analyze checkpoint_timing.jsonl")
    parser.add_argument("--path",  default=os.path.expanduser("~/Desktop/checkpoint_timing.jsonl"))
    parser.add_argument("--tail",  type=int, default=None, help="Analyze last N records only")
    parser.add_argument("--json",  action="store_true", help="Output raw stats as JSON")
    args = parser.parse_args()

    records = load_records(Path(args.path), tail=args.tail)
    analyze(records, as_json=args.json)


if __name__ == "__main__":
    main()
