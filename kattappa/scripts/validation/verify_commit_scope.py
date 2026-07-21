import sys
import fnmatch
import yaml
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_RUNNER_FILES = [
    "scripts/validation/collect_test_inventory.py",
    "scripts/validation/build_test_shards.py",
    "scripts/validation/run_test_shard.py",
    "scripts/validation/aggregate_test_results.py",
    "scripts/validation/run_full_suite_sharded.py",
    "scripts/validation/test_shard_policy.yaml",
    "scripts/validation/k-r0.5-scope-policy.yaml",
    "scripts/validation/pytest_result_plugin.py"
]

FORBIDDEN_TRACKED_DATA = [
    "backend/data/rbil_metrics.json",
    "backend/data/goals.json",
    "backend/data/world_model.json"
]

def load_scope_policy() -> dict:
    policy_file = PROJECT_ROOT / "scripts" / "validation" / "k-r0.5-scope-policy.yaml"
    if not policy_file.exists():
        raise FileNotFoundError(f"Scope policy file missing: {policy_file}")
    return yaml.safe_load(policy_file.read_text(encoding="utf-8"))

def is_path_allowed(rel_path: str, policy: dict) -> bool:
    # Normalize path separator to forward slash
    norm_path = rel_path.replace("\\", "/")
    
    # Strip leading repository prefix if present
    if norm_path.startswith("kattappa/"):
        norm_path = norm_path[9:]

    all_patterns = policy.get("allowed_paths", []) + policy.get("conditionally_allowed_paths", [])
    
    for pattern in all_patterns:
        norm_pattern = pattern.replace("\\", "/")
        if norm_pattern.startswith("kattappa/"):
            norm_pattern = norm_pattern[9:]
            
        if fnmatch.fnmatch(norm_path, norm_pattern) or fnmatch.fnmatch(norm_path, f"{norm_pattern}/*"):
            return True
        if norm_pattern.endswith("/*") and norm_path.startswith(norm_pattern[:-2]):
            return True
    return False

def audit_commit_scope(base_sha: str = "97d4bd9a5507479b5b5b903a9e09abf4bcc7b709", head_sha: str = "HEAD") -> int:
    try:
        policy = load_scope_policy()
        resolved_head = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "rev-parse", head_sha], text=True).strip()
        subject = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%s", resolved_head], text=True).strip()
        
        print(f"Auditing Commit Scope: {base_sha[:8]}..{resolved_head[:8]} ({subject})")
        errors = []

        # 1. Check all required runner files exist in HEAD via git ls-tree
        tracked_in_head = set(
            subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "ls-tree", "-r", "--name-only", resolved_head], text=True).splitlines()
        )
        for rf in REQUIRED_RUNNER_FILES:
            if rf not in tracked_in_head:
                errors.append(f"Required runner file missing from HEAD ({resolved_head[:8]}): {rf}")

        # 2. Check worktree status for forbidden tracked data modifications
        status_lines = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"], text=True).splitlines()
        for line in status_lines:
            line_clean = line.strip()
            for f in FORBIDDEN_TRACKED_DATA:
                if f in line_clean:
                    errors.append(f"Tracked data file modified in worktree: {f}")

        # 3. Audit all modified files in commit range base..head against scope allowlist
        diff_files = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "diff", "--name-only", f"{base_sha}..{resolved_head}"], text=True).splitlines()
        for f in diff_files:
            rel_f = f.strip()
            if not rel_f:
                continue
            if rel_f in FORBIDDEN_TRACKED_DATA:
                errors.append(f"Forbidden tracked data modification committed in range: {rel_f}")
            if not is_path_allowed(rel_f, policy):
                errors.append(f"File modified in range {base_sha[:8]}..{resolved_head[:8]} is NOT in scope allowlist: {rel_f}")

        # 4. Validate temporary scope exceptions
        exceptions_file = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5" / "scope-exceptions.json"
        if exceptions_file.exists():
            import json
            try:
                exceptions = json.loads(exceptions_file.read_text(encoding="utf-8"))
                for entry in exceptions:
                    path = entry.get("path")
                    req_tests = entry.get("required_tests", [])
                    if not req_tests:
                        errors.append(f"required_tests is empty for temporary exception: {path}")
                    
                    # Scan for test functions in backend/tests
                    validation_test_file = PROJECT_ROOT / "backend" / "tests" / "test_sharded_validation.py"
                    cf_test_file = PROJECT_ROOT / "backend" / "tests" / "test_counterfactuals.py"
                    ti_test_file = PROJECT_ROOT / "backend" / "tests" / "test_trust_isolation.py"
                    re_test_file = PROJECT_ROOT / "backend" / "tests" / "test_reflection_engine.py"
                    
                    all_test_content = ""
                    for tf in [validation_test_file, cf_test_file, ti_test_file, re_test_file]:
                        if tf.exists():
                            all_test_content += tf.read_text(encoding="utf-8")
                            
                    for t in req_tests:
                        if t not in all_test_content:
                            errors.append(f"required test does not exist in backend/tests: {t}")
            except Exception as e:
                errors.append(f"Failed to load or parse scope-exceptions.json: {e}")

        if errors:
            print("\n[FAILED] COMMIT SCOPE VERIFICATION FAILED:")
            for err in errors:
                print(f"  - {err}")
            return 1

        print("\n[PASSED] COMMIT SCOPE VERIFICATION PASSED: All files in range match scope allowlist, 0 tracked data mutations.")
        return 0
    except Exception as e:
        print(f"\n[FAILED] Audit failed with error: {e}")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit K-R0.5 commit scope against allowlist policy")
    parser.add_argument("--base", default="97d4bd9a5507479b5b5b903a9e09abf4bcc7b709", help="Base commit SHA")
    parser.add_argument("--head", default="HEAD", help="Head commit SHA")
    args = parser.parse_args()
    sys.exit(audit_commit_scope(args.base, args.head))
