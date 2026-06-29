"""Provenance Engine Component 6: Coordinator.

Provides a unified coordinator class serving as the single entry point for Program 5A.
Coordinates store, source registry, citation engine, and KG helper interfaces.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.core.provenance.citation_engine import CitationEngine
from backend.core.provenance.kg_helper import ProvenanceKGHelper
from backend.core.provenance.models import ProvenanceEvidenceItem, ProvenanceRecord, Source
from backend.core.provenance.source_registry import SourceRegistry
from backend.core.provenance.store import ProvenanceStore


class ProvenanceCoordinator:
    """Unified entry point coordinating all Provenance operations."""

    _instance: Optional["ProvenanceCoordinator"] = None

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._store = ProvenanceStore(db_path=db_path)
        self._sources = SourceRegistry(self._store)
        self._citations = CitationEngine(self._store)
        self._kg_helper = ProvenanceKGHelper(self._store)

    @classmethod
    def get_instance(cls) -> "ProvenanceCoordinator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls, db_path: Optional[str] = None) -> "ProvenanceCoordinator":
        """For testing: resets singleton with custom database path."""
        cls._instance = cls(db_path=db_path)
        return cls._instance

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def store(self) -> ProvenanceStore:
        return self._store

    @property
    def sources(self) -> SourceRegistry:
        return self._sources

    @property
    def citations(self) -> CitationEngine:
        return self._citations

    @property
    def kg(self) -> ProvenanceKGHelper:
        return self._kg_helper

    # ------------------------------------------------------------------
    # High-level Operations
    # ------------------------------------------------------------------

    def add_manual_evidence(
        self,
        target_id: str,
        source_id: str,
        evidence_level: Any,
        confidence: float = 1.0,
        verification_state: str = "UNVERIFIED",
        context_citation: str = "",
        supports: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceEvidenceItem:
        """Manually registers an evidence item and links it to a target ID."""
        ev = ProvenanceEvidenceItem.create(
            source_id=source_id,
            evidence_level=evidence_level,
            confidence=confidence,
            verification_state=verification_state,
            context_citation=context_citation,
            supports=supports,
            metadata=metadata,
        )
        self._store.save_evidence(ev)
        self._store.link_target_to_evidence(target_id, ev.evidence_id)
        return ev
