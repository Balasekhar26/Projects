from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.core.vector_index_resilience import VectorIndexLoadError, VectorIndexManager


def _manager(tmp_path: Path) -> VectorIndexManager:
    return VectorIndexManager(
        index_directory=tmp_path / "index",
        collection_name="test",
        embedding_provider="test",
        embedding_model="test-v1",
        embedding_dimension=2,
        memory_mode="isolated",
        sqlite_path=tmp_path / "source.sqlite3",
    )


def test_load_failure_captures_complete_diagnostic(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.index_directory.mkdir()
    (manager.index_directory / "broken.bin").write_bytes(b"broken")
    with pytest.raises(VectorIndexLoadError) as raised:
        manager.open(lambda _: (_ for _ in ()).throw(MemoryError("loadIndex allocation")))
    diagnostic = raised.value.diagnostic
    assert diagnostic.failure_category == "VECTOR_INDEX_LOAD_FAILURE"
    assert diagnostic.exception_class.endswith("MemoryError")
    assert diagnostic.storage_size_bytes > 0
    assert diagnostic.embedding_dimension == 2
    assert diagnostic.process_rss_bytes > 0
    assert list((tmp_path / "diagnostics").glob("vector_failure_*.json"))


def test_corrupt_index_is_quarantined_and_verified_rebuild_switches_atomically(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.index_directory.mkdir()
    original = manager.index_directory / "broken.bin"
    original.write_bytes(b"preserve-me")
    with sqlite3.connect(manager.sqlite_path) as connection:
        connection.execute("CREATE TABLE documents (id TEXT, content TEXT)")
        connection.execute("INSERT INTO documents VALUES ('1', 'safe source')")

    def rebuild(source: Path, target: Path) -> int:
        assert source == manager.sqlite_path
        (target / "vectors.json").write_text("[]", encoding="utf-8")
        return 1

    result = manager.recover(
        authoritative_source=manager.sqlite_path,
        rebuild=rebuild,
        verify=lambda path: json.loads((path / "vectors.json").read_text()) == [],
    )
    assert result["status"] == "recovered"
    quarantine = Path(result["quarantine"])
    assert (quarantine / "broken.bin").read_bytes() == b"preserve-me"
    assert manager.index_directory.exists()
    assert manager.verify_manifest()


def test_missing_authoritative_source_preserves_index(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.index_directory.mkdir()
    original = manager.index_directory / "broken.bin"
    original.write_bytes(b"keep")
    result = manager.recover(
        authoritative_source=None,
        rebuild=lambda *_: 0,
        verify=lambda _: False,
    )
    assert result["status"] == "unavailable"
    assert original.read_bytes() == b"keep"
    assert not list(tmp_path.glob("*.quarantine.*"))
