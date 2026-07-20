"""Persistent response cache with explicit, observable embedding fallbacks."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Protocol, Sequence
from uuid import uuid4

logger = logging.getLogger(__name__)


class CacheEmbeddingFunction(Protocol):
    def __call__(self, input: Sequence[str]) -> list[list[float]]: ...


class KattappaCacheEmbeddingFunction:
    """Chroma-compatible adapter around Kattappa's canonical RAG embedder."""

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        from backend.core.rag.embedding_engine import EmbeddingEngine

        embeddings = [EmbeddingEngine.get_embedding(text) for text in input]
        status = EmbeddingEngine.status()
        if status["mode"] == "deterministic_fallback":
            raise RuntimeError(
                "Kattappa semantic embedding provider is unavailable: "
                + str(status["reason"])
            )
        return embeddings


class SemanticResponseCache:
    """Persistent exact cache with an optional Chroma semantic index.

    Exact entries are authoritative and remain available if Chroma or the local
    embedding model cannot start. Semantic failures are recorded as degraded
    state rather than being silently converted into cache misses.
    """

    _chroma_client: Any = None
    _collection: Any = None
    _embedding_function: CacheEmbeddingFunction | None = None
    _storage_path_override: Path | None = None
    _semantic_disabled_reason: str | None = None
    _last_error: str | None = None
    _lock = threading.RLock()

    @staticmethod
    def _normalize_query(query: str) -> str:
        return re.sub(r"\s+", " ", query.strip().casefold())

    @classmethod
    def _query_hash(cls, query: str) -> str:
        normalized = cls._normalize_query(query)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def _storage_path(cls) -> Path:
        if cls._storage_path_override is not None:
            return cls._storage_path_override
        from backend.core.config import load_config

        return load_config().chroma_path / "semantic_response_cache.sqlite3"

    @classmethod
    def _connect_exact(cls) -> sqlite3.Connection:
        path = cls._storage_path().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5.0)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_response_cache (
                query_hash TEXT PRIMARY KEY,
                normalized_query TEXT NOT NULL,
                response TEXT NOT NULL,
                selected_agent TEXT NOT NULL,
                created_epoch REAL NOT NULL
            )
            """
        )
        return connection

    @classmethod
    def configure(
        cls,
        *,
        embedding_function: CacheEmbeddingFunction | None = None,
        storage_path: Path | None = None,
    ) -> None:
        """Inject an embedding provider or storage path, primarily for tests."""

        with cls._lock:
            cls._close_chroma()
            cls._chroma_client = None
            cls._collection = None
            cls._embedding_function = embedding_function
            cls._storage_path_override = storage_path
            cls._semantic_disabled_reason = None
            cls._last_error = None

    @classmethod
    def _close_chroma(cls) -> None:
        """Release persistent Chroma handles before reconfiguration on Windows."""

        if cls._chroma_client is None:
            return
        try:
            system = getattr(cls._chroma_client, "_system", None)
            if system is not None:
                system.stop()
            from chromadb.api.client import SharedSystemClient

            SharedSystemClient.clear_system_cache()
        except Exception:
            logger.exception("failed to close semantic cache Chroma client")

    @classmethod
    def reset(cls) -> None:
        cls.configure()

    @classmethod
    def _disable_semantic(cls, exc: BaseException) -> None:
        reason = f"{type(exc).__name__}: {exc}"
        cls._semantic_disabled_reason = reason
        cls._last_error = reason
        cls._collection = None
        logger.warning(
            "semantic_response_cache_degraded %s",
            json.dumps({"mode": "exact_match_fallback", "reason": reason}),
        )

    @classmethod
    def _get_collection(cls) -> Any | None:
        with cls._lock:
            if cls._semantic_disabled_reason is not None:
                return None
            if cls._collection is not None:
                return cls._collection
            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings

                from backend.core.config import load_config

                cfg = load_config()
                chroma_path = (
                    cls._storage_path_override.parent / "chroma"
                    if cls._storage_path_override is not None
                    else cfg.chroma_path
                )
                chroma_path.mkdir(parents=True, exist_ok=True)
                cls._chroma_client = chromadb.PersistentClient(
                    path=str(chroma_path),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                embedding_function = (
                    cls._embedding_function or KattappaCacheEmbeddingFunction()
                )
                cls._collection = cls._chroma_client.get_or_create_collection(
                    "kattappa_semantic_cache_v2",
                    embedding_function=embedding_function,
                    metadata={"hnsw:space": "cosine"},
                )
                return cls._collection
            except Exception as exc:
                cls._disable_semantic(exc)
                return None

    @classmethod
    def _get_exact(
        cls, query: str, ttl_seconds: float
    ) -> tuple[str | None, str | None]:
        try:
            with closing(cls._connect_exact()) as connection:
                with connection:
                    row = connection.execute(
                        """
                        SELECT response, selected_agent, created_epoch
                        FROM semantic_response_cache WHERE query_hash = ?
                        """,
                        (cls._query_hash(query),),
                    ).fetchone()
                    if row is None:
                        return None, None
                    if time.time() - float(row[2]) > ttl_seconds:
                        connection.execute(
                            "DELETE FROM semantic_response_cache WHERE query_hash = ?",
                            (cls._query_hash(query),),
                        )
                        return None, None
                    return str(row[0]), str(row[1])
        except Exception as exc:
            cls._last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("semantic response exact-cache read failed")
            return None, None

    @classmethod
    def get(
        cls, query: str, ttl_seconds: float = 3600.0
    ) -> tuple[str | None, str | None]:
        exact = cls._get_exact(query, ttl_seconds)
        if exact[0] is not None:
            return exact

        collection = cls._get_collection()
        if collection is None:
            return None, None
        try:
            if collection.count() == 0:
                return None, None
            result = collection.query(query_texts=[query], n_results=1)
            if not result or not result.get("documents") or not result["documents"][0]:
                return None, None
            if float(result["distances"][0][0]) > 0.45:
                return None, None
            metadata = result["metadatas"][0][0]
            if time.time() - float(metadata.get("timestamp", 0.0)) > ttl_seconds:
                return None, None
            return metadata.get("response"), metadata.get("selected_agent")
        except Exception as exc:
            cls._disable_semantic(exc)
            return None, None

    @classmethod
    def set(cls, query: str, response: str, selected_agent: str) -> None:
        normalized = cls._normalize_query(query)
        timestamp = time.time()
        try:
            with closing(cls._connect_exact()) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO semantic_response_cache (
                            query_hash, normalized_query, response,
                            selected_agent, created_epoch
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(query_hash) DO UPDATE SET
                            normalized_query = excluded.normalized_query,
                            response = excluded.response,
                            selected_agent = excluded.selected_agent,
                            created_epoch = excluded.created_epoch
                        """,
                        (
                            cls._query_hash(query),
                            normalized,
                            response,
                            selected_agent,
                            timestamp,
                        ),
                    )
        except Exception:
            logger.exception("semantic response exact-cache write failed")
            return

        collection = cls._get_collection()
        if collection is None:
            return
        try:
            existing = collection.get(where={"query_hash": cls._query_hash(query)})
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
            collection.add(
                ids=[str(uuid4())],
                documents=[query],
                metadatas=[
                    {
                        "query_hash": cls._query_hash(query),
                        "response": response,
                        "timestamp": timestamp,
                        "selected_agent": selected_agent,
                    }
                ],
            )
        except Exception as exc:
            cls._disable_semantic(exc)

    @classmethod
    def health(cls) -> dict[str, str | bool | None]:
        """Return lightweight readiness telemetry without loading a model."""

        semantic_available = cls._collection is not None
        if cls._semantic_disabled_reason:
            mode = "exact_match_fallback"
            reason = cls._semantic_disabled_reason
        elif semantic_available:
            mode = "semantic"
            reason = None
        else:
            mode = "exact_match_with_lazy_semantic"
            reason = "semantic provider has not been initialized"
        return {
            "available": True,
            "semantic_available": semantic_available,
            "mode": mode,
            "reason": reason,
            "last_error": cls._last_error,
        }
