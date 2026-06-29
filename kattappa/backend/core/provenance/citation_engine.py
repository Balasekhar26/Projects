"""Provenance Engine Component 4: Citation Engine.

Generates human-readable citation strings and Markdown representation of evidence chains.
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from backend.core.provenance.models import ProvenanceEvidenceItem, Source
from backend.core.provenance.store import ProvenanceStore


class CitationEngine:
    """Formats evidence lists and source statistics into citation formats."""

    def __init__(self, store: ProvenanceStore) -> None:
        self._store = store

    def format_evidence_item(self, item: ProvenanceEvidenceItem) -> str:
        """Formats a single evidence record as a clean string."""
        src = self._store.get_source(item.source_id)
        src_name = src.name if src else item.source_id
        src_type = src.source_type if src else "unknown"

        date_str = datetime.datetime.fromtimestamp(
            item.observed_at, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")

        state_str = item.verification_state.value
        support_str = "supports" if item.supports else "refutes"

        citation = f"[{item.evidence_level.name}] {src_name} ({src_type}) {support_str} (conf: {item.confidence:.2f}) observed on {date_str} [{state_str}]"
        if item.context_citation:
            citation += f" ref: {item.context_citation}"
        return citation

    def generate_markdown_citation_chain(self, target_id: str) -> str:
        """Generates a complete Markdown tree representation of the evidence chain for an entity."""
        evidence_list = self._store.get_evidence_for_target(target_id)
        if not evidence_list:
            return f"* No evidence recorded for target `{target_id}`"

        lines = [f"### Provenance Chain for `{target_id}`"]
        for idx, ev in enumerate(evidence_list, 1):
            line = f"{idx}. {self.format_evidence_item(ev)}"
            if ev.metadata:
                line += f"  \n   *Metadata: {ev.metadata}*"
            lines.append(line)
        return "\n".join(lines)
