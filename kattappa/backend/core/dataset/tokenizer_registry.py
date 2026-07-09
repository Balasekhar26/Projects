"""Tokenizer Registry (Program 27.0 / Phase 27B).

Versioned registry of trained SentencePiece tokenizer artefacts.
Persists metadata to JSON so every tokenizer build is auditable and
the active production version can be promoted without filesystem scanning.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import runtime_data_root


def _tokenizers_dir() -> Path:
    p = runtime_data_root() / "backend" / "data" / "tokenizers"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _registry_path() -> Path:
    return _tokenizers_dir() / "registry.json"


class TokenizerRegistry:
    """Thread-safe registry for trained tokenizer artefact metadata."""

    _lock = threading.RLock()

    @classmethod
    def load(cls) -> List[Dict[str, Any]]:
        with cls._lock:
            path = _registry_path()
            if not path.exists():
                return []
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def _save(cls, entries: List[Dict[str, Any]]) -> None:
        _registry_path().write_text(json.dumps(entries, indent=2), encoding="utf-8")

    @classmethod
    def register(
        cls,
        version_id: str,
        vocab_size: int,
        algorithm: str,
        corpus_version: str,
        model_path: str,
        vocab_path: str,
        fertility: float = 0.0,
        oov_rate: float = 0.0,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Adds a new tokenizer version entry to the registry."""
        with cls._lock:
            entries = cls.load()
            entry: Dict[str, Any] = {
                "version_id": version_id,
                "timestamp": time.time(),
                "vocab_size": vocab_size,
                "algorithm": algorithm,
                "corpus_version": corpus_version,
                "model_path": model_path,
                "vocab_path": vocab_path,
                "fertility": fertility,
                "oov_rate": oov_rate,
                "active": False,
                "notes": notes,
            }
            entries.append(entry)
            cls._save(entries)
            return entry

    @classmethod
    def promote(cls, version_id: str) -> bool:
        """Marks a version as active, demoting all others."""
        with cls._lock:
            entries = cls.load()
            found = False
            for e in entries:
                if e["version_id"] == version_id:
                    e["active"] = True
                    found = True
                else:
                    e["active"] = False
            if found:
                cls._save(entries)
            return found

    @classmethod
    def get_active(cls) -> Dict[str, Any] | None:
        """Returns the currently active tokenizer entry, or None."""
        with cls._lock:
            entries = cls.load()
            for e in reversed(entries):
                if e.get("active"):
                    return e
            # Fall back to latest entry if none explicitly promoted
            return entries[-1] if entries else None

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save([])
