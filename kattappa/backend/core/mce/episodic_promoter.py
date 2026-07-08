"""MCE Component 3: Episodic Promoter.

Reads high-scored episodes (composite_score >= importance_floor),
promotes them to SemanticMemory via the CognitiveMemoryBus, and
marks the source episode as promoted in the episodic store.
"""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import List

from backend.core.cognitive_memory_bus import MEMORY_BUS
from backend.core.config import load_config
from backend.core.logger import log_event
from backend.core.mce.importance_scorer import ScoredEpisode

logger = logging.getLogger(__name__)

# Minimum word count for a promotable episode — prevents noise injection
_MIN_WORD_COUNT = 3


@dataclass
class PromotionReport:
    promoted_count: int = 0
    rejected_count: int = 0
    promoted_ids: List[str] = field(default_factory=list)


class MCEEpisodicPromoter:
    """Promotes high-importance episodes to Semantic Memory."""

    DEFAULT_FLOOR: float = 0.65

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @classmethod
    def _mark_promoted(cls, episode_id: str) -> None:
        """Adds a 'promoted' tag to the episode to prevent re-promotion."""
        conn = cls._get_conn()
        try:
            import json
            row = conn.execute("SELECT tags FROM hm_episodes WHERE id = ?", (episode_id,)).fetchone()
            if not row:
                return
            try:
                tags = json.loads(row["tags"])
            except Exception:
                tags = []
            if "promoted" not in tags:
                tags.append("promoted")
            conn.execute(
                "UPDATE hm_episodes SET tags = ? WHERE id = ?",
                (json.dumps(tags), episode_id),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("EpisodicPromoter: failed to mark promoted for %s: %s", episode_id, exc)
            conn.rollback()
        finally:
            conn.close()

    @classmethod
    def promote(
        cls,
        scored_episodes: List[ScoredEpisode],
        importance_floor: float = DEFAULT_FLOOR,
    ) -> PromotionReport:
        """Promotes all episodes with composite_score >= importance_floor."""
        report = PromotionReport()

        for ep in scored_episodes:
            if ep.composite_score < importance_floor:
                report.rejected_count += 1
                continue

            # Quality gate: minimum word count
            word_count = len(ep.content.split())
            if word_count < _MIN_WORD_COUNT:
                report.rejected_count += 1
                continue

            # Check if already promoted
            if "promoted" in ep.domain:
                report.rejected_count += 1
                continue

            concept_id = f"promoted_{ep.episode_id[:8]}"
            try:
                res = MEMORY_BUS.write(
                    memory_type="semantic",
                    data={
                        "concept": concept_id,
                        "description": ep.content,
                        "source_episode_id": ep.episode_id,
                        "provenance": "mce_episodic_promotion",
                        "domain": ep.domain,
                    },
                    confidence=max(0.75, min(1.0, ep.composite_score)),
                    verified=True,
                )
                if res.success:
                    cls._mark_promoted(ep.episode_id)
                    report.promoted_count += 1
                    report.promoted_ids.append(ep.episode_id)
                    log_event("mce_promoted", f"Promoted episode {ep.episode_id} (score={ep.composite_score})")
                else:
                    report.rejected_count += 1
                    logger.debug("MemoryBus rejected promotion of %s: %s", ep.episode_id, res)
            except Exception as exc:
                logger.error("EpisodicPromoter error for %s: %s", ep.episode_id, exc)
                report.rejected_count += 1

        log_event(
            "mce_promotion_complete",
            f"Promotion complete: promoted={report.promoted_count}, rejected={report.rejected_count}",
        )
        return report
