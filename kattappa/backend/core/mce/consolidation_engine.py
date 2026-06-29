"""MCE Component 7a: Consolidation Engine.

Orchestrates the full 6-stage memory consolidation pipeline:
  1. Deduplicate (DuplicateDetector)
  2. Score (ImportanceScorer)
  3. Promote (EpisodicPromoter)
  4. Extract triples (SemanticExtractor)
  5. Integrate into KG (GraphIntegrator)
  6. Archive stale episodes (ArchiveManager)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict

from backend.core.logger import log_event
from backend.core.mce.archive_manager import ArchiveReport, MCEArchiveManager
from backend.core.mce.duplicate_detector import DuplicationReport, MCEDuplicateDetector
from backend.core.mce.episodic_promoter import MCEEpisodicPromoter, PromotionReport
from backend.core.mce.graph_integrator import IntegrationReport, MCEGraphIntegrator
from backend.core.mce.importance_scorer import MCEImportanceScorer
from backend.core.mce.semantic_extractor import MCESemanticExtractor

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationReport:
    """Summary of a single consolidation cycle."""
    cycle_id: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_sec: float = 0.0

    # Per-stage stats
    dedup: DuplicationReport = field(default_factory=DuplicationReport)
    promotion: PromotionReport = field(default_factory=PromotionReport)
    integration: IntegrationReport = field(default_factory=IntegrationReport)
    archive: ArchiveReport = field(default_factory=ArchiveReport)

    # Derived totals
    episodes_scanned: int = 0
    triples_extracted: int = 0
    success: bool = True
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_sec": round(self.duration_sec, 3),
            "dedup": {
                "exact_dupes": self.dedup.exact_dupe_count,
                "near_dupes": self.dedup.near_dupe_count,
                "unique": self.dedup.unique_count,
            },
            "promotion": {
                "promoted": self.promotion.promoted_count,
                "rejected": self.promotion.rejected_count,
            },
            "integration": {
                "nodes_added": self.integration.nodes_added,
                "relations_added": self.integration.relations_added,
                "errors": self.integration.errors,
            },
            "archive": {
                "archived": self.archive.archived_count,
                "scanned": self.archive.total_scanned,
            },
            "triples_extracted": self.triples_extracted,
            "success": self.success,
            "error": self.error,
        }


class MCEConsolidationEngine:
    """Orchestrates a full memory consolidation cycle."""

    @classmethod
    def run_cycle(
        cls,
        importance_floor: float = 0.65,
        archive_after_days: float = 30.0,
        episode_limit: int = 2000,
        jaccard_threshold: float = 0.85,
    ) -> ConsolidationReport:
        import uuid
        report = ConsolidationReport(
            cycle_id=f"cycle_{uuid.uuid4().hex[:8]}",
            started_at=time.time(),
        )
        log_event("mce_cycle_start", f"Consolidation cycle {report.cycle_id} started")

        try:
            # Stage 1: Deduplication
            report.dedup = MCEDuplicateDetector.detect(
                jaccard_threshold=jaccard_threshold,
                limit=episode_limit,
            )
            unique_ids = report.dedup.unique_ids
            report.episodes_scanned = (
                report.dedup.unique_count
                + report.dedup.exact_dupe_count
                + report.dedup.near_dupe_count
            )

            # Stage 2: Score unique episodes
            scored = MCEImportanceScorer.score_episodes(
                episode_ids=unique_ids if unique_ids else None,
                limit=episode_limit,
            )

            # Stage 3: Promote high-importance episodes to Semantic Memory
            report.promotion = MCEEpisodicPromoter.promote(
                scored_episodes=scored,
                importance_floor=importance_floor,
            )

            # Stage 4: Extract knowledge triples from promoted episodes
            all_triples = []
            promoted_episodes = [
                ep for ep in scored if ep.episode_id in report.promotion.promoted_ids
            ]
            for ep in promoted_episodes:
                triples = MCESemanticExtractor.extract(
                    content=ep.content,
                    source_episode_id=ep.episode_id,
                )
                all_triples.extend(triples)
            report.triples_extracted = len(all_triples)

            # Stage 5: Write triples to Knowledge Graph
            if all_triples:
                report.integration = MCEGraphIntegrator.integrate(all_triples)

            # Stage 6: Archive stale low-recall episodes
            report.archive = MCEArchiveManager.archive_stale(
                archive_after_days=archive_after_days,
            )

        except Exception as exc:
            logger.error("MCE cycle %s failed: %s", report.cycle_id, exc)
            report.success = False
            report.error = str(exc)

        report.completed_at = time.time()
        report.duration_sec = report.completed_at - report.started_at
        log_event(
            "mce_cycle_complete",
            f"Cycle {report.cycle_id} done in {report.duration_sec:.2f}s — "
            f"promoted={report.promotion.promoted_count}, "
            f"kg_nodes={report.integration.nodes_added}, "
            f"archived={report.archive.archived_count}",
        )
        return report
