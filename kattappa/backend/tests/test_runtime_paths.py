import os
import pytest
from pathlib import Path
from backend.core.runtime_paths import (
    get_kattappa_container_root,
    assert_project_local_path,
    get_runtime_root,
    get_sandbox_root,
    get_validation_workspace_root,
)


def test_container_root_resolution():
    root = get_kattappa_container_root()
    assert root.exists()
    assert (root / ".git").exists() or root == Path(r"C:\Users\balu\Projects\kattappa").resolve()


def test_assert_project_local_path_valid():
    root = get_kattappa_container_root()
    valid_file = root / "backend" / "core" / "runtime_paths.py"
    res = assert_project_local_path(valid_file)
    assert res == valid_file.resolve()


def test_assert_project_local_path_unc_rejected():
    with pytest.raises(ValueError, match="UNC paths are prohibited"):
        assert_project_local_path(r"\\evil-server\share\file.txt")


def test_assert_project_local_path_escape_rejected():
    with pytest.raises(ValueError, match="escapes project container root"):
        assert_project_local_path(r"C:\Windows\System32\cmd.exe")


def test_runtime_directories_inside_container():
    rt = get_runtime_root()
    sb = get_sandbox_root()
    val = get_validation_workspace_root("test_run_123")
    
    root = get_kattappa_container_root()
    assert rt.relative_to(root)
    assert sb.relative_to(root)
    assert val.relative_to(root)
