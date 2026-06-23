"""
Step 9.0 — Research Reader module.
Fetches and logs research papers/articles and maps trust levels.
"""
from __future__ import annotations

import json
import time
import uuid
import threading
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.source_trust_engine import SourceTrustEngine, TrustLevel
from backend.core.research_memory import ResearchMemory


def _documents_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "research_documents.json"


TRUST_MAP = {
    "peer_reviewed": "High",
    "reproduced": "High",
    "preprint": "Medium",
    "blog": "Low",
}


DEFAULT_SOURCES = [
    {
        "source": "arXiv:2406.1234",
        "title": "Adaptive Memory Consolidation in LLM Agents",
        "content": "This paper presents a method for dynamically summarizing and consolidating agent experience memory. By compressing old episodic memories into semantic structures, retrieval latency is minimized.",
        "source_type": "peer_reviewed",
    },
    {
        "source": "arXiv:2407.5678",
        "title": "Skepticism Filters for Self-Improving Codebases",
        "content": "To prevent cascades of bad suggestions, LLMs must pass through strict skepticism checks. Occam gates compare the expected ROI of complex changes to simple caching adjustments.",
        "source_type": "preprint",
    },
    {
        "source": "Blog: Engineering AI",
        "title": "Fast Retrieval in Vector Space via Orphan Garbage Collection",
        "content": "Orphaned vector embeddings slow down semantic search. Regular garbage collection sweeps remove expired candidates and maintain database indexing efficiency.",
        "source_type": "blog",
    },
]


class ResearchReader:
    _lock = threading.RLock()

    @classmethod
    def _load_documents(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _documents_path()
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def _save_documents(cls, docs: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _documents_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(docs, indent=2), encoding="utf-8")

    @classmethod
    def read_sources(cls, custom_sources: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Reads sources, deduplicates against stored documents and research memory, logs new ones, and returns them."""
        sources_to_read = custom_sources if custom_sources is not None else DEFAULT_SOURCES
        
        with cls._lock:
            existing_docs = cls._load_documents()
            existing_titles = {d["title"].strip().lower() for d in existing_docs if "title" in d}
            
            new_docs = []
            for src in sources_to_read:
                title = src.get("title", "").strip()
                if not title:
                    continue
                if title.lower() in existing_titles or ResearchMemory.is_duplicate_document(title):
                    continue  # Deduplicated!
                
                source_name = src.get("source", "Unknown")
                source_type = src.get("source_type", "preprint").strip().lower()
                
                # Fetch trust level from reputation engine
                rep_data = SourceTrustEngine.get_source_reputation(source_name, source_type)
                trust_level = rep_data.get("trust_level", TrustLevel.LOW.value)
                
                # Skip documents from REJECTED sources
                if trust_level == TrustLevel.REJECTED.value:
                    continue

                # Map TrustLevel enum string back to old High/Medium/Low representation for backward compatibility
                compat_trust_level = "Low"
                if trust_level in (TrustLevel.VERIFIED.value, TrustLevel.HIGH.value):
                    compat_trust_level = "High"
                elif trust_level == TrustLevel.MEDIUM.value:
                    compat_trust_level = "Medium"

                doc = {
                    "id": f"doc_{uuid.uuid4().hex[:12]}",
                    "source": source_name,
                    "title": title,
                    "content": src.get("content", ""),
                    "source_type": source_type,
                    "trust_level": compat_trust_level,
                    "timestamp": time.time(),
                }
                new_docs.append(doc)
                existing_docs.append(doc)
                existing_titles.add(title.lower())
                
                # Record in research memory
                ResearchMemory.record_read(title)
                
            if new_docs:
                cls._save_documents(existing_docs)
                
            return new_docs
