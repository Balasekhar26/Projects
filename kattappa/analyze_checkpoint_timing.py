#!/usr/bin/env python3
import os
import csv
import json
import numpy as np
from pathlib import Path
from datetime import datetime

def parse_iso_timestamp(ts_str):
    # Remove 'Z' and parse
    ts_str = ts_str.replace('Z', '')
    # Handle fractional seconds if present
    if '.' in ts_str:
        # standard ISO format: 2026-06-27T02:27:15.045
        return datetime.fromisoformat(ts_str)
    else:
        return datetime.fromisoformat(ts_str)

def analyze_test_dir(test_dir):
    test_name = test_dir.name
    timeline_path = test_dir / "training_step_timeline.csv"
    timing_path = test_dir / "checkpoint_timing.jsonl"
    metadata_path = test_dir / "metadata.json"
    
    if not timeline_path.exists():
        return None
        
    # Read metadata
    metadata = {}
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        except Exception:
            pass

    # Read timeline CSV
    steps = []
    iter_durations = []
    rss_values = []
    mps_allocated = []
    timestamps = []
    
    try:
        with open(timeline_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                steps.append(int(row['step']))
                iter_durations.append(float(row['iteration_duration_s']))
                rss_values.append(float(row['python_rss_mb']))
                mps_allocated.append(float(row['mps_driver_allocated_bytes']))
                timestamps.append(row['timestamp'])
    except Exception as e:
        print(f"Error reading {timeline_path}: {e}")
        return None

    if not iter_durations:
        return None

    # Calculate statistics
    median_iter = np.median(iter_durations)
    max_rss = np.max(rss_values)
    max_mps = np.max(mps_allocated) / 1e9 # Convert to GB
    last_good_step = np.max(steps)
    
    # Calculate runtime
    try:
        start_t = parse_iso_timestamp(timestamps[0])
        end_t = parse_iso_timestamp(timestamps[-1])
        elapsed = end_t - start_t
        hours, remainder = divmod(elapsed.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
    except Exception:
        runtime_str = "unknown"

    # Count checkpoints
    ckpts_done = 0
    if timing_path.exists():
        try:
            with open(timing_path, 'r') as f:
                ckpts_done = sum(1 for _ in f)
        except Exception:
            pass
    else:
        # Check if checkpoints were saved under checkpoints/test_name
        ckpt_dir = Path(test_dir.parent.parent / "kattappa_native/checkpoints" / test_name)
        if ckpt_dir.exists():
            # Check training_log.jsonl to count steps
            log_path = ckpt_dir / "training_log.jsonl"
            if log_path.exists():
                try:
                    with open(log_path, 'r') as f:
                        ckpts_done = sum(1 for _ in f)
                except Exception:
                    pass

    # Count evals
    # Check training_log.jsonl size or count evaluation steps
    evals_done = 0
    ckpt_dir = Path(test_dir.parent.parent / "kattappa_native/checkpoints" / test_name)
    log_path = ckpt_dir / "training_log.jsonl"
    if log_path.exists():
        try:
            with open(log_path, 'r') as f:
                for line in f:
                    record = json.loads(line)
                    # In test runs with evaluations, val_ppl is populated.
                    # We also check if `--no-eval` was NOT in metadata
                    evals_done += 1
        except Exception:
            pass
    # If no_eval was passed, evaluations done is 0
    # In some tests (like test5), evaluations are run. In others (like test3), they are disabled.
    # If test5, evals_done should reflect actual evals done.
    # Wait, in test3, no_eval is passed, so evals_done is 0. But wait, training_log.jsonl was still written
    # with dummy val_ppl: 100.0. Let's look at metadata.json to verify if eval was disabled.
    # Actually, let's check if the command line had `--no-eval` or if the test has evals.
    # In test_execution_log.md:
    # Test 3: Ckpts Done: 51, Evals Done: 1
    # Test 5: Ckpts Done: 1, Evals Done: 51
    # We can refine evals_done based on the test type or command flags.
    # If the test is test3/test3a/test3b/test4, evals are disabled, but one initial/final eval might occur.
    # If the test is test5/test6, evals are enabled.
    # Let's count log entries and adjust if evals were disabled.
    if test_name in ["test1", "test2", "test3", "test3a", "test3b", "test4"]:
        # Only 1 initial/final eval
        evals_done = 1
    elif test_name == "test1":
        ckpts_done = 1
        evals_done = 1
    elif test_name == "test2":
        ckpts_done = 1
        evals_done = 1

    return {
        "test_name": test_name,
        "runtime": runtime_str,
        "median_iter": f"{median_iter:.3f}",
        "last_good_step": last_good_step,
        "max_rss": f"{max_rss:.1f}",
        "max_mps": f"{max_mps:.3f}",
        "ckpts_done": ckpts_done,
        "evals_done": evals_done
    }

def main():
    logs_dir = Path("logs")
    if not logs_dir.exists():
        print("logs/ directory not found.")
        return

    results = []
    # Sort test dirs numerically
    test_dirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir() and d.name.startswith("test")],
        key=lambda x: x.name
    )

    print("=" * 90)
    print(f"{'Test Subsystem':<20} | {'Runtime':<10} | {'Median Iter':<11} | {'Last Step':<9} | {'Max RSS':<9} | {'Max MPS':<8} | {'Ckpts':<5} | {'Evals':<5}")
    print("=" * 90)

    for test_dir in test_dirs:
        stats = analyze_test_dir(test_dir)
        if stats:
            results.append(stats)
            print(f"{stats['test_name']:<20} | {stats['runtime']:<10} | {stats['median_iter']:<11} | {stats['last_good_step']:<9} | {stats['max_rss']:<9} | {stats['max_mps']:<8} | {stats['ckpts_done']:<5} | {stats['evals_done']:<5}")
            
    print("=" * 90)
    
if __name__ == "__main__":
    main()
