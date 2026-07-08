"""Provenance Engine Component 3: Source Registry.

Coordinates known information sources and aligns with SourceTrustEngine reputations.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.provenance.models import Source
from backend.core.provenance.store import ProvenanceStore
from backend.core.source_trust_engine import SourceTrustEngine

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Registry coordinating sources and tracking trust reputations dynamically."""

    def __init__(self, store: ProvenanceStore) -> None:
        self._store = store

    def register_source(
        self,
        source_id: str,
        name: str,
        source_type: str,
        base_reputation: float = 0.3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Source:
        """Registers or retrieves a source, ensuring it aligns with the local TrustEngine."""
        # Align/load base reputation from SourceTrustEngine logic
        rep_data = SourceTrustEngine.get_source_reputation(name, source_type)
        current_reputation = rep_data.get("reputation_score", base_reputation)
        trust_level = rep_data.get("trust_level", "LOW")

        src = Source(
            source_id=source_id,
            name=name,
            source_type=source_type,
            base_reputation=base_reputation,
            current_reputation=current_reputation,
            trust_level=trust_level,
            metadata=metadata or {},
        )
        self._store.save_source(src)
        return src

    def get_source(self, source_id: str) -> Optional[Source]:
        """Retrieves source by ID and keeps its current reputation synced with TrustEngine."""
        src = self._store.get_source(source_id)
        if not src:
            return None
        
        # Sync with dynamic outcomes in SourceTrustEngine
        rep_data = SourceTrustEngine.get_source_reputation(src.name, src.source_type)
        synced_reputation = rep_data.get("reputation_score", src.current_reputation)
        synced_trust = rep_data.get("trust_level", src.trust_level)

        if synced_reputation != src.current_reputation or synced_trust != src.trust_level:
            updated_src = Source(
                source_id=src.source_id,
                name=src.name,
                source_type=src.source_type,
                base_reputation=src.base_reputation,
                current_reputation=synced_reputation,
                trust_level=synced_trust,
                metadata=src.metadata,
            )
            self._store.save_source(updated_src)
            return updated_src

        return src

    def list_sources(self) -> List[Source]:
        """Lists all registered sources."""
        return self._store.list_sources()

    def update_reputation(self, name: str, outcome: str) -> None:
        """Triggers a reputation update via SourceTrustEngine, making it persistent."""
        SourceTrustEngine.update_reputation_for_source(name, outcome)
        # Force syncing registered sources sharing this name
        for src in self.list_sources():
            if src.name == name:
                self.get_source(src.source_id)  # triggers sync/update
