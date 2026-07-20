"""Hermetic import-provenance checks for Kattappa development commands."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import site
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


FIRST_PARTY_PACKAGES = (
    "backend",
    "kattappa_native",
    "kattappa_runtime",
    "kattappa_data_engine",
)
OBSOLETE_PACKAGE_NAMES = ("tests",)

# Development commands use an explicit workspace-source model. Python sets
# sys.path[0] to scripts/dev when a script is invoked by file path, so make the
# one supported source root explicit before importing first-party packages.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))


def repository_root() -> Path:
    return _WORKSPACE_ROOT


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _site_package_roots() -> tuple[Path, ...]:
    roots = {Path(value).resolve() for value in site.getsitepackages()}
    user_site = site.getusersitepackages()
    if user_site:
        roots.add(Path(user_site).resolve())
    roots.update(
        Path(value).resolve()
        for value in sys.path
        if value and Path(value).name.lower() in {"site-packages", "dist-packages"}
    )
    return tuple(sorted(roots, key=str))


def _editable_roots() -> tuple[Path, ...]:
    roots: set[Path] = set()
    for distribution in importlib.metadata.distributions():
        try:
            payload = distribution.read_text("direct_url.json")
            if not payload:
                continue
            direct_url = json.loads(payload)
            if not direct_url.get("dir_info", {}).get("editable"):
                continue
            url = str(direct_url.get("url", ""))
            if url.startswith("file:///"):
                roots.add(Path(url[8:]).resolve())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return tuple(sorted(roots, key=str))


@dataclass(frozen=True)
class ImportDiagnostic:
    package: str
    imported_locations: tuple[str, ...]
    conflicts: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class EnvironmentReport:
    status: str
    repository_root: str
    python_executable: str
    installation_model: str
    diagnostics: tuple[ImportDiagnostic, ...]

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _module_locations(package: str) -> tuple[Path, ...]:
    module = importlib.import_module(package)
    locations: set[Path] = set()
    module_file = getattr(module, "__file__", None)
    if module_file:
        locations.add(Path(module_file).resolve())
    module_path = getattr(module, "__path__", None)
    if module_path:
        locations.update(Path(value).resolve() for value in module_path)
    return tuple(sorted(locations, key=str))


def verify_environment(
    *,
    repo_root: Path | None = None,
    site_package_roots: Iterable[Path] | None = None,
    import_packages: bool = True,
) -> EnvironmentReport:
    """Return a non-mutating report for first-party import provenance."""

    root = (repo_root or repository_root()).resolve()
    site_roots = tuple(
        Path(value).resolve()
        for value in (site_package_roots or _site_package_roots())
    )
    editable_roots = _editable_roots()
    diagnostics: list[ImportDiagnostic] = []

    for package in FIRST_PARTY_PACKAGES:
        imported: tuple[Path, ...] = ()
        conflicts: list[Path] = []
        if import_packages:
            try:
                imported = _module_locations(package)
            except ImportError:
                imported = ()

        for site_root in site_roots:
            candidate = site_root / package
            if candidate.exists() and not _inside(candidate, root):
                conflicts.append(candidate.resolve())

        approved = bool(imported) and all(
            _inside(location, root)
            or any(_inside(location, editable) for editable in editable_roots)
            for location in imported
        )
        problems = [str(path) for path in conflicts]
        if import_packages and not imported:
            problems.append("package could not be imported")
        elif import_packages and not approved:
            problems.extend(
                f"import resolves outside repository: {location}"
                for location in imported
                if not _inside(location, root)
            )

        diagnostics.append(
            ImportDiagnostic(
                package=package,
                imported_locations=tuple(str(path) for path in imported),
                conflicts=tuple(dict.fromkeys(problems)),
                status="ok" if not problems else "conflict",
            )
        )

    stale_test_locations = tuple(
        str((site_root / package).resolve())
        for site_root in site_roots
        for package in OBSOLETE_PACKAGE_NAMES
        if (site_root / package).exists()
    )
    diagnostics.append(
        ImportDiagnostic(
            package="tests",
            imported_locations=(),
            conflicts=stale_test_locations,
            status="ok" if not stale_test_locations else "conflict",
        )
    )

    ok = all(item.status == "ok" for item in diagnostics)
    return EnvironmentReport(
        status="ok" if ok else "shadowed",
        repository_root=str(root),
        python_executable=str(Path(sys.executable).resolve()),
        installation_model="workspace_source_path",
        diagnostics=tuple(diagnostics),
    )


def require_verified_environment() -> EnvironmentReport:
    report = verify_environment()
    if not report.ok:
        conflicts = [
            conflict
            for diagnostic in report.diagnostics
            for conflict in diagnostic.conflicts
        ]
        raise RuntimeError(
            "Kattappa environment import shadowing detected. "
            + "Conflicts: "
            + "; ".join(conflicts)
            + ". Repair with: powershell -ExecutionPolicy Bypass "
            + "-File scripts/dev/bootstrap_environment.ps1"
        )
    return report
