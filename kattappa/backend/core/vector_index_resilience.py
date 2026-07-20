"""Diagnostics and non-destructive recovery primitives for vector indexes."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sqlite3
import threading
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import psutil
from filelock import FileLock, Timeout


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        return digest.hexdigest()
    for item in sorted((value for value in path.rglob("*") if value.is_file()), key=str):
        if item.name == "index_manifest.json":
            continue
        digest.update(str(item.relative_to(path)).replace("\\", "/").encode("utf-8"))
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class VectorIndexManifest:
    schema_version: int
    backend: str
    backend_version: str
    collection_name: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    distance_metric: str
    created_at: str
    updated_at: str
    document_count: int
    index_checksum: str


@dataclass(frozen=True)
class VectorFailureDiagnostic:
    failure_category: str
    exception_class: str
    exception_message: str
    exception_fingerprint: str
    traceback: str
    collection_name: str
    storage_directory: str
    storage_size_bytes: int
    sqlite_size_bytes: int
    embedding_dimension: int
    embedding_provider: str
    embedding_model: str
    backend_version: str
    process_rss_bytes: int
    available_ram_bytes: int
    open_client_count: int
    concurrent_readers: int
    concurrent_writers: int
    index_open_elsewhere: bool
    memory_mode: str
    captured_at: str

    def public_summary(self) -> dict[str, Any]:
        return {
            "failure_category": self.failure_category,
            "exception_class": self.exception_class,
            "exception_fingerprint": self.exception_fingerprint,
            "memory_mode": self.memory_mode,
            "captured_at": self.captured_at,
        }


class VectorIndexLoadError(RuntimeError):
    def __init__(self, diagnostic: VectorFailureDiagnostic):
        super().__init__(diagnostic.exception_message)
        self.diagnostic = diagnostic


class VectorIndexManager:
    """Own one index directory and preserve failed indexes for diagnosis."""

    _counter_lock = threading.Lock()
    _readers = 0
    _writers = 0
    _open_clients = 0

    def __init__(
        self,
        *,
        index_directory: Path,
        collection_name: str,
        embedding_provider: str,
        embedding_model: str,
        embedding_dimension: int,
        memory_mode: str,
        backend: str = "kattappa_json_vector",
        distance_metric: str = "cosine",
        sqlite_path: Path | None = None,
        diagnostics_directory: Path | None = None,
    ) -> None:
        self.index_directory = index_directory.resolve()
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.memory_mode = memory_mode
        self.backend = backend
        self.distance_metric = distance_metric
        self.sqlite_path = sqlite_path.resolve() if sqlite_path else None
        self.diagnostics_directory = (
            diagnostics_directory or self.index_directory.parent / "diagnostics"
        ).resolve()
        self.lock_path = self.index_directory.with_suffix(".writer.lock")

    def _backend_version(self) -> str:
        if self.backend == "chromadb":
            try:
                return importlib.metadata.version("chromadb")
            except importlib.metadata.PackageNotFoundError:
                return "unavailable"
        return "1"

    @property
    def manifest_path(self) -> Path:
        return self.index_directory / "index_manifest.json"

    def write_manifest(self, *, document_count: int, created_at: str | None = None) -> VectorIndexManifest:
        self.index_directory.mkdir(parents=True, exist_ok=True)
        existing_created = created_at
        if self.manifest_path.exists() and not existing_created:
            try:
                existing_created = json.loads(
                    self.manifest_path.read_text(encoding="utf-8")
                ).get("created_at")
            except (OSError, json.JSONDecodeError):
                existing_created = None
        now = _utc_now()
        manifest = VectorIndexManifest(
            schema_version=1,
            backend=self.backend,
            backend_version=self._backend_version(),
            collection_name=self.collection_name,
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            distance_metric=self.distance_metric,
            created_at=existing_created or now,
            updated_at=now,
            document_count=document_count,
            index_checksum=_checksum(self.index_directory),
        )
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(asdict(manifest), indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.manifest_path)
        return manifest

    def read_manifest(self) -> VectorIndexManifest:
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return VectorIndexManifest(**payload)

    def verify_manifest(self) -> bool:
        manifest = self.read_manifest()
        return manifest.index_checksum == _checksum(self.index_directory)

    def _capture_failure(self, exc: BaseException) -> VectorFailureDiagnostic:
        rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        fingerprint = hashlib.sha256(
            f"{type(exc).__module__}.{type(exc).__name__}:{exc}".encode("utf-8")
        ).hexdigest()[:24]
        process = psutil.Process()
        diagnostic = VectorFailureDiagnostic(
            failure_category="VECTOR_INDEX_LOAD_FAILURE",
            exception_class=f"{type(exc).__module__}.{type(exc).__name__}",
            exception_message=str(exc),
            exception_fingerprint=fingerprint,
            traceback=rendered,
            collection_name=self.collection_name,
            storage_directory=str(self.index_directory),
            storage_size_bytes=_directory_size(self.index_directory),
            sqlite_size_bytes=(
                self.sqlite_path.stat().st_size
                if self.sqlite_path and self.sqlite_path.exists()
                else 0
            ),
            embedding_dimension=self.embedding_dimension,
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            backend_version=self._backend_version(),
            process_rss_bytes=process.memory_info().rss,
            available_ram_bytes=psutil.virtual_memory().available,
            open_client_count=self._open_clients,
            concurrent_readers=self._readers,
            concurrent_writers=self._writers,
            index_open_elsewhere=self.lock_path.exists(),
            memory_mode=self.memory_mode,
            captured_at=_utc_now(),
        )
        self.diagnostics_directory.mkdir(parents=True, exist_ok=True)
        report_path = self.diagnostics_directory / f"vector_failure_{fingerprint}.json"
        report_path.write_text(json.dumps(asdict(diagnostic), indent=2) + "\n", encoding="utf-8")
        return diagnostic

    def open(self, loader: Callable[[Path], Any]) -> Any:
        with self._counter_lock:
            type(self)._readers += 1
        try:
            try:
                value = loader(self.index_directory)
                with self._counter_lock:
                    type(self)._open_clients += 1
                return value
            except Exception as exc:
                raise VectorIndexLoadError(self._capture_failure(exc)) from exc
        finally:
            with self._counter_lock:
                type(self)._readers -= 1

    def recover(
        self,
        *,
        authoritative_source: Path | None,
        rebuild: Callable[[Path, Path], int],
        verify: Callable[[Path], bool],
    ) -> dict[str, Any]:
        """Quarantine the original and atomically install a verified rebuild."""

        if authoritative_source is None or not authoritative_source.exists():
            return {"status": "unavailable", "reason": "authoritative source unavailable"}
        try:
            with FileLock(str(self.lock_path), timeout=0):
                with self._counter_lock:
                    type(self)._writers += 1
                try:
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                    quarantine = self.index_directory.with_name(
                        f"{self.index_directory.name}.quarantine.{timestamp}"
                    )
                    if self.index_directory.exists():
                        os.replace(self.index_directory, quarantine)
                    rebuild_dir = self.index_directory.with_name(
                        f"{self.index_directory.name}.rebuild.{timestamp}"
                    )
                    rebuild_dir.mkdir(parents=True, exist_ok=False)
                    document_count = rebuild(authoritative_source, rebuild_dir)
                    if not verify(rebuild_dir):
                        failed = rebuild_dir.with_name(rebuild_dir.name + ".failed")
                        os.replace(rebuild_dir, failed)
                        return {
                            "status": "failed",
                            "quarantine": str(quarantine),
                            "failed_rebuild": str(failed),
                        }
                    os.replace(rebuild_dir, self.index_directory)
                    self.write_manifest(document_count=document_count)
                    return {
                        "status": "recovered",
                        "quarantine": str(quarantine) if quarantine.exists() else None,
                        "active": str(self.index_directory),
                    }
                finally:
                    with self._counter_lock:
                        type(self)._writers -= 1
        except Timeout:
            return {"status": "locked", "reason": "another writer owns the index"}


def sqlite_document_count(path: Path, table: str = "documents") -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
