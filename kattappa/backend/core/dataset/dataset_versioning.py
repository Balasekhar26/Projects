"""Dataset Versioning (Program 26.0).

Maintains metadata snapshots for every generated dataset version so the
corpus history remains auditable and reproducible.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import runtime_data_root


def _versions_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "datasets" / "dataset_versions.json"


class DatasetVersioning:
    """Persists and retrieves versioned dataset metadata."""

    _lock = threading.RLock()

    @classmethod
    def load_versions(cls) -> List[Dict[str, Any]]:
        with cls._lock:
            path = _versions_path()
            if not path.exists():
                return []
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_versions(cls, versions: List[Dict[str, Any]]) -> None:
        with cls._lock:
            path = _versions_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(versions, indent=2), encoding="utf-8")

    @classmethod
    def register_version(
        cls,
        version_id: str,
        sample_count: int,
        fmt: str,
        source_trajectory_count: int,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Records a new dataset version entry."""
        with cls._lock:
            versions = cls.load_versions()
            entry = {
                "version_id": version_id,
                "timestamp": time.time(),
                "sample_count": sample_count,
                "format": fmt,
                "source_trajectory_count": source_trajectory_count,
                "notes": notes,
            }
            versions.append(entry)
            cls.save_versions(versions)
            return entry

    @classmethod
    def get_latest_version(cls) -> Dict[str, Any] | None:
        with cls._lock:
            versions = cls.load_versions()
            if not versions:
                return None
            return sorted(versions, key=lambda v: v["timestamp"])[-1]

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls.save_versions([])
