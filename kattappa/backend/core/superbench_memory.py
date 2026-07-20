"""Run-scoped memory isolation and degradation for Superbench."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.vector_index_resilience import VectorIndexLoadError, VectorIndexManager


class MemoryMode(str, Enum):
    ISOLATED = "isolated"
    READ_ONLY = "read_only"
    PRODUCTION = "production"


def _embedding(text: str, dimension: int = 32) -> list[float]:
    values = [0.0] * dimension
    for token in text.lower().split():
        values[int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % dimension] += 1.0
    return values


@dataclass(frozen=True)
class MemoryPreparation:
    backend: str
    warnings: tuple[str, ...]
    failure_category: str | None = None
    exception_fingerprint: str | None = None
    recovery_action: str | None = None


class SuperbenchMemorySession:
    """Own all mutable memory for one benchmark run."""

    def __init__(self, workspace: Path, mode: MemoryMode) -> None:
        self.workspace = workspace.resolve()
        self.mode = mode
        self.sqlite_path = self.workspace / "memory" / "authoritative.sqlite3"
        self.index_path = self.workspace / "memory" / "vector_index"
        self.manager = VectorIndexManager(
            index_directory=self.index_path,
            collection_name="superbench_run_memory",
            embedding_provider="kattappa_deterministic",
            embedding_model="sha256-token-v1",
            embedding_dimension=32,
            memory_mode=mode.value,
            sqlite_path=self.sqlite_path,
            diagnostics_directory=self.workspace / "diagnostics",
        )

    def _seed_authoritative_source(self, prompt: str) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, content TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT OR REPLACE INTO documents VALUES (?, ?)", ("task_prompt", prompt)
            )
            connection.commit()

    @staticmethod
    def _build(source: Path, target: Path) -> int:
        with sqlite3.connect(source) as connection:
            rows = connection.execute("SELECT id, content FROM documents ORDER BY id").fetchall()
        payload = [
            {"id": row[0], "content": row[1], "embedding": _embedding(row[1])}
            for row in rows
        ]
        (target / "vectors.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return len(payload)

    @staticmethod
    def _verify(path: Path) -> bool:
        payload = json.loads((path / "vectors.json").read_text(encoding="utf-8"))
        return isinstance(payload, list) and all(len(item["embedding"]) == 32 for item in payload)

    @staticmethod
    def _load(path: Path, *, simulate_failure: bool) -> list[dict[str, Any]]:
        if simulate_failure:
            raise MemoryError("controlled loadIndex memory-allocation failure")
        payload = json.loads((path / "vectors.json").read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("vector index payload must be a list")
        return payload

    def prepare(
        self,
        prompt: str,
        *,
        vector_enabled: bool = True,
        simulate_vector_failure: bool = False,
    ) -> MemoryPreparation:
        if self.mode is not MemoryMode.ISOLATED:
            return MemoryPreparation(
                backend="production_read_only" if self.mode is MemoryMode.READ_ONLY else "production",
                warnings=(),
            )

        self._seed_authoritative_source(prompt)
        if not vector_enabled:
            return MemoryPreparation(
                backend="keyword_fallback",
                warnings=("Vector memory disabled; isolated SQLite keyword retrieval selected.",),
            )

        self.index_path.mkdir(parents=True, exist_ok=True)
        self._build(self.sqlite_path, self.index_path)
        self.manager.write_manifest(document_count=1)
        try:
            self.manager.open(
                lambda path: self._load(path, simulate_failure=simulate_vector_failure)
            )
            return MemoryPreparation(backend="isolated_vector", warnings=())
        except VectorIndexLoadError as exc:
            recovery = self.manager.recover(
                authoritative_source=self.sqlite_path,
                rebuild=self._build,
                verify=self._verify,
            )
            return MemoryPreparation(
                backend="keyword_fallback",
                warnings=(
                    "Vector index unavailable; isolated SQLite keyword retrieval selected.",
                ),
                failure_category=exc.diagnostic.failure_category,
                exception_fingerprint=exc.diagnostic.exception_fingerprint,
                recovery_action=str(recovery.get("status")),
            )
