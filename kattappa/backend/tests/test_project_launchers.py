from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

PROJECTS = [
    "kattappa",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore").lower()


def test_each_project_has_double_click_setup_and_run_launcher() -> None:
    for project in PROJECTS:
        root = REPO_ROOT / project
        if not root.exists():
            continue
        assert (root / "setup.bat").exists(), project
        assert (root / "run.exe").exists(), project
        assert (root / "scripts" / "run.cmd").exists(), project


def test_each_setup_supports_setup_only_mode() -> None:
    for project in PROJECTS:
        root = REPO_ROOT / project
        if not root.exists():
            continue
        setup_text = _read(root / "setup.bat")
        assert "--setup-only" in setup_text, project


def test_non_kattappa_setups_launch_their_project_after_setup() -> None:
    for project in PROJECTS:
        root = REPO_ROOT / project
        if not root.exists():
            continue
        setup_text = _read(root / "setup.bat")
        if project == "kattappa":
            assert "--launch" in setup_text, project
        else:
            assert "scripts\\run.cmd" in setup_text, project


def test_run_launchers_self_setup_when_runtime_is_missing() -> None:
    for project in PROJECTS:
        root = REPO_ROOT / project
        if not root.exists():
            continue
        run_text = _read(root / "scripts" / "run.cmd")
        assert "setup.bat" in run_text, project
        assert "--setup-only" in run_text, project
