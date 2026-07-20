from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.core.superbench_memory import MemoryMode, SuperbenchMemorySession


def test_isolated_memory_uses_run_workspace(tmp_path: Path) -> None:
    session = SuperbenchMemorySession(tmp_path / "run-a", MemoryMode.ISOLATED)
    result = session.prepare("isolated prompt")
    assert result.backend == "isolated_vector"
    assert session.sqlite_path.is_file()
    assert session.manager.manifest_path.is_file()


def test_vector_failure_degrades_and_quarantines_without_deletion(tmp_path: Path) -> None:
    session = SuperbenchMemorySession(tmp_path / "run", MemoryMode.ISOLATED)
    result = session.prepare("prompt", simulate_vector_failure=True)
    assert result.backend == "keyword_fallback"
    assert result.failure_category == "VECTOR_INDEX_LOAD_FAILURE"
    assert result.recovery_action == "recovered"
    assert list((tmp_path / "run" / "memory").glob("vector_index.quarantine.*"))
    assert session.index_path.exists()


def test_concurrent_runs_never_share_mutable_index_state(tmp_path: Path) -> None:
    def prepare(name: str) -> Path:
        session = SuperbenchMemorySession(tmp_path / name, MemoryMode.ISOLATED)
        assert session.prepare(name).backend == "isolated_vector"
        return session.index_path

    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(prepare, ("run-a", "run-b")))
    assert paths[0] != paths[1]
    assert all(path.exists() for path in paths)
