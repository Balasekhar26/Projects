"""MCE Component 2: Importance Scorer.

Calculates a composite importance score for episodic memories based on:
- Base importance value already stored on the episode
- Recency bonus: decaying boost if recalled within last 24 hours
- Recall frequency bonus: +0.05 per recall above baseline
- Domain weight multiplier (configurable per domain)
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


# Per-domain importance multipliers
DOMAIN_WEIGHTS: Dict[str, float] = {
    "technical": 1.2,
    "code": 1.2,
    "personal": 1.1,
    "goal": 1.15,
    "research": 1.1,
    "general": 1.0,
    "transient": 0.7,
}


@dataclass
class ScoredEpisode:
    episode_id: str
    content: str
    base_importance: float
    composite_score: float
    domain: str
    recall_count: int
    last_recalled_at: float


class MCEImportanceScorer:
    """Scores episodic memories for consolidation promotion candidacy."""

    RECENCY_WINDOW_SEC: float = 86400.0   # 24 hours
    RECALL_BONUS_PER_HIT: float = 0.05
    RECALL_BONUS_CAP: float = 0.25

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @classmethod
    def score_episodes(
        cls,
        episode_ids: Optional[List[str]] = None,
        limit: int = 2000,
    ) -> List[ScoredEpisode]:
        """Score episodes and return them sorted by composite_score descending."""
        conn = cls._get_conn()
        now = time.time()

        try:
            if episode_ids:
                placeholders = ",".join("?" * len(episode_ids))
                rows = conn.execute(
                    f"SELECT * FROM hm_episodes WHERE id IN ({placeholders})",
                    episode_ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hm_episodes WHERE pinned = 0 ORDER BY importance DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except Exception as exc:
            logger.warning("ImportanceScorer: could not read episodes: %s", exc)
            return []
        finally:
            conn.close()

        scored: List[ScoredEpisode] = []
        for row in rows:
            base = float(row["importance"])

            # 1. Recency bonus (linear decay within 24h window)
            age_sec = now - float(row["last_recalled_at"])
            recency_bonus = max(0.0, 0.15 * (1.0 - age_sec / cls.RECENCY_WINDOW_SEC))

            # 2. Recall frequency bonus
            recalls = max(0, int(row["recall_count"]) - 1)
            recall_bonus = min(cls.RECALL_BONUS_CAP, recalls * cls.RECALL_BONUS_PER_HIT)

            # 3. Domain multiplier
            tags_raw = row["tags"] if "tags" in row.keys() else "[]"
            try:
                import json
                tags = json.loads(tags_raw)
            except Exception:
                tags = []
            domain = "general"
            for tag in tags:
                if tag.lower() in DOMAIN_WEIGHTS:
                    domain = tag.lower()
                    break
            domain_mult = DOMAIN_WEIGHTS.get(domain, 1.0)

            composite = min(1.0, (base + recency_bonus + recall_bonus) * domain_mult)
            scored.append(
                ScoredEpisode(
                    episode_id=row["id"],
                    content=row["content"],
                    base_importance=base,
                    composite_score=round(composite, 4),
                    domain=domain,
                    recall_count=int(row["recall_count"]),
                    last_recalled_at=float(row["last_recalled_at"]),
                )
            )

        scored.sort(key=lambda s: s.composite_score, reverse=True)
        log_event("mce_importance_scored", f"Scored {len(scored)} episodes")
        return scored
