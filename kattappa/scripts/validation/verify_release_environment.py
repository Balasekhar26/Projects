import sys
import os
import json
import hashlib
import subprocess
from pathlib import Path

# Get Project Root (assume this script is in scripts/validation)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def get_browser_status():
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        local_app_data = str(Path.home() / "AppData" / "Local")
    
    playwright_dir = Path(local_app_data) / "ms-playwright"
    status = {"chromium": False, "firefox": False, "webkit": False}
    
    if playwright_dir.exists():
        # Iterate over both files/folders, handling force/hidden files by using os.listdir
        try:
            for name in os.listdir(playwright_dir):
                name_lower = name.lower()
                if name_lower.startswith("chromium"):
                    status["chromium"] = True
                elif name_lower.startswith("firefox"):
                    status["firefox"] = True
                elif name_lower.startswith("webkit"):
                    status["webkit"] = True
        except Exception:
            pass
    return status

def check_import(module_name):
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def compute_file_hash(filepath: Path) -> str:
    if not filepath.exists():
        return "missing"
    hasher = hashlib.sha256()
    hasher.update(filepath.read_bytes())
    return hasher.hexdigest()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify Release Environment Preflight")
    parser.add_argument("--bypass-git", action="store_true", help="Bypass git worktree clean check")
    args = parser.parse_args()

    errors = []
    
    # 1. Python Version Check
    py_ver = sys.version_info
    if py_ver.major != 3 or py_ver.minor != 10:
        errors.append(f"Python version mismatch: expected 3.10, got {py_ver.major}.{py_ver.minor}")

    # 2. Pytest Version Check
    pytest_version = "unknown"
    try:
        import pytest
        pytest_version = pytest.__version__
        if pytest_version != "9.0.3":
            errors.append(f"pytest version mismatch: expected 9.0.3, got {pytest_version}")
    except Exception as e:
        errors.append(f"Failed to import pytest: {e}")

    # 3. Import Checks
    packages = ["fastapi", "langgraph", "playwright", "torch", "pandas", "chromadb"]
    import_results = {}
    for pkg in packages:
        status = check_import(pkg)
        import_results[pkg] = status
        if not status:
            errors.append(f"Failed to import package: {pkg}")

    # 4. Environment Consistency Check
    pip_check_status = "FAIL"
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
        if res.returncode == 0:
            pip_check_status = "PASS"
        else:
            pip_check_status = "FAIL"
            errors.append(f"pip check failed: {res.stdout.strip()} {res.stderr.strip()}")
    except Exception as e:
        errors.append(f"Failed to run pip check: {e}")

    # 5. Hash Logs
    req_file = PROJECT_ROOT / "requirements.txt"
    requirements_hash = compute_file_hash(req_file)
    
    freeze_hash = "unknown"
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True)
        freeze_hash = hashlib.sha256(res.stdout.encode("utf-8")).hexdigest()
    except Exception as e:
        errors.append(f"Failed to run pip freeze: {e}")

    # 6. Clean Worktree Check
    clean_worktree = False
    git_dirty_files = []
    try:
        import git
        repo = git.Repo(PROJECT_ROOT, search_parent_directories=True)
        # Check if the repo is dirty, including untracked files
        # We pass untracked_files=True
        clean_worktree = not repo.is_dirty(untracked_files=True)
        if not clean_worktree:
            # list uncommitted changes
            git_dirty_files = [item.a_path for item in repo.index.diff(None)] + repo.untracked_files
            # filter out untracked requirements.txt in parent directory if it's there
            git_dirty_files = [f for f in git_dirty_files if "requirements.txt" not in f or "kattappa/" in f]
            if not git_dirty_files:
                clean_worktree = True
            
            if not clean_worktree and not args.bypass_git:
                errors.append(f"Git worktree is dirty. Uncommitted changes: {git_dirty_files}")
    except Exception as e:
        if not args.bypass_git:
            errors.append(f"Failed to check git status: {e}")

    # 7. Virtualenv Location Verification
    virtualenv_verified = False
    exe_path = sys.executable.lower()
    if "envs\\k-r0.5-py310" in exe_path or "kattappa\\envs" in exe_path:
        virtualenv_verified = True
    else:
        errors.append(f"Virtualenv location verification failed. Executable: {sys.executable}")

    # 8. Browser Check
    browser_status = get_browser_status()
    if not browser_status["chromium"]:
        errors.append("Playwright Chromium browser binary is missing from ms-playwright folder.")

    status = "PASS" if not errors else "FAIL"

    output = {
        "status": status,
        "python_version": sys.version,
        "pytest_version": pytest_version,
        "import_checks": import_results,
        "pip_check": pip_check_status,
        "requirements_hash": requirements_hash,
        "freeze_hash": freeze_hash,
        "clean_worktree": clean_worktree,
        "virtualenv_verified": virtualenv_verified,
        "browser_status": browser_status,
        "errors": errors
    }

    print(json.dumps(output, indent=2))
    if status == "FAIL":
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
