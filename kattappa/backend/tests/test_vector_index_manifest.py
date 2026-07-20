from __future__ import annotations

import json
from pathlib import Path

from backend.core.vector_index_resilience import VectorIndexManager


def test_manifest_records_provenance_and_checksum(tmp_path: Path) -> None:
    index = tmp_path / "index"
    index.mkdir()
    (index / "vectors.json").write_text("[]", encoding="utf-8")
    manager = VectorIndexManager(
        index_directory=index,
        collection_name="test_vectors",
        embedding_provider="test",
        embedding_model="deterministic",
        embedding_dimension=32,
        memory_mode="isolated",
    )
    manifest = manager.write_manifest(document_count=0)
    assert manifest.schema_version == 1
    assert manifest.collection_name == "test_vectors"
    assert manifest.embedding_dimension == 32
    assert manifest.distance_metric == "cosine"
    assert manager.verify_manifest()
    payload = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
    assert payload["index_checksum"] == manifest.index_checksum
