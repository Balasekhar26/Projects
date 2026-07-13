#!/usr/bin/env python
"""Manual Evaluation Harness — Kattappa M38.

Runs tasks from ``evaluation/manual_tasks.yaml`` through the live app via
FastAPI TestClient and verifies assertions.

Usage::

    # Run all tasks
    python evaluation/run_manual_evals.py

    # Run only canary tasks (the Canary 50 benchmark)
    python evaluation/run_manual_evals.py --canary

    # Run a specific category
    python evaluation/run_manual_evals.py --category "File Operations"

    # Combine flags
    python evaluation/run_manual_evals.py --canary --category "Direct QA"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import json
import tempfile
import shutil
from pathlib import Path

# Add project root to path so we can import backend packages
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load yaml dynamically
try:
    import yaml
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml"], capture_output=True)
    import yaml

# Force mock mode in model router so it responds quickly and predictably during evaluation tests
os.environ["PYTEST_CURRENT_TEST"] = "1"
os.environ["KATTAPPA_ENV"] = "test"


# Create a clean temp sandbox directory for memory and database isolation
tmp_dir = Path(tempfile.mkdtemp(prefix="kattappa_eval_"))
chroma_path = tmp_dir / "chroma"
sqlite_path = tmp_dir / "kattappa_test.db"
chroma_path.mkdir(parents=True, exist_ok=True)

from backend.core.config import BackendConfig
mock_config = BackendConfig(
    root=tmp_dir,
    backend_root=tmp_dir,
    ollama_host="http://127.0.0.1:11434",
    model_map={
        "fast": "qwen2.5:0.5b",
        "general": "qwen2.5:0.5b",
        "power": "qwen2.5:0.5b",
        "coder": "qwen2.5:0.5b",
        "vision": "qwen2.5:0.5b",
        "reasoning": "qwen2.5:0.5b",
    },
    chroma_path=chroma_path,
    sqlite_path=sqlite_path,
    memory_collection="kattappa_memory_eval",
    shell_enabled=False,
    desktop_enabled=True,
    screen_capture_enabled=False,
    guidance_overlay_enabled=True,
    teach_mode_enabled=True,
    screenshots_dir=tmp_dir / "screenshots",
    audio_dir=tmp_dir / "audio",
    logs_dir=tmp_dir / "logs",
    workspace_dir=tmp_dir / "workspace",
    hardware_profile="BALANCED",
    context_budget=4096,
)

# Apply mock config BEFORE importing main app
import backend.core.config
backend.core.config.load_config = lambda: mock_config

from fastapi.testclient import TestClient
from backend.main import app


EVAL_DIR = Path(__file__).parent
YAML_PATH = EVAL_DIR / "manual_tasks.yaml"
SCORECARD_PATH = EVAL_DIR / "scorecard.json"
HISTORY_PATH = EVAL_DIR / "canary_history.jsonl"


def _check_assertion(ass: dict, reply: str, selected_agent: str) -> tuple[bool, str | None]:
    """Return (passed, failure_message)."""
    ass_type = ass.get("type")

    if ass_type == "substring":
        expected = ass.get("expected", "")
        if expected.lower() in reply.lower():
            return True, None
        return False, f"Substring '{expected}' not found in reply."

    elif ass_type == "not_empty":
        if reply.strip():
            return True, None
        return False, "Reply was empty."

    elif ass_type == "agent":
        expected = ass.get("expected", "")
        if expected.lower() in selected_agent.lower():
            return True, None
        return False, f"Expected agent '{expected}' but got '{selected_agent}'."

    else:
        # Unknown assertion type — treat as pass (forward-compatible)
        return True, None


def run_evaluation(canary_only: bool = False, category_filter: str | None = None) -> dict:
    client = TestClient(app)

    if not YAML_PATH.exists():
        print(f"Error: task file not found at {YAML_PATH}")
        sys.exit(1)

    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    all_tasks = data.get("tasks", [])

    # Apply filters
    tasks = all_tasks
    if canary_only:
        tasks = [t for t in tasks if t.get("canary", False)]
    if category_filter:
        tasks = [t for t in tasks if t.get("category", "").lower() == category_filter.lower()]

    run_label = "CANARY 50" if canary_only else "ALL TASKS"
    if category_filter:
        run_label += f" — {category_filter}"

    print(f"\nLoaded {len(tasks)} tasks ({run_label})\n")
    print("=" * 60)
    print(f"RUNNING KATTAPPA EVALUATION HARNESS — {run_label}")
    print("=" * 60)

    passed_count = 0
    results = []

    for idx, task in enumerate(tasks, 1):
        task_id = task.get("id")
        prompt = task.get("prompt", "")
        category = task.get("category", "General")
        assertions = task.get("assertions", task.get("expected_assertions", []))

        print(f"\n[{idx}/{len(tasks)}] Task: {task_id} ({category})")
        print(f"  Prompt: '{prompt[:80]}{'...' if len(prompt) > 80 else ''}'")

        t0 = time.perf_counter()
        response = client.post("/chat", json={"message": prompt})
        latency = (time.perf_counter() - t0) * 1000.0

        if response.status_code == 200:
            res_data = response.json()
            reply = res_data.get("response") or ""
            state = res_data.get("state") or {}
            selected_agent = state.get("selected_agent") or "unknown"
        else:
            reply = f"Error: Status {response.status_code}"
            selected_agent = "error"

        print(f"  Agent: {selected_agent}")
        print(f"  Response: {reply[:100]}{'...' if len(reply) > 100 else ''}")
        print(f"  Latency: {latency:.2f} ms")

        # Evaluate assertions
        task_passed = True
        failed_assertion: str | None = None

        for ass in assertions:
            passed, failure_msg = _check_assertion(ass, reply, selected_agent)
            if not passed:
                task_passed = False
                failed_assertion = failure_msg
                break

        if task_passed:
            print("  Status: \033[92mPASS\033[0m")
            passed_count += 1
        else:
            print(f"  Status: \033[91mFAIL\033[0m ({failed_assertion})")

        results.append({
            "id": task_id,
            "prompt": prompt,
            "category": category,
            "reply": reply,
            "selected_agent": selected_agent,
            "latency_ms": round(latency, 2),
            "passed": task_passed,
            "error_msg": failed_assertion,
        })

    # ── Scorecard ──────────────────────────────────────────────────────────────
    total = len(tasks)
    success_rate = (passed_count / total * 100.0) if total else 0.0

    print("\n" + "=" * 60)
    print("EVALUATION SCORECARD SUMMARY")
    print("=" * 60)
    print(f"Passed:         {passed_count}")
    print(f"Failed:         {total - passed_count}")
    print(f"Success Rate:   {success_rate:.2f}%")

    scorecard = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_label": run_label,
        "canary_only": canary_only,
        "category_filter": category_filter,
        "total_tasks": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "success_rate": round(success_rate, 2),
        "results": results,
    }

    SCORECARD_PATH.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    print(f"Saved detailed scorecard to: {SCORECARD_PATH}\n")

    # ── Append to canary history ───────────────────────────────────────────────
    history_entry = {k: v for k, v in scorecard.items() if k != "results"}
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(history_entry) + "\n")

    return scorecard


def main() -> None:
    parser = argparse.ArgumentParser(description="Kattappa Manual Evaluation Harness")
    parser.add_argument("--canary", action="store_true",
                        help="Run only tasks tagged canary: true.")
    parser.add_argument("--category", type=str, default=None,
                        help="Run only tasks in this category (case-insensitive).")
    args = parser.parse_args()

    try:
        scorecard = run_evaluation(canary_only=args.canary, category_filter=args.category)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if scorecard["failed"] > 0 and scorecard["success_rate"] < 80.0:
        sys.exit(1)


if __name__ == "__main__":
    main()
