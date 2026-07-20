"""Populate Superbench Database and Run Sweep.

Seeds the SQLite database with 1000 tasks and executes a representative
sample sweep of tests across all categories.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Enable test mode to allow mock model routing
os.environ["KATTAPPA_TEST_MODE"] = "true"

# Mock cognitive_kernel to bypass full service loops during seeding/verification
sys.modules["backend.core.cognitive_kernel"] = MagicMock()

# Configure PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.superbench_engine import SuperbenchEngine


def main():
    print("Initializing SQLite schema and generating 1000 benchmark tasks...")
    count = SuperbenchEngine.generate_benchmark_tasks()
    print(f"Success! Procedurally generated {count} benchmark tasks.")

    print("\nExecuting sample sweep of tests to populate results and telemetry...")
    tasks = SuperbenchEngine.list_tasks()
    
    # Run 1 task per category (20 categories total) to seed baseline dashboard telemetry
    categories = list(set(t["category"] for t in tasks))
    print(f"Found {len(categories)} categories. Initiating execution sweep...")
    
    success_count = 0
    failure_count = 0
    rejected_count = 0
    
    for cat in sorted(categories):
        cat_tasks = [t for t in tasks if t["category"] == cat]
        if cat_tasks:
            # Pick the intermediate level task template
            task = cat_tasks[len(cat_tasks) // 2]
            print(f"  Running: [{task['id']}] [{task['difficulty']}] {task['prompt']}...")
            try:
                res = SuperbenchEngine.execute_task(task["id"])
                print(f"    -> Result: {res['result']} (Latency: {res['latency']}s, Confidence: {res['confidence']})")
                if res["result"] == "SUCCESS":
                    success_count += 1
                elif res["result"] == "REJECTED":
                    rejected_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                print(f"    -> Error executing task: {e}")
                failure_count += 1
                
    print("\nSweep Complete!")
    print(f"Total executed: {len(categories)}")
    print(f"Successes: {success_count} | Rejected: {rejected_count} | Failures: {failure_count}")


if __name__ == "__main__":
    main()
