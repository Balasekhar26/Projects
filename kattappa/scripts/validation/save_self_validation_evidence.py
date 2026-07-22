import os
import sys
import json
import time
import hashlib
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TARGET_FILES = [
    "backend/tests/test_sharded_validation.py",
    "scripts/validation/pytest_result_plugin.py",
    "scripts/validation/collect_test_inventory.py",
    "scripts/validation/build_test_shards.py",
    "scripts/validation/execute_pytest_shard.py",
    "scripts/validation/run_test_shard.py",
    "scripts/validation/aggregate_test_results.py",
    "scripts/validation/run_full_suite_sharded.py",
    "scripts/validation/save_self_validation_evidence.py",
    "scripts/validation/verify_commit_scope.py",
    "scripts/validation/test_shard_policy.yaml",
    "scripts/validation/k-r0.5-scope-policy.yaml",
    "requirements.txt",
]


def compute_source_fingerprint() -> tuple[str, dict[str, str]]:
    runner_files_sha256 = {}
    hasher_combined = hashlib.sha256()

    for f in TARGET_FILES:
        f_path = PROJECT_ROOT / f
        if not f_path.exists():
            raise FileNotFoundError(f"Release-critical source file not found for fingerprinting: {f}")
        file_bytes = f_path.read_bytes()
        f_hash = hashlib.sha256(file_bytes).hexdigest()
        runner_files_sha256[f] = f_hash
        hasher_combined.update(f.encode("utf-8"))
        hasher_combined.update(f_hash.encode("utf-8"))

    return hasher_combined.hexdigest(), runner_files_sha256


def get_requirements_hash() -> str:
    req_file = PROJECT_ROOT / "requirements.txt"
    if req_file.exists():
        return hashlib.sha256(req_file.read_bytes()).hexdigest()
    return "missing-requirements-file"


def get_environment_hash(python_exe: str) -> str:
    env_str = f"{sys.version}|{sys.platform}|{python_exe}"
    return hashlib.sha256(env_str.encode("utf-8")).hexdigest()


def get_git_status() -> list[str]:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True
        )
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception as e:
        return [f"git-error: {e}"]


def get_git_commit(ref: str = "HEAD") -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", ref],
            cwd=str(PROJECT_ROOT),
            text=True
        ).strip()
    except Exception as e:
        return f"git-error: {e}"


def get_git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(PROJECT_ROOT),
            text=True
        ).strip()
    except Exception:
        return "unknown"


def parse_junit_xml(xml_path: Path) -> dict[str, int]:
    if not xml_path.exists():
        raise FileNotFoundError(f"JUnit XML result file missing: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    tests = int(root.attrib.get("tests", 0))
    failures = int(root.attrib.get("failures", 0))
    errors = int(root.attrib.get("errors", 0))
    skipped = int(root.attrib.get("skipped", 0))
    passed = tests - (failures + errors + skipped)

    return {
        "collection_count": tests,
        "passed": passed,
        "failed": failures,
        "errors": errors,
        "skipped": skipped
    }


def execute_self_validation(run_number: int, python_exe: str):
    print(f"=== Starting Release-Grade Self-Validation Run {run_number} ===")
    started_at = datetime.now(timezone.utc).isoformat()

    # Preflight Checks
    status_before = get_git_status()
    source_tree_hash_before, files_sha_before = compute_source_fingerprint()
    candidate_commit = get_git_commit("HEAD")
    remote_branch = f"origin/{get_git_branch()}"
    remote_commit = get_git_commit(remote_branch)

    # Determine Destination Directory under Kattappa project container
    val_root = os.environ.get("KATTAPPA_VALIDATION_ROOT")
    if val_root:
        base_dir = Path(val_root)
    else:
        base_dir = PROJECT_ROOT / "validation-runs"

    dest_dir = base_dir / "self-validation-runs" / f"run-{run_number}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    junit_xml = dest_dir / "junit-results.xml"

    # Execute Pytest with JUnit XML output
    test_file = PROJECT_ROOT / "backend" / "tests" / "test_sharded_validation.py"
    cmd = [
        python_exe, "-m", "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        f"--junitxml={junit_xml}"
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_ENV"] = "test"

    t0 = time.time()
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    duration = time.time() - t0
    completed_at = datetime.now(timezone.utc).isoformat()

    status_after = get_git_status()
    source_tree_hash_after, files_sha_after = compute_source_fingerprint()

    # Parse machine-readable counts
    counts = parse_junit_xml(junit_xml)

    # Evaluate Validation Rules
    valid = True
    validation_reasons = []

    if not candidate_commit or "error" in candidate_commit:
        valid = False
        validation_reasons.append("candidate_commit is missing or invalid")

    if candidate_commit != remote_commit:
        valid = False
        validation_reasons.append(f"remote commit ({remote_commit}) differs from candidate commit ({candidate_commit})")

    if counts["collection_count"] == 0:
        valid = False
        validation_reasons.append("collected count is zero")

    if source_tree_hash_before != source_tree_hash_after:
        valid = False
        validation_reasons.append("source_tree_hash modified during execution")

    if status_before:
        valid = False
        validation_reasons.append(f"worktree dirty before run: {status_before}")

    if status_after:
        valid = False
        validation_reasons.append(f"worktree dirty after run: {status_after}")

    if proc.returncode != 0:
        valid = False
        validation_reasons.append(f"exit_code non-zero ({proc.returncode})")

    if counts["passed"] != counts["collection_count"]:
        valid = False
        validation_reasons.append(f"passed count ({counts['passed']}) != collected count ({counts['collection_count']})")

    evidence = {
        "run_number": run_number,
        "candidate_commit": candidate_commit,
        "remote_commit": remote_commit,
        "branch": get_git_branch(),
        "python_version": sys.version,
        "python_executable": python_exe,
        "requirements_hash": get_requirements_hash(),
        "environment_hash": get_environment_hash(python_exe),
        "source_tree_hash": source_tree_hash_before,
        "collection_count": counts["collection_count"],
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
        "exit_code": proc.returncode,
        "worktree_status_before": status_before,
        "worktree_status_after": status_after,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": round(duration, 2),
        "valid": valid,
        "validation_reasons": validation_reasons,
        "runner_files_sha256": files_sha_before,
    }

    # Save outputs
    (dest_dir / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (dest_dir / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (dest_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")

    print(f"\nSaved self-validation evidence for Run {run_number} under {dest_dir}")
    print(f"  Valid: {valid} | Passed: {counts['passed']}/{counts['collection_count']} | Candidate: {candidate_commit[:12]}")

    if not valid:
        print(f"[FAILED] Validation failed: {', '.join(validation_reasons)}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Release-Grade Self-Validation Evidence Recorder")
    parser.add_argument("--run-number", type=int, required=True, choices=[1, 2, 3], help="Run number (1, 2, or 3)")
    parser.add_argument("--python-exe", type=str, required=True, help="Path to Python interpreter")
    args = parser.parse_args()
    execute_self_validation(args.run_number, args.python_exe)
