"""Shared Runtime Paths Authority (Program 50.0).

Provides centralized, canonical path resolution and strict containment security checks
for all Kattappa subsystems. Enforces that every file, directory, database, worktree,
and temporary artifact stays strictly inside the project root container (C:\\Users\\balu\\Projects\\kattappa).
"""
from __future__ import annotations

import os
from pathlib import Path

# Absolute allowed container root default
CONTAINER_ROOT_DEFAULT = Path(r"C:\Users\balu\Projects\kattappa").resolve()


def get_kattappa_container_root() -> Path:
    """Return the absolute, canonical root of the Kattappa project container.
    
    Authority chain:
    1. Explicit KATTAPPA_CONTAINER_ROOT env var
    2. Governance config workspace_dir (if available)
    3. Local default or .git (file or directory) upward search
    4. Fail closed if no root found
    """
    # 1. Env Var Authority
    env_root = os.getenv("KATTAPPA_CONTAINER_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if candidate.is_dir():
            return candidate

    # 2. Config Authority
    try:
        from backend.core.config import load_config
        config = load_config()
        if hasattr(config, "workspace_dir") and config.workspace_dir:
            cfg_root = Path(config.workspace_dir).resolve()
            if cfg_root.is_dir():
                return cfg_root
    except Exception:
        pass

    # 3. Default container root
    if CONTAINER_ROOT_DEFAULT.is_dir():
        return CONTAINER_ROOT_DEFAULT

    # Upward search for .git file or directory
    cwd = Path(__file__).resolve().parent
    for _ in range(7):
        if (cwd / ".git").exists():
            return cwd
        cwd = cwd.parent

    raise RuntimeError("No valid Kattappa container root found. Execution failed closed.")


def assert_project_local_path(path: Path | str) -> Path:
    """Validate that path resolves strictly inside the Kattappa container root.
    
    Rejects:
    - Path traversal attempts (..)
    - Symlink / junction escapes outside root
    - Drive-letter mismatch
    - UNC path redirection
    """
    p_str = str(path)
    if p_str.startswith(r"\\") or p_str.startswith("//"):
        raise ValueError(f"UNC paths are prohibited for container safety: '{path}'")

    resolved = Path(path).resolve()
    root = get_kattappa_container_root()
    
    # Drive mismatch check (Windows)
    if os.name == 'nt' and resolved.drive.lower() != root.drive.lower():
        raise ValueError(f"Path '{resolved}' has drive '{resolved.drive}' which mismatches container drive '{root.drive}'")
        
    try:
        resolved.relative_to(root)
    except ValueError:
        if os.name == 'nt':
            r_parts = [pt.lower() for pt in root.parts]
            p_parts = [pt.lower() for pt in resolved.parts]
            if len(p_parts) >= len(r_parts) and p_parts[:len(r_parts)] == r_parts:
                return resolved
        raise ValueError(f"Security Violation: Path '{resolved}' escapes project container root '{root}'")
        
    return resolved


def get_runtime_root() -> Path:
    """Return the project-local runtime root directory."""
    root = get_kattappa_container_root() / "runtime"
    root.mkdir(parents=True, exist_ok=True)
    return assert_project_local_path(root)


def get_sandbox_root() -> Path:
    """Return the project-local sandbox root directory.
    
    Uses KATTAPPA_SANDBOX_ROOT env var if set (and valid), otherwise defaults to
    <container_root>/runtime/sandboxes.
    """
    env_root = os.getenv("KATTAPPA_SANDBOX_ROOT")
    if env_root:
        root = Path(env_root).resolve()
    else:
        root = get_runtime_root() / "sandboxes"
        
    assert_project_local_path(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_validation_workspace_root(run_id: str) -> Path:
    """Return the project-local workspace root for a validation run."""
    root = get_kattappa_container_root() / "validation-runs" / run_id
    assert_project_local_path(root)
    root.mkdir(parents=True, exist_ok=True)
    return root
