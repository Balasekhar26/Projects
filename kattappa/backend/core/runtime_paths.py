"""Shared Runtime Paths Authority (Program 50.0).

Provides centralized, canonical path resolution and strict containment security checks
for all Kattappa subsystems. Enforces that every file, directory, database, worktree,
and temporary artifact stays strictly inside the project root container (C:\\Users\\balu\\Projects\\kattappa).
"""
from __future__ import annotations

import os
from pathlib import Path

# Absolute allowed container root
CONTAINER_ROOT = Path(r"C:\Users\balu\Projects\kattappa").resolve()


def get_kattappa_container_root() -> Path:
    """Return the absolute, canonical root of the Kattappa project container."""
    if CONTAINER_ROOT.exists():
        return CONTAINER_ROOT
    
    # Fallback to local repo root search
    cwd = Path(__file__).resolve().parent
    for _ in range(5):
        if (cwd / ".git").exists():
            return cwd
        cwd = cwd.parent
    return cwd


def assert_project_local_path(path: Path | str) -> Path:
    """Validate that path resolves strictly inside the Kattappa container root.
    
    Rejects:
    - Path traversal attempts (..)
    - Symlink / junction escapes outside root
    - Drive-letter mismatch
    - UNC path redirection
    """
    resolved = Path(path).resolve()
    root = get_kattappa_container_root()
    
    # Drive mismatch check (Windows)
    if resolved.drive.lower() != root.drive.lower():
        raise ValueError(f"Path '{resolved}' has drive '{resolved.drive}' which mismatches container drive '{root.drive}'")
    
    # UNC path check
    if str(path).startswith(r"\\") or str(resolved).startswith(r"\\"):
        raise ValueError(f"UNC paths are prohibited for container safety: '{path}'")
        
    try:
        resolved.relative_to(root)
    except ValueError:
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
