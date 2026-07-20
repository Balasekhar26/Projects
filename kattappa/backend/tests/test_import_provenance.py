from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.dev.environment_guard import FIRST_PARTY_PACKAGES, verify_environment


ROOT = Path(__file__).resolve().parents[2]


def test_workspace_imports_are_verified() -> None:
    report = verify_environment(repo_root=ROOT)
    assert report.ok
    assert report.installation_model == "workspace_source_path"
    for package in FIRST_PARTY_PACKAGES:
        item = next(value for value in report.diagnostics if value.package == package)
        assert item.status == "ok"
        assert item.imported_locations
        assert all(str(ROOT) in location for location in item.imported_locations)


def test_simulated_duplicate_package_is_detected_without_mutation(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    duplicate = site_packages / "backend"
    duplicate.mkdir(parents=True)
    marker = duplicate / "__init__.py"
    marker.write_text("STALE = True\n", encoding="utf-8")
    before = marker.read_bytes()

    report = verify_environment(
        repo_root=ROOT,
        site_package_roots=(site_packages,),
        import_packages=False,
    )

    assert not report.ok
    diagnostic = next(value for value in report.diagnostics if value.package == "backend")
    assert str(duplicate.resolve()) in diagnostic.conflicts
    assert marker.read_bytes() == before


def test_stale_tests_package_is_detected(tmp_path: Path) -> None:
    stale = tmp_path / "site-packages" / "tests"
    stale.mkdir(parents=True)
    report = verify_environment(
        repo_root=ROOT,
        site_package_roots=(stale.parent,),
        import_packages=False,
    )
    diagnostic = next(value for value in report.diagnostics if value.package == "tests")
    assert diagnostic.status == "conflict"
    assert diagnostic.conflicts == (str(stale.resolve()),)


def test_cli_outputs_structured_diagnostics() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev" / "verify_environment.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "ok"
    assert report["repository_root"] == str(ROOT)
